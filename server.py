import os
import time
import asyncio
from collections import defaultdict
from typing import Any

import httpx
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

SERVER_NAME = "Zoho Books Reports"
ZOHO_DC = os.getenv("ZOHO_DC", "in")
ZOHO_ORG_ID = os.getenv("ZOHO_ORG_ID", "")
ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID", "")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET", "")
ZOHO_REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN", "")
ALLOWED_HOST = os.getenv("ALLOWED_HOST", "localhost")

API_BASE = f"https://www.zohoapis.{ZOHO_DC}/books/v3"
ACCOUNTS_BASE = f"https://accounts.zoho.{ZOHO_DC}/oauth/v2/token"

mcp = MCPServer(
    SERVER_NAME,
    instructions=(
        "Read-only Zoho Books reporting connector. Never creates, updates, or deletes data. "
        "Use organization_id from environment by default unless explicitly supplied."
    ),
)

_access_token: str | None = None
_token_expires_at = 0.0


def _require_env() -> None:
    missing = [
        k for k, v in {
            "ZOHO_ORG_ID": ZOHO_ORG_ID,
            "ZOHO_CLIENT_ID": ZOHO_CLIENT_ID,
            "ZOHO_CLIENT_SECRET": ZOHO_CLIENT_SECRET,
            "ZOHO_REFRESH_TOKEN": ZOHO_REFRESH_TOKEN,
        }.items() if not v
    ]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


async def _get_access_token() -> str:
    global _access_token, _token_expires_at
    _require_env()
    if _access_token and time.time() < _token_expires_at - 60:
        return _access_token

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            ACCOUNTS_BASE,
            data={
                "refresh_token": ZOHO_REFRESH_TOKEN,
                "client_id": ZOHO_CLIENT_ID,
                "client_secret": ZOHO_CLIENT_SECRET,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        payload = response.json()
        if "access_token" not in payload:
            raise RuntimeError(f"Zoho token refresh failed: {payload}")
        _access_token = payload["access_token"]
        _token_expires_at = time.time() + int(payload.get("expires_in", 3600))
        return _access_token


async def _zoho_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    token = await _get_access_token()
    clean_path = path.lstrip("/")
    if clean_path.startswith("http://") or clean_path.startswith("https://"):
        raise ValueError("Only relative Zoho Books API paths are allowed")
    url = f"{API_BASE}/{clean_path}"
    q = dict(params or {})
    q.setdefault("organization_id", ZOHO_ORG_ID)
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(
            url,
            params=q,
            headers={"Authorization": f"Zoho-oauthtoken {token}"},
        )
        response.raise_for_status()
        return response.json()


async def _paged_zoho_get(path: str, params: dict[str, Any] | None = None, per_page: int = 200) -> list[dict[str, Any]]:
    """Fetch all pages from a standard Zoho Books list endpoint."""
    rows: list[dict[str, Any]] = []
    page = 1
    base_params = dict(params or {})
    while True:
        q = dict(base_params)
        q["page"] = page
        q["per_page"] = per_page
        payload = await _zoho_get(path, q)

        # Find the first top-level list field (e.g. invoices, creditnotes).
        batch: list[dict[str, Any]] = []
        for value in payload.values():
            if isinstance(value, list):
                batch = value
                break
        rows.extend(batch)

        page_context = payload.get("page_context") or {}
        if not page_context.get("has_more_page"):
            break
        page += 1
    return rows


async def _get_many_details(path_prefix: str, ids: list[str], concurrency: int = 3) -> list[dict[str, Any]]:
    """Fetch record details with throttling and automatic retry for Zoho 429 rate limits."""
    token = await _get_access_token()
    semaphore = asyncio.Semaphore(max(1, min(concurrency, 5)))

    async with httpx.AsyncClient(timeout=90) as client:
        async def fetch(record_id: str) -> dict[str, Any] | None:
            async with semaphore:
                url = f"{API_BASE}/{path_prefix}/{record_id}"

                for attempt in range(6):
                    try:
                        response = await client.get(
                            url,
                            params={"organization_id": ZOHO_ORG_ID},
                            headers={"Authorization": f"Zoho-oauthtoken {token}"},
                        )

                        if response.status_code == 429:
                            retry_after = response.headers.get("Retry-After")
                            try:
                                wait_seconds = float(retry_after) if retry_after else min(2 ** attempt, 30)
                            except ValueError:
                                wait_seconds = min(2 ** attempt, 30)

                            await asyncio.sleep(max(wait_seconds, 1))
                            continue

                        response.raise_for_status()
                        return response.json()

                    except httpx.HTTPStatusError:
                        return None
                    except (httpx.TimeoutException, httpx.NetworkError):
                        if attempt >= 5:
                            return None
                        await asyncio.sleep(min(2 ** attempt, 15))
                    except Exception:
                        return None

                return None

        results: list[dict[str, Any] | None] = []
        batch_size = 25

        for start in range(0, len(ids), batch_size):
            batch_ids = ids[start:start + batch_size]
            batch_results = await asyncio.gather(*(fetch(record_id) for record_id in batch_ids))
            results.extend(batch_results)

            # Small pause between batches to avoid bursting the Zoho Books API.
            if start + batch_size < len(ids):
                await asyncio.sleep(2)

        return results


@mcp.tool()
async def health() -> dict[str, Any]:
    """Check whether the server has the required Zoho configuration."""
    return {
        "ok": True,
        "server": SERVER_NAME,
        "zoho_dc": ZOHO_DC,
        "organization_id_configured": bool(ZOHO_ORG_ID),
    }


@mcp.tool()
async def list_organizations() -> dict[str, Any]:
    """List Zoho Books organizations accessible to the configured Zoho account."""
    token = await _get_access_token()
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{API_BASE}/organizations",
            headers={"Authorization": f"Zoho-oauthtoken {token}"},
        )
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def list_invoices(date_start: str | None = None, date_end: str | None = None, page: int = 1, per_page: int = 200) -> dict[str, Any]:
    """List invoices, optionally filtered by invoice date range (YYYY-MM-DD)."""
    params: dict[str, Any] = {"page": page, "per_page": per_page}
    if date_start:
        params["date_start"] = date_start
    if date_end:
        params["date_end"] = date_end
    return await _zoho_get("invoices", params)


