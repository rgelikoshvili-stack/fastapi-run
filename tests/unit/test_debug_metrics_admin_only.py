"""tests/unit/test_debug_metrics_admin_only.py

Access-control tests for /debug/* and /metrics.
Verifies: unauthenticated → 401, non-admin → 403, admin allowed.
No DB, no network, no real app imports.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _req(role="admin", authenticated=True):
    return SimpleNamespace(
        state=SimpleNamespace(authenticated=authenticated, role=role, tenant_id="t1")
    )


def _unauthed():
    return SimpleNamespace(
        state=SimpleNamespace(authenticated=False, role=None, tenant_id=None)
    )


NON_ADMIN_ROLES = ("viewer", "reviewer", "accountant", "cfo", "ai_supervisor")


# ── /debug/openai ─────────────────────────────────────────────────────────────

class TestDebugOpenai:
    def test_admin_allowed(self, monkeypatch):
        from app.api.routes_debug import debug_openai
        monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
        result = debug_openai(_req("admin"))
        assert result["ok"] is True

    def test_non_admin_blocked(self):
        from app.api.routes_debug import debug_openai
        for role in NON_ADMIN_ROLES:
            with pytest.raises(HTTPException) as exc:
                debug_openai(_req(role))
            assert exc.value.status_code == 403, f"Expected 403 for {role}"

    def test_unauthenticated_blocked(self):
        from app.api.routes_debug import debug_openai
        with pytest.raises(HTTPException) as exc:
            debug_openai(_unauthed())
        assert exc.value.status_code == 401


# ── /debug/balance-ping ───────────────────────────────────────────────────────

class TestDebugBalancePing:
    def test_admin_allowed(self, monkeypatch):
        from app.api.routes_debug import debug_balance_ping
        monkeypatch.setenv("BALANCE_API_URL", "https://balance.example")
        monkeypatch.setenv("BALANCE_API_KEY", "fake-key")
        monkeypatch.setenv("BALANCE_COMPANY_ID", "c123")
        result = debug_balance_ping(_req("admin"))
        assert result["ok"] is True

    def test_non_admin_blocked(self):
        from app.api.routes_debug import debug_balance_ping
        for role in NON_ADMIN_ROLES:
            with pytest.raises(HTTPException) as exc:
                debug_balance_ping(_req(role))
            assert exc.value.status_code == 403, f"Expected 403 for {role}"

    def test_unauthenticated_blocked(self):
        from app.api.routes_debug import debug_balance_ping
        with pytest.raises(HTTPException) as exc:
            debug_balance_ping(_unauthed())
        assert exc.value.status_code == 401


# ── /debug/ai-routing ─────────────────────────────────────────────────────────

class TestDebugAiRouting:
    def test_admin_allowed(self):
        from app.api.routes_debug import debug_ai_routing
        result = debug_ai_routing(_req("admin"))
        assert result["ok"] is True

    def test_non_admin_blocked(self):
        from app.api.routes_debug import debug_ai_routing
        for role in NON_ADMIN_ROLES:
            with pytest.raises(HTTPException) as exc:
                debug_ai_routing(_req(role))
            assert exc.value.status_code == 403, f"Expected 403 for {role}"

    def test_unauthenticated_blocked(self):
        from app.api.routes_debug import debug_ai_routing
        with pytest.raises(HTTPException) as exc:
            debug_ai_routing(_unauthed())
        assert exc.value.status_code == 401


# ── /debug/llm-ping ───────────────────────────────────────────────────────────

class TestDebugLlmPing:
    def test_admin_allowed(self):
        from app.api.routes_debug import debug_llm_ping
        with patch("app.api.routes_debug._ping_anthropic",
                   AsyncMock(return_value={"ok": False, "model": "m", "error": "NOT_CONFIGURED"})), \
             patch("app.api.routes_debug._ping_openrouter",
                   AsyncMock(return_value={"ok": False, "model": "m", "error": "NOT_CONFIGURED"})):
            result = asyncio.run(debug_llm_ping(_req("admin")))
        assert "anthropic" in result

    def test_non_admin_blocked(self):
        from app.api.routes_debug import debug_llm_ping
        for role in NON_ADMIN_ROLES:
            with pytest.raises(HTTPException) as exc:
                asyncio.run(debug_llm_ping(_req(role)))
            assert exc.value.status_code == 403, f"Expected 403 for {role}"

    def test_unauthenticated_blocked(self):
        from app.api.routes_debug import debug_llm_ping
        with pytest.raises(HTTPException) as exc:
            asyncio.run(debug_llm_ping(_unauthed()))
        assert exc.value.status_code == 401


# ── /debug/kb-files ───────────────────────────────────────────────────────────

class TestDebugKbFiles:
    def test_admin_allowed(self):
        from app.api.routes_debug import debug_kb_files
        result = asyncio.run(debug_kb_files(_req("admin")))
        assert isinstance(result, dict)

    def test_non_admin_blocked(self):
        from app.api.routes_debug import debug_kb_files
        for role in NON_ADMIN_ROLES:
            with pytest.raises(HTTPException) as exc:
                asyncio.run(debug_kb_files(_req(role)))
            assert exc.value.status_code == 403, f"Expected 403 for {role}"

    def test_unauthenticated_blocked(self):
        from app.api.routes_debug import debug_kb_files
        with pytest.raises(HTTPException) as exc:
            asyncio.run(debug_kb_files(_unauthed()))
        assert exc.value.status_code == 401


# ── /metrics via RBAC middleware ──────────────────────────────────────────────

class TestMetricsMiddleware:
    def test_metrics_unauthenticated_gets_401(self):
        import asyncio as _asyncio
        import app.api.middleware.rbac_middleware as mod

        async def _run():
            request = MagicMock()
            request.url.path = "/metrics"
            request.method = "GET"
            request.query_params = {}
            request.state = SimpleNamespace(authenticated=False)
            return await mod.rbac_middleware(request, AsyncMock(return_value=MagicMock(status_code=200)))

        resp = _asyncio.run(_run())
        assert resp.status_code == 401

    def test_metrics_viewer_gets_403(self):
        import asyncio as _asyncio
        import app.api.middleware.rbac_middleware as mod

        async def _run():
            request = MagicMock()
            request.url.path = "/metrics"
            request.method = "GET"
            request.query_params = {}
            request.state = SimpleNamespace(authenticated=True, role="viewer", tenant_id="t1")
            return await mod.rbac_middleware(request, AsyncMock(return_value=MagicMock(status_code=200)))

        resp = _asyncio.run(_run())
        assert resp.status_code == 403

    def test_metrics_accountant_gets_403(self):
        import asyncio as _asyncio
        import app.api.middleware.rbac_middleware as mod

        async def _run():
            request = MagicMock()
            request.url.path = "/metrics"
            request.method = "GET"
            request.query_params = {}
            request.state = SimpleNamespace(authenticated=True, role="accountant", tenant_id="t1")
            return await mod.rbac_middleware(request, AsyncMock(return_value=MagicMock(status_code=200)))

        resp = _asyncio.run(_run())
        assert resp.status_code == 403

    def test_metrics_admin_passes_middleware(self):
        import asyncio as _asyncio
        import app.api.middleware.rbac_middleware as mod

        async def _run():
            request = MagicMock()
            request.url.path = "/metrics"
            request.method = "GET"
            request.query_params = {}
            request.state = SimpleNamespace(authenticated=True, role="admin", tenant_id="t1")
            return await mod.rbac_middleware(request, AsyncMock(return_value=MagicMock(status_code=200)))

        resp = _asyncio.run(_run())
        assert resp.status_code == 200


# ── /debug/* via RBAC middleware ──────────────────────────────────────────────

class TestDebugMiddlewareProtection:
    def _run_middleware(self, path, role=None, authenticated=True):
        import asyncio as _asyncio
        import app.api.middleware.rbac_middleware as mod

        async def _inner():
            request = MagicMock()
            request.url.path = path
            request.method = "GET"
            request.query_params = {}
            request.state = SimpleNamespace(
                authenticated=authenticated,
                role=role,
                tenant_id="t1",
            )
            return await mod.rbac_middleware(request, AsyncMock(return_value=MagicMock(status_code=200)))

        return _asyncio.run(_inner())

    def test_debug_log_unauthenticated_401(self):
        resp = self._run_middleware("/debug/log", authenticated=False)
        assert resp.status_code == 401

    def test_debug_ai_routing_unauthenticated_401(self):
        resp = self._run_middleware("/debug/ai-routing", authenticated=False)
        assert resp.status_code == 401

    def test_debug_llm_ping_unauthenticated_401(self):
        resp = self._run_middleware("/debug/llm-ping", authenticated=False)
        assert resp.status_code == 401

    def test_debug_openai_unauthenticated_401(self):
        resp = self._run_middleware("/debug/openai", authenticated=False)
        assert resp.status_code == 401

    def test_debug_viewer_gets_403(self):
        resp = self._run_middleware("/debug/openai", role="viewer")
        assert resp.status_code == 403

    def test_debug_accountant_gets_403(self):
        resp = self._run_middleware("/debug/ai-routing", role="accountant")
        assert resp.status_code == 403

    def test_debug_admin_passes_middleware(self):
        resp = self._run_middleware("/debug/openai", role="admin")
        assert resp.status_code == 200


# ── Permission map entries ─────────────────────────────────────────────────────

class TestPermissionMapEntries:
    def test_debug_in_permission_map(self):
        from app.api.policy.permission_map import PERMISSION_MAP
        debug_entries = [(m, p, perm) for m, p, perm in PERMISSION_MAP if p == "/debug"]
        assert debug_entries, "/debug has no entry in PERMISSION_MAP"

    def test_debug_uses_tenants_manage(self):
        from app.api.policy.permission_map import PERMISSION_MAP
        debug_entries = [(m, p, perm) for m, p, perm in PERMISSION_MAP if p == "/debug"]
        assert all(perm == "tenants:manage" for _, _, perm in debug_entries), (
            f"/debug should require tenants:manage, got: {debug_entries}"
        )

    def test_metrics_uses_dashboard_admin(self):
        from app.api.policy.permission_map import PERMISSION_MAP
        metrics_entries = [(m, p, perm) for m, p, perm in PERMISSION_MAP if p == "/metrics"]
        assert metrics_entries, "/metrics has no entry in PERMISSION_MAP"
        assert all(perm == "dashboard:admin" for _, _, perm in metrics_entries), (
            f"/metrics should require dashboard:admin, got: {metrics_entries}"
        )

    def test_debug_ai_routing_not_in_public_prefixes(self):
        import inspect
        import app.api.middleware.rbac_middleware as mod
        src = inspect.getsource(mod.rbac_middleware)
        idx = src.index("public_prefixes")
        block_end = src.index(")", idx)
        block = src[idx:block_end]
        assert "/debug/ai-routing" not in block, (
            "/debug/ai-routing must not be in public_prefixes — it requires authentication"
        )

    def test_no_debug_prefix_in_public_prefixes(self):
        import inspect
        import app.api.middleware.rbac_middleware as mod
        src = inspect.getsource(mod.rbac_middleware)
        idx = src.index("public_prefixes")
        block_end = src.index(")", idx)
        block = src[idx:block_end]
        assert '"/debug' not in block and "''/debug" not in block, (
            "No /debug paths should appear in public_prefixes"
        )


# ── Via TestClient (end-to-end without auth) ──────────────────────────────────

class TestViaTestClient:
    def test_metrics_no_token_401_or_403(self):
        from fastapi.testclient import TestClient
        from main import app
        resp = TestClient(app).get("/metrics")
        assert resp.status_code in (401, 403)

    def test_debug_openai_no_token_401_or_403(self):
        from fastapi.testclient import TestClient
        from main import app
        resp = TestClient(app).get("/debug/openai")
        assert resp.status_code in (401, 403)

    def test_debug_ai_routing_no_token_401_or_403(self):
        from fastapi.testclient import TestClient
        from main import app
        resp = TestClient(app).get("/debug/ai-routing")
        assert resp.status_code in (401, 403)

    def test_debug_balance_ping_no_token_401_or_403(self):
        from fastapi.testclient import TestClient
        from main import app
        resp = TestClient(app).get("/debug/balance-ping")
        assert resp.status_code in (401, 403)

    def test_health_remains_public(self):
        from fastapi.testclient import TestClient
        from main import app
        resp = TestClient(app).get("/health")
        assert resp.status_code == 200
