"""tests/unit/test_phase8b_admin_dashboard.py — Phase 8b: Admin Dashboard.

Covers:
  1. get_system_health — DB ping + env-based connector modes
  2. get_tenant_summary (mocked DB)
  3. get_tenant_detail (mocked DB)
  4. adjust_tenant_plan — valid + invalid plan + not found
  5. Routes: importable, prefix, permissions
  6. Permission map and registry
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _ctx(rows=None, fetchrow=None, fetchval_side=None):
    conn = AsyncMock()
    conn.fetch    = AsyncMock(return_value=rows or [])
    conn.fetchrow = AsyncMock(return_value=fetchrow)
    if fetchval_side:
        conn.fetchval = AsyncMock(side_effect=fetchval_side)
    else:
        conn.fetchval = AsyncMock(return_value=0)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__  = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# 1. get_system_health
# ---------------------------------------------------------------------------
class TestGetSystemHealth:
    @pytest.mark.asyncio
    async def test_db_ok(self):
        from app.api.services.admin_dashboard_service import get_system_health
        with patch("app.api.services.admin_dashboard_service.get_conn",
                   return_value=_ctx(fetchval_side=[1])):
            result = await get_system_health()
        assert result["database"]["ok"] is True
        assert result["all_ok"] is True

    @pytest.mark.asyncio
    async def test_db_fail(self):
        from app.api.services.admin_dashboard_service import get_system_health
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))
        mock_ctx.__aexit__  = AsyncMock(return_value=False)
        with patch("app.api.services.admin_dashboard_service.get_conn", return_value=mock_ctx):
            result = await get_system_health()
        assert result["database"]["ok"] is False
        assert result["all_ok"] is False

    @pytest.mark.asyncio
    async def test_connector_modes_in_result(self):
        from app.api.services.admin_dashboard_service import get_system_health
        with patch("app.api.services.admin_dashboard_service.get_conn",
                   return_value=_ctx(fetchval_side=[1])):
            result = await get_system_health()
        assert "connectors" in result
        assert "balance" in result["connectors"]
        assert "1c" in result["connectors"]
        assert "oris" in result["connectors"]
        assert "fina" in result["connectors"]
        assert "apex" in result["connectors"]

    @pytest.mark.asyncio
    async def test_redis_configured_field(self):
        from app.api.services.admin_dashboard_service import get_system_health
        with patch("app.api.services.admin_dashboard_service.get_conn",
                   return_value=_ctx(fetchval_side=[1])):
            result = await get_system_health()
        assert "redis_configured" in result
        assert isinstance(result["redis_configured"], bool)


# ---------------------------------------------------------------------------
# 2. get_tenant_summary
# ---------------------------------------------------------------------------
class TestGetTenantSummary:
    @pytest.mark.asyncio
    async def test_returns_tenant_list(self):
        from app.api.services.admin_dashboard_service import get_tenant_summary
        tenant_row = {"tenant_id": "t1", "name": "Test", "plan": "FREE",
                      "is_active": True, "status": "active", "created_at": "2026-01-01"}
        plan_row   = MagicMock()
        plan_row.__getitem__ = lambda s, k: {"plan": "FREE", "cnt": 1}[k]
        plan_row.keys = lambda: ["plan", "cnt"]

        conn = AsyncMock()
        conn.fetch    = AsyncMock(side_effect=[[tenant_row], [plan_row]])
        conn.fetchval = AsyncMock(return_value=10)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__  = AsyncMock(return_value=False)

        with patch("app.api.services.admin_dashboard_service.get_conn", return_value=ctx), \
             patch("app.api.services.admin_dashboard_service.get_usage",
                   new=AsyncMock(return_value={"draft_count": 5, "user_count": 2})):
            result = await get_tenant_summary()

        assert "tenants" in result
        assert result["total_drafts"] == 10


# ---------------------------------------------------------------------------
# 3. get_tenant_detail
# ---------------------------------------------------------------------------
class TestGetTenantDetail:
    @pytest.mark.asyncio
    async def test_raises_if_not_found(self):
        from app.api.services.admin_dashboard_service import get_tenant_detail
        with patch("app.api.services.admin_dashboard_service.get_conn",
                   return_value=_ctx(fetchrow=None)):
            with pytest.raises(ValueError, match="TENANT_NOT_FOUND"):
                await get_tenant_detail("unknown")

    @pytest.mark.asyncio
    async def test_returns_detail(self):
        from app.api.services.admin_dashboard_service import get_tenant_detail
        tenant = {"tenant_id": "t1", "name": "Test", "plan": "STARTER",
                  "is_active": True, "status": "active", "created_at": "2026-01-01",
                  "updated_at": "2026-01-01", "slug": "t1"}
        stats  = {"total": 20, "posted": 15, "drafted": 5, "rejected": 0, "posted_amount": 5000}
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=[tenant, stats])
        conn.fetchval = AsyncMock(return_value=8)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__  = AsyncMock(return_value=False)
        with patch("app.api.services.admin_dashboard_service.get_conn", return_value=ctx), \
             patch("app.api.services.admin_dashboard_service.get_usage",
                   new=AsyncMock(return_value={"draft_count": 20, "user_count": 3})):
            result = await get_tenant_detail("t1")
        assert result["plan"] == "STARTER"
        assert result["drafts"]["total"] == 20


# ---------------------------------------------------------------------------
# 4. adjust_tenant_plan
# ---------------------------------------------------------------------------
class TestAdjustTenantPlan:
    @pytest.mark.asyncio
    async def test_valid_plan_change(self):
        from app.api.services.admin_dashboard_service import adjust_tenant_plan
        row = {"tenant_id": "t1", "name": "Test", "plan": "PROFESSIONAL", "updated_at": "2026-01-01"}
        with patch("app.api.services.admin_dashboard_service.get_conn",
                   return_value=_ctx(fetchrow=row)):
            result = await adjust_tenant_plan("t1", "PROFESSIONAL", "admin")
        assert result["plan"] == "PROFESSIONAL"
        assert result["adjusted_by"] == "admin"

    @pytest.mark.asyncio
    async def test_invalid_plan_raises(self):
        from app.api.services.admin_dashboard_service import adjust_tenant_plan
        with pytest.raises(ValueError, match="INVALID_PLAN"):
            await adjust_tenant_plan("t1", "GOLD", "admin")

    @pytest.mark.asyncio
    async def test_tenant_not_found_raises(self):
        from app.api.services.admin_dashboard_service import adjust_tenant_plan
        with patch("app.api.services.admin_dashboard_service.get_conn",
                   return_value=_ctx(fetchrow=None)):
            with pytest.raises(ValueError, match="TENANT_NOT_FOUND"):
                await adjust_tenant_plan("unknown", "FREE", "admin")


# ---------------------------------------------------------------------------
# 5. Routes
# ---------------------------------------------------------------------------
class TestAdminRoutes:
    def test_router_importable(self):
        import importlib
        mod = importlib.import_module("app.api.routes_admin_dashboard")
        assert hasattr(mod, "router")

    def test_router_prefix(self):
        from app.api.routes_admin_dashboard import router
        assert router.prefix == "/admin"

    def test_all_routes_require_tenants_manage(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_admin_dashboard.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name in (
                "system_health", "tenant_summary", "tenant_detail", "set_plan"
            ):
                assert "tenants:manage" in ast.unparse(node)


# ---------------------------------------------------------------------------
# 6. Permission map and registry
# ---------------------------------------------------------------------------
class TestAdminRegistration:
    def test_permission_map_has_admin(self):
        import pathlib
        src = pathlib.Path("app/api/policy/permission_map.py").read_text(encoding="utf-8")
        assert '"/admin"' in src or "'/admin'" in src

    def test_get_admin_maps_tenants_manage(self):
        from app.api.policy.permission_map import match_permission
        assert match_permission("GET", "/admin/health") == "tenants:manage"

    def test_router_registered(self):
        import pathlib
        src = pathlib.Path("app/core/router_registry.py").read_text(encoding="utf-8")
        assert "routes_admin_dashboard" in src

    def test_service_importable(self):
        import importlib
        mod = importlib.import_module("app.api.services.admin_dashboard_service")
        assert hasattr(mod, "get_system_health")
        assert hasattr(mod, "get_tenant_summary")
        assert hasattr(mod, "get_tenant_detail")
        assert hasattr(mod, "adjust_tenant_plan")