@mcp.tool()
async def list_credit_notes(page: int = 1, per_page: int = 200, status: str | None = None) -> dict[str, Any]:
    """List credit notes. Filter by status when needed."""
    params: dict[str, Any] = {"page": page, "per_page": per_page}
    if status:
        params["status"] = status
    return await _zoho_get("creditnotes", params)


@mcp.tool()
async def list_customer_payments(page: int = 1, per_page: int = 200) -> dict[str, Any]:
    """List customer payments."""
    return await _zoho_get("customerpayments", {"page": page, "per_page": per_page})


@mcp.tool()
async def list_contacts(page: int = 1, per_page: int = 200, contact_type: str | None = None) -> dict[str, Any]:
    """List contacts/customers/vendors."""
    params: dict[str, Any] = {"page": page, "per_page": per_page}
    if contact_type:
        params["contact_type"] = contact_type
    return await _zoho_get("contacts", params)


@mcp.tool()
async def list_items(page: int = 1, per_page: int = 200, search_text: str | None = None) -> dict[str, Any]:
    """List Zoho Books items and current item metadata."""
    params: dict[str, Any] = {"page": page, "per_page": per_page}
    if search_text:
        params["search_text"] = search_text
    return await _zoho_get("items", params)


@mcp.tool()
async def list_sales_orders(page: int = 1, per_page: int = 200) -> dict[str, Any]:
    """List sales orders."""
    return await _zoho_get("salesorders", {"page": page, "per_page": per_page})


@mcp.tool()
async def list_sales_receipts(page: int = 1, per_page: int = 200, date_start: str | None = None, date_end: str | None = None) -> dict[str, Any]:
    """List sales receipts, optionally filtered by date range."""
    params: dict[str, Any] = {"page": page, "per_page": per_page}
    if date_start:
        params["date_start"] = date_start
    if date_end:
        params["date_end"] = date_end
    return await _zoho_get("salesreceipts", params)


