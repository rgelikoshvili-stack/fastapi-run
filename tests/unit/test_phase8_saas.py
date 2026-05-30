"""tests/unit/test_phase8_saas.py — Phase 8: SaaS Layer.

Covers:
  1. Plan definitions — FREE/STARTER/PROFESSIONAL/ENTERPRISE
  2. get_plan_limits + is_feature_allowed + is_connector_allowed
  3. get_usage (mocked DB)
  4. check_quota — within / exceeded
  5. get_onboarding_status (mocked DB)
  6. upgrade_plan_request — valid + invalid plan
  7. Routes: importable, prefix, permissions
  8. Permission map and registry
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ctx(fetchval_side=None, fetchrow=None, rows=None):
    conn = AsyncMock()
    if fetchval_side:
        conn.fetchval = AsyncMock(side_effect=fetchval_side)
    else:
        conn.fetchval = AsyncMock(return_value=0)
    conn.fetchrow = AsyncMock(return_value=fetchrow)
    conn.fetch    = AsyncMock(return_value=rows or [])
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__  = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# 1. Plan definitions
# ---------------------------------------------------------------------------
class TestPlanDefinitions:
    def test_all_four_plans_exist(self):
        from app.api.services.saas_service import PLANS
        assert {"FREE", "STARTER", "PROFESSIONAL", "ENTERPRISE"} == set(PLANS.keys())

    def test_free_plan_has_50_drafts_limit(self):
        from app.api.services.saas_service import PLANS
        assert PLANS["FREE"]["max_drafts_per_month"] == 50

    def test_enterprise_unlimited(self):
        from app.api.services.saas_service import PLANS
        assert PLANS["ENTERPRISE"]["max_drafts_per_month"] == -1

    def test_starter_allows_balance_connector(self):
        from app.api.services.saas_service import PLANS
        assert "balance" in PLANS["STARTER"]["connectors_allowed"]

    def test_free_no_connectors(self):
        from app.api.services.saas_service import PLANS
        assert PLANS["FREE"]["connectors_allowed"] == []


# ---------------------------------------------------------------------------
# 2. get_plan_limits + feature/connector checks
# ---------------------------------------------------------------------------
class TestPlanChecks:
    def test_get_plan_limits_known_plan(self):
        from app.api.services.saas_service import get_plan_limits
        limits = get_plan_limits("STARTER")
        assert limits["max_users"] == 5

    def test_get_plan_limits_unknown_falls_back_to_free(self):
        from app.api.services.saas_service import get_plan_limits
        limits = get_plan_limits("GOLD")
        assert limits["max_drafts_per_month"] == 50

    def test_is_feature_allowed_true(self):
        from app.api.services.saas_service import is_feature_allowed
        assert is_feature_allowed("PROFESSIONAL", "payroll") is True

    def test_is_feature_allowed_false(self):
        from app.api.services.saas_service import is_feature_allowed
        assert is_feature_allowed("FREE", "payroll") is False

    def test_enterprise_allows_all_features(self):
        from app.api.services.saas_service import is_feature_allowed
        assert is_feature_allowed("ENTERPRISE", "any_feature") is True

    def test_is_connector_allowed_true(self):
        from app.api.services.saas_service import is_connector_allowed
        assert is_connector_allowed("PROFESSIONAL", "1c") is True

    def test_is_connector_allowed_false(self):
        from app.api.services.saas_service import is_connector_allowed
        assert is_connector_allowed("FREE", "balance") is False


# ---------------------------------------------------------------------------
# 3. get_usage
# ---------------------------------------------------------------------------
class TestGetUsage:
    @pytest.mark.asyncio
    async def test_returns_draft_and_user_count(self):
        from app.api.services.saas_service import get_usage
        with patch("app.api.services.saas_service.get_conn",
                   return_value=_ctx(fetchval_side=[42, 3])):
            result = await get_usage("t1", "2026-01")
        assert result["draft_count"] == 42
        assert result["user_count"]  == 3
        assert result["month"] == "2026-01"


# ---------------------------------------------------------------------------
# 4. check_quota
# ---------------------------------------------------------------------------
class TestCheckQuota:
    @pytest.mark.asyncio
    async def test_within_quota_drafts(self):
        from app.api.services.saas_service import check_quota
        with patch("app.api.services.saas_service.get_tenant_plan",
                   new=AsyncMock(return_value="STARTER")), \
             patch("app.api.services.saas_service.get_usage",
                   new=AsyncMock(return_value={"draft_count": 100, "user_count": 2})):
            result = await check_quota("t1", "drafts")
        assert result["allowed"] is True
        assert result["limit"] == 500

    @pytest.mark.asyncio
    async def test_exceeded_quota_drafts(self):
        from app.api.services.saas_service import check_quota
        with patch("app.api.services.saas_service.get_tenant_plan",
                   new=AsyncMock(return_value="FREE")), \
             patch("app.api.services.saas_service.get_usage",
                   new=AsyncMock(return_value={"draft_count": 55, "user_count": 1})):
            result = await check_quota("t1", "drafts")
        assert result["allowed"] is False
        assert result["current"] == 55

    @pytest.mark.asyncio
    async def test_enterprise_always_allowed(self):
        from app.api.services.saas_service import check_quota
        with patch("app.api.services.saas_service.get_tenant_plan",
                   new=AsyncMock(return_value="ENTERPRISE")), \
             patch("app.api.services.saas_service.get_usage",
                   new=AsyncMock(return_value={"draft_count": 99999, "user_count": 500})):
            result = await check_quota("t1", "drafts")
        assert result["allowed"] is True
        assert result["limit"] == -1


# ---------------------------------------------------------------------------
# 5. get_onboarding_status
# ---------------------------------------------------------------------------
class TestGetOnboardingStatus:
    @pytest.mark.asyncio
    async def test_empty_tenant_zero_percent(self):
        from app.api.services.saas_service import get_onboarding_status
        with patch("app.api.services.saas_service.get_conn",
                   return_value=_ctx(fetchval_side=[None, 0, 0, 0])):
            result = await get_onboarding_status("t1")
        assert result["pct"] == 0
        assert result["onboarded"] is False

    @pytest.mark.asyncio
    async def test_partial_completion(self):
        from app.api.services.saas_service import get_onboarding_status
        with patch("app.api.services.saas_service.get_conn",
                   return_value=_ctx(fetchval_side=["123456789", 1, 1, 1])):
            result = await get_onboarding_status("t1")
        assert result["completed"] >= 3
        assert result["total"] == 5

    @pytest.mark.asyncio
    async def test_steps_have_required_fields(self):
        from app.api.services.saas_service import get_onboarding_status
        with patch("app.api.services.saas_service.get_conn",
                   return_value=_ctx(fetchval_side=[None, 0, 0, 0])):
            result = await get_onboarding_status("t1")
        for step in result["steps"]:
            assert "id" in step
            assert "name" in step
            assert "completed" in step


# ---------------------------------------------------------------------------
# 6. upgrade_plan_request
# ---------------------------------------------------------------------------
class TestUpgradePlanRequest:
    @pytest.mark.asyncio
    async def test_valid_upgrade(self):
        from app.api.services.saas_service import upgrade_plan_request
        with patch("app.api.services.saas_service.set_tenant_setting",
                   new=AsyncMock(return_value=True)):
            result = await upgrade_plan_request("t1", "PROFESSIONAL", "admin")
        assert result["requested_plan"] == "PROFESSIONAL"
        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_invalid_plan_raises(self):
        from app.api.services.saas_service import upgrade_plan_request
        with pytest.raises(ValueError, match="INVALID_PLAN"):
            await upgrade_plan_request("t1", "GOLD", "admin")


# ---------------------------------------------------------------------------
# 7. Routes
# ---------------------------------------------------------------------------
class TestSaasRoutes:
    def test_router_importable(self):
        import importlib
        mod = importlib.import_module("app.api.routes_saas")
        assert hasattr(mod, "router")

    def test_router_prefix(self):
        from app.api.routes_saas import router
        assert router.prefix == "/saas"

    def test_plans_endpoint_exists(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_saas.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        names = [n.name for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]
        assert "list_plans" in names

    def test_upgrade_requires_tenants_manage(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_saas.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "upgrade":
                assert "tenants:manage" in ast.unparse(node)
                return
        pytest.fail("upgrade not found")


# ---------------------------------------------------------------------------
# 8. Permission map and registry
# ---------------------------------------------------------------------------
class TestSaasRegistration:
    def test_permission_map_has_saas(self):
        import pathlib
        src = pathlib.Path("app/api/policy/permission_map.py").read_text(encoding="utf-8")
        assert '"/saas"' in src or "'/saas'" in src

    def test_get_maps_reports_read(self):
        from app.api.policy.permission_map import match_permission
        assert match_permission("GET", "/saas/plans") == "reports:read"

    def test_post_maps_tenants_manage(self):
        from app.api.policy.permission_map import match_permission
        assert match_permission("POST", "/saas/upgrade") == "tenants:manage"

    def test_router_registered(self):
        import pathlib
        src = pathlib.Path("app/core/router_registry.py").read_text(encoding="utf-8")
        assert "routes_saas" in src

    def test_service_importable(self):
        import importlib
        mod = importlib.import_module("app.api.services.saas_service")
        assert hasattr(mod, "PLANS")
        assert hasattr(mod, "get_plan_limits")
        assert hasattr(mod, "check_quota")
        assert hasattr(mod, "get_usage")
        assert hasattr(mod, "get_onboarding_status")
        assert hasattr(mod, "upgrade_plan_request")
