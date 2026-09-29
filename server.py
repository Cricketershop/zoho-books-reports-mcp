import os
import time
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