@mcp.tool()
async def sales_by_item(
    date_start: str,
    date_end: str,
    top_n: int = 25,
    sort_by: str = "net_quantity",
    include_credit_notes: bool = True,
) -> dict[str, Any]:
    """
    Fast Zoho Books Sales by Item report.

    Uses Zoho's native Sales by Item report endpoint, so it does NOT fetch
    hundreds/thousands of invoices one-by-one. Suitable for month, year,
    and Top-100 SKU queries.

    sort_by: net_quantity, net_sales, gross_quantity, gross_sales

    Note: Zoho's native Sales by Item report is used as the source of truth.
    The report's quantity_sold and amount values are returned as the net report
    values for the selected period. include_credit_notes is retained for
    backward compatibility but the native report determines the final figures.
    """
    if not date_start or not date_end:
        raise ValueError("date_start and date_end are required in YYYY-MM-DD format")

    allowed_sort = {"net_quantity", "net_sales", "gross_quantity", "gross_sales"}
    if sort_by not in allowed_sort:
        raise ValueError(f"sort_by must be one of: {', '.join(sorted(allowed_sort))}")

    top_n = max(1, min(int(top_n), 500))

    # Zoho Books native Sales by Item report endpoint.
    payload = await _zoho_get(
        "reports/salesbyitem",
        {
            "from_date": date_start,
            "to_date": date_end,
        },
    )

    sales = payload.get("sales") or []
    rows: list[dict[str, Any]] = []

    for entry in sales:
        item_meta = entry.get("item") or {}
        quantity = float(entry.get("quantity_sold") or 0)
        amount = float(entry.get("amount") or 0)

        rows.append(
            {
                "sku": str(item_meta.get("sku") or "").strip(),
                "item_id": str(entry.get("item_id") or "").strip(),
                "item_name": str(entry.get("item_name") or "").strip(),
                "category_name": str(entry.get("category_name") or "").strip(),
                "group_name": str(entry.get("group_name") or "").strip(),
                "unit": str(entry.get("unit") or "").strip(),
                "gross_quantity": round(quantity, 3),
                "gross_sales": round(amount, 2),
                "return_quantity": 0.0,
                "return_value": 0.0,
                "net_quantity": round(quantity, 3),
                "net_sales": round(amount, 2),
                "average_price": round(float(entry.get("average_price") or 0), 2),
            }
        )

    sort_key = {
        "net_quantity": "net_quantity",
        "net_sales": "net_sales",
        "gross_quantity": "gross_quantity",
        "gross_sales": "gross_sales",
    }[sort_by]

    rows.sort(key=lambda x: float(x.get(sort_key) or 0), reverse=True)

    return {
        "date_start": date_start,
        "date_end": date_end,
        "source": "Zoho Books native Sales by Item report",
        "sort_by": sort_by,
        "include_credit_notes_requested": include_credit_notes,
        "items_count": len(rows),
        "items": rows[:top_n],
    }


@mcp.tool()
async def zoho_books_read(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Advanced read-only Zoho Books GET tool for endpoints not yet wrapped above.
    Pass a relative Books v3 path such as 'reports/...' or 'items'.
    This tool never sends POST/PUT/PATCH/DELETE requests.
    """
    if not path or path.startswith("/"):
        path = path.lstrip("/")
    blocked = ("settings/preferences",)
    if any(path.startswith(x) for x in blocked):
        raise ValueError("This endpoint is blocked in the read-only connector")
    return await _zoho_get(path, params)


security = TransportSecuritySettings(
    allowed_hosts=[ALLOWED_HOST, f"{ALLOWED_HOST}:*", "localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"],
    allowed_origins=[f"https://{ALLOWED_HOST}", f"http://{ALLOWED_HOST}", "http://localhost", "http://127.0.0.1"],
)

app = mcp.streamable_http_app(
    transport_security=security,
    json_response=True,
)
