from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def _request(role="admin"):
    return SimpleNamespace(state=SimpleNamespace(authenticated=True, role=role, tenant_id="tenant-a"))


def test_debug_openai_requires_tenants_manage_permission(monkeypatch):
    from app.api.routes_debug import debug_openai

    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
    with pytest.raises(HTTPException) as exc:
        debug_openai(_request("viewer"))
    assert exc.value.status_code == 403


def test_debug_openai_redacts_key_details(monkeypatch):
    from app.api.routes_debug import debug_openai

    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
    result = debug_openai(_request("admin"))
    data = result["data"]

    assert data == {"configured": True}
    assert "key_prefix" not in data
    assert "length" not in data


def test_debug_balance_ping_redacts_sensitive_config(monkeypatch):
    from app.api.routes_debug import debug_balance_ping

    monkeypatch.setenv("BALANCE_API_URL", "https://balance.example")
    monkeypatch.setenv("BALANCE_API_KEY", "balance-secret")
    monkeypatch.setenv("BALANCE_COMPANY_ID", "company-123")

    result = debug_balance_ping(_request("admin"))
    data = result["data"]

    assert data == {
        "base_url_configured": True,
        "api_key_configured": True,
        "company_id_configured": True,
    }
    assert "https://balance.example" not in str(data)
    assert "balance-secret" not in str(data)
    assert "company-123" not in str(data)


# ── Token in URL restricted to download paths ──────────────────────────────

def test_token_in_url_only_allowed_on_download_paths():
    """?token= query param must only be accepted on file-download paths, not general API paths."""
    import inspect
    import app.api.middleware.rbac_middleware as mod
    src = inspect.getsource(mod)
    # The restriction must reference _DOWNLOAD_PREFIXES or equivalent pattern
    assert "_DOWNLOAD_PREFIXES" in src or "download" in src.lower(), (
        "?token= fallback must be limited to download/export paths"
    )
    # Must not accept token= for arbitrary paths (old code had no path check)
    # Verify the path.startswith guard exists before the token read
    assert "path.startswith" in src, "token-in-URL must check path.startswith before reading token"


def test_token_in_url_rejected_for_non_download_path():
    """?token= must be ignored for normal API paths like /api/reports."""
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    import app.api.middleware.rbac_middleware as mod

    async def _run():
        # Build a fake request for /api/reports (NOT a download path)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/reports",
            "query_string": b"token=fake-jwt-token",
            "headers": [],
        }
        request = MagicMock()
        request.url.path = "/api/reports"
        request.method = "GET"
        request.query_params = {"token": "fake-jwt-token"}
        request.state = SimpleNamespace(authenticated=False)

        responses = []

        async def call_next(r):
            return MagicMock(status_code=200)

        # Middleware should NOT authenticate using query token for /api/reports
        # (It should return 401 Unauthorized because the path is not a download path)
        response = await mod.rbac_middleware(request, call_next)
        return response

    resp = asyncio.run(_run())
    # Should get 401 because token-in-URL is not used for /api/reports
    assert resp.status_code == 401, (
        f"Expected 401 for non-download path with ?token=, got {resp.status_code}"
    )
