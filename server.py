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
