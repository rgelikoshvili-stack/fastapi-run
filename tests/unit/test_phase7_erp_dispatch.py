"""tests/unit/test_phase7_erp_dispatch.py — Phase 7: Multi-ERP Dispatch.

Covers:
  1. infer_transaction_type — pure account code mapping
  2. apply_routing_rules — pure, fallback to default
  3. connector_health_matrix — mocked connectors
  4. get_routing_rules / set_routing_rule (mocked tenant_settings)
  5. route_transaction (mocked)
  6. get_dispatch_log_summary (mocked DB)
  7. Routes: importable, prefix, permissions
  8. Permission map and registry
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. infer_transaction_type
# ---------------------------------------------------------------------------
class TestInferTransactionType:
    def test_sales_revenue_account(self):
        from app.api.services.erp_dispatch_service import infer_transaction_type
        assert infer_transaction_type("6110") == "sales"

    def test_expense_account(self):
        from app.api.services.erp_dispatch_service import infer_transaction_type
        assert infer_transaction_type("7310") == "expenses"

    def test_payroll_salary_account(self):
        from app.api.services.erp_dispatch_service import infer_transaction_type
        assert infer_transaction_type("7210") == "payroll"

    def test_inventory_account(self):
        from app.api.services.erp_dispatch_service import infer_transaction_type
        assert infer_transaction_type("1310") == "inventory"

    def test_unknown_returns_default(self):
        from app.api.services.erp_dispatch_service import infer_transaction_type
        assert infer_transaction_type("9999") == "default"


# ---------------------------------------------------------------------------
# 2. apply_routing_rules
# ---------------------------------------------------------------------------
class TestApplyRoutingRules:
    def test_uses_specific_rule(self):
        from app.api.services.erp_dispatch_service import apply_routing_rules
        rules = {"sales": "balance", "expenses": "1c", "default": "balance"}
        assert apply_routing_rules(rules, "expenses") == "1c"

    def test_falls_back_to_default(self):
        from app.api.services.erp_dispatch_service import apply_routing_rules
        rules = {"default": "1c"}
        assert apply_routing_rules(rules, "payroll") == "1c"

    def test_falls_back_to_balance_when_no_default(self):
        from app.api.services.erp_dispatch_service import apply_routing_rules
        assert apply_routing_rules({}, "sales") == "balance"


# ---------------------------------------------------------------------------
# 3. connector_health_matrix
# ---------------------------------------------------------------------------
class TestConnectorHealthMatrix:
    def test_returns_all_known_connectors(self):
        from app.api.services.erp_dispatch_service import connector_health_matrix, KNOWN_CONNECTORS
        with patch("app.api.services.erp_dispatch_service._check_connector_health",
                   return_value={"connector": "x", "status": "ok", "connected": True, "mode": "demo", "message": ""}):
            result = connector_health_matrix("t1")
        assert len(result["connectors"]) == len(KNOWN_CONNECTORS)

    def test_healthy_count_matches(self):
        from app.api.services.erp_dispatch_service import connector_health_matrix, KNOWN_CONNECTORS
        healthy = {"connector": "x", "status": "ok",    "connected": True,  "mode": "demo", "message": ""}
        error   = {"connector": "y", "status": "error", "connected": False, "mode": "live", "message": "timeout"}
        # Build side_effects for all 5 connectors: 4 healthy + 1 error
        side_effects = [healthy] * (len(KNOWN_CONNECTORS) - 1) + [error]
        with patch("app.api.services.erp_dispatch_service._check_connector_health",
                   side_effect=side_effects):
            result = connector_health_matrix("t1")
        assert result["healthy_count"] == len(KNOWN_CONNECTORS) - 1
        assert result["all_healthy"] is False

    def test_error_connector_still_included(self):
        from app.api.services.erp_dispatch_service import connector_health_matrix
        with patch("app.api.services.erp_dispatch_service._check_connector_health",
                   return_value={"connector": "x", "status": "error", "connected": False, "mode": "live", "message": "fail"}):
            result = connector_health_matrix("t1")
        assert any(r["status"] == "error" for r in result["connectors"])


# ---------------------------------------------------------------------------
# 4. get_routing_rules / set_routing_rule
# ---------------------------------------------------------------------------
class TestRoutingRules:
    @pytest.mark.asyncio
    async def test_get_defaults_when_empty(self):
        from app.api.services.erp_dispatch_service import get_routing_rules
        with patch("app.api.services.erp_dispatch_service.get_tenant_setting",
                   new=AsyncMock(return_value={})):
            rules = await get_routing_rules("t1")
        assert "default" in rules
        assert rules["default"] == "balance"

    @pytest.mark.asyncio
    async def test_stored_rules_override_defaults(self):
        from app.api.services.erp_dispatch_service import get_routing_rules
        with patch("app.api.services.erp_dispatch_service.get_tenant_setting",
                   new=AsyncMock(return_value={"expenses": "1c"})):
            rules = await get_routing_rules("t1")
        assert rules["expenses"] == "1c"

    @pytest.mark.asyncio
    async def test_set_routing_rule_valid(self):
        from app.api.services.erp_dispatch_service import set_routing_rule
        with patch("app.api.services.erp_dispatch_service.get_tenant_setting",
                   new=AsyncMock(return_value={})), \
             patch("app.api.services.erp_dispatch_service.set_tenant_setting",
                   new=AsyncMock(return_value=True)):
            result = await set_routing_rule("t1", "expenses", "1c")
        assert result["expenses"] == "1c"

    @pytest.mark.asyncio
    async def test_set_routing_invalid_txn_type_raises(self):
        from app.api.services.erp_dispatch_service import set_routing_rule
        with pytest.raises(ValueError, match="INVALID_TXN_TYPE"):
            await set_routing_rule("t1", "unknown_type", "balance")

    @pytest.mark.asyncio
    async def test_set_routing_invalid_connector_raises(self):
        from app.api.services.erp_dispatch_service import set_routing_rule
        with pytest.raises(ValueError, match="INVALID_CONNECTOR"):
            await set_routing_rule("t1", "sales", "sap")


# ---------------------------------------------------------------------------
# 5. route_transaction
# ---------------------------------------------------------------------------
class TestRouteTransaction:
    @pytest.mark.asyncio
    async def test_routes_expense_to_1c(self):
        from app.api.services.erp_dispatch_service import route_transaction
        with patch("app.api.services.erp_dispatch_service.get_tenant_setting",
                   new=AsyncMock(return_value={"expenses": "1c"})):
            result = await route_transaction("t1", "7310")
        assert result["txn_type"] == "expenses"
        assert result["connector"] == "1c"

    @pytest.mark.asyncio
    async def test_unknown_account_uses_default(self):
        from app.api.services.erp_dispatch_service import route_transaction
        with patch("app.api.services.erp_dispatch_service.get_tenant_setting",
                   new=AsyncMock(return_value={})):
            result = await route_transaction("t1", "9999")
        assert result["txn_type"] == "default"
        assert result["connector"] == "balance"


# ---------------------------------------------------------------------------
# 6. get_dispatch_log_summary
# ---------------------------------------------------------------------------
class TestGetDispatchLogSummary:
    @pytest.mark.asyncio
    async def test_returns_by_connector_and_recent(self):
        from app.api.services.erp_dispatch_service import get_dispatch_log_summary
        agg_rows = [
            MagicMock(target_system="balance", status="success", count=5),
            MagicMock(target_system="1c",      status="error",   count=1),
        ]
        for r in agg_rows:
            r.__getitem__ = lambda self, k: getattr(self, k)
        conn = AsyncMock()
        conn.fetch = AsyncMock(side_effect=[agg_rows, []])
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__  = AsyncMock(return_value=False)
        with patch("app.api.services.erp_dispatch_service.get_conn", return_value=ctx):
            result = await get_dispatch_log_summary("t1")
        assert "by_connector" in result
        assert "recent" in result


# ---------------------------------------------------------------------------
# 7. Routes
# ---------------------------------------------------------------------------
class TestErpDispatchRoutes:
    def test_router_importable(self):
        import importlib
        mod = importlib.import_module("app.api.routes_erp_dispatch")
        assert hasattr(mod, "router")

    def test_router_prefix(self):
        from app.api.routes_erp_dispatch import router
        assert router.prefix == "/erp-dispatch"

    def test_health_requires_posting_read(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_erp_dispatch.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "health_matrix":
                assert "posting:read" in ast.unparse(node)
                return
        pytest.fail("health_matrix not found")

    def test_update_routing_requires_posting_write(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_erp_dispatch.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "update_routing":
                assert "posting:write" in ast.unparse(node)
                return
        pytest.fail("update_routing not found")


# ---------------------------------------------------------------------------
# 8. Permission map and registry
# ---------------------------------------------------------------------------
class TestErpDispatchRegistration:
    def test_permission_map_has_erp_dispatch(self):
        import pathlib
        src = pathlib.Path("app/api/policy/permission_map.py").read_text(encoding="utf-8")
        assert "/erp-dispatch" in src

    def test_get_maps_posting_read(self):
        from app.api.policy.permission_map import match_permission
        assert match_permission("GET", "/erp-dispatch/health") == "posting:read"

    def test_put_maps_posting_write(self):
        from app.api.policy.permission_map import match_permission
        assert match_permission("PUT", "/erp-dispatch/routing") == "posting:write"

    def test_router_registered(self):
        import pathlib
        src = pathlib.Path("app/core/router_registry.py").read_text(encoding="utf-8")
        assert "routes_erp_dispatch" in src

    def test_service_importable(self):
        import importlib
        mod = importlib.import_module("app.api.services.erp_dispatch_service")
        assert hasattr(mod, "infer_transaction_type")
        assert hasattr(mod, "apply_routing_rules")
        assert hasattr(mod, "connector_health_matrix")
        assert hasattr(mod, "get_routing_rules")
        assert hasattr(mod, "set_routing_rule")
        assert hasattr(mod, "route_transaction")
        assert hasattr(mod, "get_dispatch_log_summary")
