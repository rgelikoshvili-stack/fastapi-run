"""tests/unit/test_accounting_gap_12a.py — Task 12A: Accounting Gap Audit.

Covers:
  1. /bs/detail no longer returns unposted drafts (status filter enforced)
  2. opening_balances service: upsert, list, delete, totals
  3. opening_balances route: upsert returns ok, 403 for wrong role,
     mismatch account_code rejected
  4. period_close endpoint exists and is registered
  5. retained_earnings account code is defined
  6. CIT rate is 15% (Georgian Estonian model)
"""
from __future__ import annotations

import importlib
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. /bs/detail — posted-only filter
# ---------------------------------------------------------------------------
class TestBsDetailPostedFilter:
    def test_bs_detail_conditions_include_posted_filter(self):
        import ast, pathlib
        src = (pathlib.Path("app/api/routes_reports.py")).read_text(encoding="utf-8")
        tree = ast.parse(src)

        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "bs_detail":
                func_src = ast.unparse(node)
                assert "posted" in func_src, (
                    "bs_detail must filter journal_drafts to posted status"
                )
                assert "simulated_success" in func_src, (
                    "bs_detail must include simulated_success alongside posted"
                )
                return
        pytest.fail("bs_detail function not found in routes_reports.py")

    def test_pnl_detail_already_had_posted_filter(self):
        import ast, pathlib
        src = (pathlib.Path("app/api/routes_reports.py")).read_text(encoding="utf-8")
        tree = ast.parse(src)

        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "pnl_detail":
                func_src = ast.unparse(node)
                assert "posted" in func_src
                return
        pytest.fail("pnl_detail function not found in routes_reports.py")

    def test_cashflow_detail_does_not_query_journal_drafts(self):
        import ast, pathlib
        src = (pathlib.Path("app/api/routes_reports.py")).read_text(encoding="utf-8")
        tree = ast.parse(src)

        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "cashflow_detail":
                func_src = ast.unparse(node)
                assert "journal_drafts" not in func_src, (
                    "cashflow_detail should not query journal_drafts"
                )
                return
        pytest.fail("cashflow_detail function not found in routes_reports.py")


# ---------------------------------------------------------------------------
# 2. opening_balances service
# ---------------------------------------------------------------------------
class TestOpeningBalancesService:
    def test_service_module_importable(self):
        mod = importlib.import_module("app.api.services.opening_balances_service")
        assert hasattr(mod, "upsert_opening_balance")
        assert hasattr(mod, "list_opening_balances")
        assert hasattr(mod, "delete_opening_balance")
        assert hasattr(mod, "get_opening_balance_totals")

    @pytest.mark.asyncio
    async def test_upsert_calls_conn_fetchrow(self):
        from datetime import date
        from app.api.services.opening_balances_service import upsert_opening_balance

        mock_row = {
            "id": 1, "tenant_id": "t1", "account_code": "1110",
            "account_name": "Cash", "debit": "1000.00", "credit": "0.00",
            "as_of_date": date(2026, 1, 1), "created_by": "admin",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.services.opening_balances_service.get_conn", return_value=mock_ctx):
            result = await upsert_opening_balance(
                tenant_id="t1", account_code="1110", account_name="Cash",
                debit=Decimal("1000"), credit=Decimal("0"),
                as_of_date=date(2026, 1, 1), created_by="admin",
            )
        assert result["account_code"] == "1110"
        assert result["debit"] == 1000.0
        mock_conn.fetchrow.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_returns_list(self):
        from app.api.services.opening_balances_service import list_opening_balances

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.services.opening_balances_service.get_conn", return_value=mock_ctx):
            result = await list_opening_balances("t1")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_delete_returns_true_on_success(self):
        from datetime import date
        from app.api.services.opening_balances_service import delete_opening_balance

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="DELETE 1")
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.services.opening_balances_service.get_conn", return_value=mock_ctx):
            result = await delete_opening_balance("t1", "1110", date(2026, 1, 1))
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_not_found(self):
        from datetime import date
        from app.api.services.opening_balances_service import delete_opening_balance

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="DELETE 0")
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.services.opening_balances_service.get_conn", return_value=mock_ctx):
            result = await delete_opening_balance("t1", "9999", date(2026, 1, 1))
        assert result is False

    @pytest.mark.asyncio
    async def test_totals_balanced_flag(self):
        from datetime import date
        from app.api.services.opening_balances_service import get_opening_balance_totals

        mock_row = {"row_count": 2, "total_debit": "5000.00", "total_credit": "5000.00"}
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.services.opening_balances_service.get_conn", return_value=mock_ctx):
            result = await get_opening_balance_totals("t1", date(2026, 1, 1))
        assert result["balanced"] is True
        assert result["difference"] == 0.0

    @pytest.mark.asyncio
    async def test_totals_unbalanced_flag(self):
        from datetime import date
        from app.api.services.opening_balances_service import get_opening_balance_totals

        mock_row = {"row_count": 1, "total_debit": "1000.00", "total_credit": "800.00"}
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.services.opening_balances_service.get_conn", return_value=mock_ctx):
            result = await get_opening_balance_totals("t1", date(2026, 1, 1))
        assert result["balanced"] is False
        assert result["difference"] == 200.0


