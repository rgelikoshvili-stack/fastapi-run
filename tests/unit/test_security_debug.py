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
        request = MagicMock()
        request.url.path = "/api/reports"
        request.method = "GET"
        request.query_params = {"token": "fake-jwt-token"}
        request.state = SimpleNamespace(authenticated=False)

        async def call_next(r):
            return MagicMock(status_code=200)

        response = await mod.rbac_middleware(request, call_next)
        return response

    resp = asyncio.run(_run())
    assert resp.status_code == 401, (
        f"Expected 401 for non-download path with ?token=, got {resp.status_code}"
    )


# ── P2-2: /metrics must be protected (not in public prefixes) ─────────────────

def test_metrics_not_in_rbac_public_prefixes():
    """/metrics must not appear in rbac_middleware public_prefixes — requires auth."""
    import inspect
    import app.api.middleware.rbac_middleware as mod
    src = inspect.getsource(mod.rbac_middleware)
    # Find the public_prefixes tuple inside the function
    idx = src.index("public_prefixes")
    # Grab the block up to the closing paren of the tuple
    block_end = src.index(")", idx)
    block = src[idx:block_end]
    assert '"/metrics"' not in block and "'metrics'" not in block, (
        "/metrics is still in rbac_middleware public_prefixes — it is publicly accessible"
    )


def test_metrics_requires_dashboard_admin_permission():
    """/metrics must be mapped to dashboard:admin in PERMISSION_MAP."""
    from app.api.policy.permission_map import PERMISSION_MAP
    metrics_entries = [(m, p, perm) for m, p, perm in PERMISSION_MAP if p == "/metrics"]
    assert metrics_entries, "/metrics has no entry in PERMISSION_MAP"
    assert all(perm == "dashboard:admin" for _, _, perm in metrics_entries), (
        f"/metrics permission should be dashboard:admin, got {metrics_entries}"
    )


def test_metrics_unauthenticated_gets_401():
    """/metrics with no token must return 401 from rbac_middleware."""
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    import app.api.middleware.rbac_middleware as mod

    async def _run():
        request = MagicMock()
        request.url.path = "/metrics"
        request.method = "GET"
        request.query_params = {}
        request.state = SimpleNamespace(authenticated=False)

        async def call_next(r):
            return MagicMock(status_code=200)

        return await mod.rbac_middleware(request, call_next)

    resp = asyncio.run(_run())
    assert resp.status_code == 401, (
        f"Expected 401 for unauthenticated /metrics, got {resp.status_code}"
    )


# ── P2-3: CORS must use explicit allowlists ────────────────────────────────────

def test_cors_methods_not_wildcard():
    """CORSMiddleware must not use allow_methods=['*']."""
    import inspect
    import main as app_main
    src = inspect.getsource(app_main)
    assert 'allow_methods=["*"]' not in src and "allow_methods=['*']" not in src, (
        "CORS allow_methods is still wildcard"
    )


def test_cors_headers_not_wildcard():
    """CORSMiddleware must not use allow_headers=['*']."""
    import inspect
    import main as app_main
    src = inspect.getsource(app_main)
    assert 'allow_headers=["*"]' not in src and "allow_headers=['*']" not in src, (
        "CORS allow_headers is still wildcard"
    )


def test_cors_required_headers_present():
    """CORS allowlist must include Authorization and X-Tenant-ID."""
    import inspect
    import main as app_main
    src = inspect.getsource(app_main)
    assert '"Authorization"' in src or "'Authorization'" in src
    assert '"X-Tenant-ID"' in src or "'X-Tenant-ID'" in src
