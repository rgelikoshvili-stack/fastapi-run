"""tests/unit/test_phase6_monthly_close.py — Phase 6: Monthly Close Cockpit.

Covers:
  1. build_close_checklist — pure, all 5 items
  2. run_checklist (mocked DB) — per-checker results
  3. get_trial_balance_snapshot (mocked DB)
  4. save_close_signoff (mocked DB) + invalid role
  5. get_close_status (mocked DB) — ready_to_lock logic
  6. Routes: importable, prefix, permissions
  7. Permission map and registry
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _multi_ctx(side_effects):
    """Mock that returns different values for each fetchrow/fetchval call."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(side_effect=side_effects)
    conn.fetchval = AsyncMock(return_value=0)
    conn.fetch    = AsyncMock(return_value=[])
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__  = AsyncMock(return_value=False)
    return ctx


def _ctx(fetchrow=None, rows=None, fetchval=None):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow)
    conn.fetch    = AsyncMock(return_value=rows or [])
    conn.fetchval = AsyncMock(return_value=fetchval or 0)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__  = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# 1. build_close_checklist
# ---------------------------------------------------------------------------
class TestBuildCloseChecklist:
    def test_returns_5_items(self):
        from app.api.services.monthly_close_service import build_close_checklist
        items = build_close_checklist()
        assert len(items) == 5

    def test_all_pending_initially(self):
        from app.api.services.monthly_close_service import build_close_checklist
        items = build_close_checklist()
        assert all(i["status"] == "pending" for i in items)

    def test_has_required_ids(self):
        from app.api.services.monthly_close_service import build_close_checklist
        ids = {i["id"] for i in build_close_checklist()}
        assert "unposted_drafts"   in ids
        assert "reconciliation_rate" in ids
        assert "opening_balances"  in ids
        assert "payroll_submitted" in ids
        assert "trial_balance"     in ids


# ---------------------------------------------------------------------------
# 2. run_checklist (mocked)
# ---------------------------------------------------------------------------
class TestRunChecklist:
    @pytest.mark.asyncio
    async def test_unposted_drafts_ok_when_zero(self):
        from app.api.services.monthly_close_service import run_checklist
        conn = AsyncMock()
        # fetchval for unposted count
        conn.fetchval = AsyncMock(return_value=0)
        # fetchrow for others: reconciliation, opening, payroll, trial_balance
        conn.fetchrow = AsyncMock(side_effect=[
            {"total": 10, "reconciled": 10},          # reconciliation
            {"total_debit": "1000", "total_credit": "1000"},  # opening balances
            {"status": "accepted"},                    # payroll
            {"total_debit": "5000", "total_credit": "5000"},  # trial balance
        ])
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__  = AsyncMock(return_value=False)
        with patch("app.api.services.monthly_close_service.get_conn", return_value=ctx):
            result = await run_checklist("t1", "2026-01")
        unposted = next(i for i in result if i["id"] == "unposted_drafts")
        assert unposted["status"] == "ok"

    @pytest.mark.asyncio
    async def test_unposted_drafts_failed_when_nonzero(self):
        from app.api.services.monthly_close_service import run_checklist
        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=3)
        conn.fetchrow = AsyncMock(side_effect=[
            {"total": 5, "reconciled": 5},
            {"total_debit": "0", "total_credit": "0"},
            None,
            {"total_debit": "0", "total_credit": "0"},
        ])
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__  = AsyncMock(return_value=False)
        with patch("app.api.services.monthly_close_service.get_conn", return_value=ctx):
            result = await run_checklist("t1", "2026-01")
        unposted = next(i for i in result if i["id"] == "unposted_drafts")
        assert unposted["status"] == "failed"
        assert unposted["value"] == 3

    @pytest.mark.asyncio
    async def test_reconciliation_warning_at_70_to_90(self):
        from app.api.services.monthly_close_service import run_checklist
        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=0)  # unposted
        conn.fetchrow = AsyncMock(side_effect=[
            {"total": 10, "reconciled": 8},   # 80% — warning
            {"total_debit": "0", "total_credit": "0"},
            None,
            {"total_debit": "0", "total_credit": "0"},
        ])
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__  = AsyncMock(return_value=False)
        with patch("app.api.services.monthly_close_service.get_conn", return_value=ctx):
            result = await run_checklist("t1", "2026-01")
        recon = next(i for i in result if i["id"] == "reconciliation_rate")
        assert recon["status"] == "warning"


# ---------------------------------------------------------------------------
# 3. get_trial_balance_snapshot
# ---------------------------------------------------------------------------
class TestGetTrialBalanceSnapshot:
    @pytest.mark.asyncio
    async def test_balanced_returns_true(self):
        from app.api.services.monthly_close_service import get_trial_balance_snapshot
        rows = [
            {"account_code": "1120", "debit": 1000, "credit": 0},
            {"account_code": "6110", "debit": 0,    "credit": 1000},
        ]
        with patch("app.api.services.monthly_close_service.get_conn", return_value=_ctx(rows=rows)):
            result = await get_trial_balance_snapshot("t1", "2026-01")
        assert result["balanced"] is True
        assert result["total_debit"] == 1000.0
        assert result["total_credit"] == 1000.0

    @pytest.mark.asyncio
    async def test_empty_is_balanced(self):
        from app.api.services.monthly_close_service import get_trial_balance_snapshot
        with patch("app.api.services.monthly_close_service.get_conn", return_value=_ctx(rows=[])):
            result = await get_trial_balance_snapshot("t1", "2026-01")
        assert result["balanced"] is True
        assert result["lines"] == []