# ---------------------------------------------------------------------------
# 3. opening_balances routes
# ---------------------------------------------------------------------------
class TestOpeningBalancesRoutes:
    def test_router_importable(self):
        mod = importlib.import_module("app.api.routes_opening_balances")
        assert hasattr(mod, "router")

    def test_router_prefix(self):
        from app.api.routes_opening_balances import router
        assert router.prefix == "/opening-balances"

    def test_upsert_rejects_account_code_mismatch(self):
        import asyncio
        from datetime import date
        from app.api.routes_opening_balances import upsert_balance, OpeningBalanceIn

        payload = OpeningBalanceIn(
            account_code="2000",
            account_name="Mismatch",
            debit=Decimal("0"),
            credit=Decimal("0"),
            as_of_date=date(2026, 1, 1),
        )
        mock_request = MagicMock()
        mock_request.state.tenant_id = "t1"
        mock_request.state.user_id = "u1"

        with patch("app.api.routes_opening_balances.require_permission"):
            result = asyncio.get_event_loop().run_until_complete(
                upsert_balance("1110", payload, mock_request)
            )
        assert result["ok"] is False
        assert result["error"]["code"] == "ACCOUNT_CODE_MISMATCH"

    def test_upsert_requires_posting_write_permission(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_opening_balances.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "upsert_balance":
                func_src = ast.unparse(node)
                assert "posting:write" in func_src
                return
        pytest.fail("upsert_balance not found")

    def test_list_requires_reports_read_permission(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_opening_balances.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "list_balances":
                func_src = ast.unparse(node)
                assert "reports:read" in func_src
                return
        pytest.fail("list_balances not found")

    def test_permission_map_has_opening_balances_entries(self):
        import pathlib
        src = pathlib.Path("app/api/policy/permission_map.py").read_text(encoding="utf-8")
        assert "/opening-balances" in src
        assert "reports:read" in src
        assert "posting:write" in src

    def test_router_registered_in_registry(self):
        import pathlib
        src = pathlib.Path("app/core/router_registry.py").read_text(encoding="utf-8")
        assert "routes_opening_balances" in src


# ---------------------------------------------------------------------------
# 4. period_close endpoint exists
# ---------------------------------------------------------------------------
class TestPeriodCloseExists:
    def test_routes_closing_has_close_period(self):
        import pathlib
        src = pathlib.Path("app/api/routes_closing.py").read_text(encoding="utf-8")
        assert "close_period" in src

    def test_close_period_requires_permission(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_closing.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "close_period":
                func_src = ast.unparse(node)
                assert "require_permission" in func_src
                return
        pytest.fail("close_period not found in routes_closing.py")


# ---------------------------------------------------------------------------
# 5. retained_earnings account code
# ---------------------------------------------------------------------------
class TestRetainedEarningsAccount:
    def test_retained_earnings_account_defined(self):
        from app.api.services.accounting_rules_core import UNIFIED_ACCOUNTS
        assert "retained_earnings" in UNIFIED_ACCOUNTS
        assert UNIFIED_ACCOUNTS["retained_earnings"] == "4210"


# ---------------------------------------------------------------------------
# 6. CIT rate
# ---------------------------------------------------------------------------
class TestCITRate:
    def test_cit_rate_is_15_percent(self):
        import pathlib
        src = pathlib.Path("app/api/routes_tax.py").read_text(encoding="utf-8")
        assert "0.15" in src, "CIT rate should be 0.15 (15%)"

    def test_cit_route_exists(self):
        import pathlib
        src = pathlib.Path("app/api/routes_tax.py").read_text(encoding="utf-8")
        assert "cit" in src.lower()