# ---------------------------------------------------------------------------
# 4. save_close_signoff
# ---------------------------------------------------------------------------
class TestSaveCloseSignoff:
    @pytest.mark.asyncio
    async def test_accountant_signoff(self):
        from app.api.services.monthly_close_service import save_close_signoff
        row = {"id": 1, "tenant_id": "t1", "month": "2026-01",
               "signed_by": "user1", "role": "accountant",
               "status": "accountant_signed", "signed_at": "2026-01-31"}
        with patch("app.api.services.monthly_close_service.get_conn", return_value=_ctx(fetchrow=row)):
            result = await save_close_signoff("t1", "2026-01", "user1", "accountant")
        assert result["role"] == "accountant"
        assert result["status"] == "accountant_signed"

    @pytest.mark.asyncio
    async def test_invalid_role_raises(self):
        from app.api.services.monthly_close_service import save_close_signoff
        with pytest.raises(ValueError, match="INVALID_ROLE"):
            await save_close_signoff("t1", "2026-01", "user1", "manager")


# ---------------------------------------------------------------------------
# 5. get_close_status
# ---------------------------------------------------------------------------
class TestGetCloseStatus:
    @pytest.mark.asyncio
    async def test_open_state_when_no_signoffs(self):
        from app.api.services.monthly_close_service import get_close_status
        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=0)
        conn.fetchrow = AsyncMock(side_effect=[
            {"total": 0, "reconciled": 0},
            {"total_debit": "0", "total_credit": "0"},
            None,
            {"total_debit": "0", "total_credit": "0"},
        ])
        conn.fetch = AsyncMock(return_value=[])  # no signoffs
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__  = AsyncMock(return_value=False)
        with patch("app.api.services.monthly_close_service.get_conn", return_value=ctx):
            result = await get_close_status("t1", "2026-01")
        assert result["close_state"] == "open"
        assert result["ready_to_lock"] is False

    @pytest.mark.asyncio
    async def test_cfo_signed_state(self):
        from app.api.services.monthly_close_service import get_close_status
        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=0)
        conn.fetchrow = AsyncMock(side_effect=[
            {"total": 10, "reconciled": 10},
            {"total_debit": "1000", "total_credit": "1000"},
            {"status": "accepted"},
            {"total_debit": "1000", "total_credit": "1000"},
        ])
        conn.fetch = AsyncMock(return_value=[
            {"role": "accountant", "signed_by": "a1", "status": "accountant_signed", "signed_at": "2026-01-30"},
            {"role": "cfo",        "signed_by": "c1", "status": "cfo_signed",        "signed_at": "2026-01-31"},
        ])
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__  = AsyncMock(return_value=False)
        with patch("app.api.services.monthly_close_service.get_conn", return_value=ctx):
            result = await get_close_status("t1", "2026-01")
        assert result["close_state"] == "cfo_signed"


# ---------------------------------------------------------------------------
# 6. Routes
# ---------------------------------------------------------------------------
class TestMonthlyCloseRoutes:
    def test_router_importable(self):
        import importlib
        mod = importlib.import_module("app.api.routes_monthly_close")
        assert hasattr(mod, "router")

    def test_router_prefix(self):
        from app.api.routes_monthly_close import router
        assert router.prefix == "/monthly-close"

    def test_status_requires_reports_read(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_monthly_close.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "close_status":
                assert "reports:read" in ast.unparse(node)
                return
        pytest.fail("close_status not found")

    def test_signoff_requires_posting_write(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_monthly_close.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "signoff":
                assert "posting:write" in ast.unparse(node)
                return
        pytest.fail("signoff not found")


# ---------------------------------------------------------------------------
# 7. Permission map and registry
# ---------------------------------------------------------------------------
class TestMonthlyCloseRegistration:
    def test_permission_map_has_monthly_close(self):
        import pathlib
        src = pathlib.Path("app/api/policy/permission_map.py").read_text(encoding="utf-8")
        assert "/monthly-close" in src

    def test_get_maps_reports_read(self):
        from app.api.policy.permission_map import match_permission
        assert match_permission("GET", "/monthly-close/status") == "reports:read"

    def test_post_maps_posting_write(self):
        from app.api.policy.permission_map import match_permission
        assert match_permission("POST", "/monthly-close/signoff") == "posting:write"

    def test_router_registered(self):
        import pathlib
        src = pathlib.Path("app/core/router_registry.py").read_text(encoding="utf-8")
        assert "routes_monthly_close" in src

    def test_service_importable(self):
        import importlib
        mod = importlib.import_module("app.api.services.monthly_close_service")
        assert hasattr(mod, "build_close_checklist")
        assert hasattr(mod, "run_checklist")
        assert hasattr(mod, "get_trial_balance_snapshot")
        assert hasattr(mod, "save_close_signoff")
        assert hasattr(mod, "get_close_status")

    def test_ddl_has_monthly_close_signoffs(self):
        import pathlib
        src = pathlib.Path("app/startup/migrations_tables.py").read_text(encoding="utf-8")
        assert "monthly_close_signoffs" in src
