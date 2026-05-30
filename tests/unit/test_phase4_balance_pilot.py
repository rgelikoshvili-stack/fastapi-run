"""tests/unit/test_phase4_balance_pilot.py — Phase 4: Balance.ge Controlled Pilot.

Covers:
  1. run_preflight_check — all pass, dry_run missing, creds missing
  2. enable_live_posting — succeeds, fails on preflight
  3. disable_live_posting
  4. get_pilot_status — enabled/disabled, global gate
  5. Routes: registered in routes_posting, require correct permissions
  6. dry_run_posting_service already exists (regression check)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ctx(fetchval_side=None, fetchrow=None):
    conn = AsyncMock()
    if fetchval_side:
        conn.fetchval = AsyncMock(side_effect=fetchval_side)
    else:
        conn.fetchval = AsyncMock(return_value=0)
    conn.fetchrow = AsyncMock(return_value=fetchrow)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__  = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# 1. run_preflight_check
# ---------------------------------------------------------------------------
class TestRunPreflightCheck:
    @pytest.mark.asyncio
    async def test_all_checks_pass(self):
        from app.api.services.balance_pilot_service import run_preflight_check
        cred_row = {"id": 1, "masked_hint": "****1234"}
        ctx = _ctx(fetchval_side=[3, 5], fetchrow=cred_row)
        # fetchval called twice (dry_run_count, approved_count); fetchrow once (cred)
        conn = AsyncMock()
        conn.fetchval = AsyncMock(side_effect=[3, 5])
        conn.fetchrow = AsyncMock(return_value=cred_row)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=conn)
        mock_ctx.__aexit__  = AsyncMock(return_value=False)
        with patch("app.api.services.balance_pilot_service.get_conn", return_value=mock_ctx):
            result = await run_preflight_check("t1")
        assert result["ready"] is True
        assert result["blockers"] == []
        assert len(result["checks"]) == 3

    @pytest.mark.asyncio
    async def test_no_dry_run_blocks(self):
        from app.api.services.balance_pilot_service import run_preflight_check
        cred_row = {"id": 1, "masked_hint": "****1234"}
        conn = AsyncMock()
        conn.fetchval = AsyncMock(side_effect=[0, 5])   # 0 dry_runs
        conn.fetchrow = AsyncMock(return_value=cred_row)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=conn)
        mock_ctx.__aexit__  = AsyncMock(return_value=False)
        with patch("app.api.services.balance_pilot_service.get_conn", return_value=mock_ctx):
            result = await run_preflight_check("t1")
        assert result["ready"] is False
        assert "dry_run_executed" in result["blockers"]

    @pytest.mark.asyncio
    async def test_no_credentials_blocks(self):
        from app.api.services.balance_pilot_service import run_preflight_check
        conn = AsyncMock()
        conn.fetchval = AsyncMock(side_effect=[1, 5])   # has dry_run
        conn.fetchrow = AsyncMock(return_value=None)    # no credentials
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=conn)
        mock_ctx.__aexit__  = AsyncMock(return_value=False)
        with patch("app.api.services.balance_pilot_service.get_conn", return_value=mock_ctx):
            result = await run_preflight_check("t1")
        assert result["ready"] is False
        assert "credentials_configured" in result["blockers"]


# ---------------------------------------------------------------------------
# 2. enable_live_posting
# ---------------------------------------------------------------------------
class TestEnableLivePosting:
    @pytest.mark.asyncio
    async def test_enable_succeeds_when_preflight_passes(self):
        from app.api.services.balance_pilot_service import enable_live_posting
        mock_preflight = {"ready": True, "checks": [], "blockers": []}
        with patch("app.api.services.balance_pilot_service.run_preflight_check",
                   new=AsyncMock(return_value=mock_preflight)), \
             patch("app.api.services.balance_pilot_service.set_tenant_setting",
                   new=AsyncMock(return_value=True)):
            result = await enable_live_posting("t1", "admin", "Test pilot")
        assert result["enabled"] is True
        assert result["signed_by"] == "admin"
        assert "warning" in result

    @pytest.mark.asyncio
    async def test_enable_fails_when_preflight_fails(self):
        from app.api.services.balance_pilot_service import enable_live_posting
        mock_preflight = {"ready": False, "checks": [], "blockers": ["dry_run_executed"]}
        with patch("app.api.services.balance_pilot_service.run_preflight_check",
                   new=AsyncMock(return_value=mock_preflight)):
            with pytest.raises(ValueError, match="PREFLIGHT_FAILED"):
                await enable_live_posting("t1", "admin")


# ---------------------------------------------------------------------------
# 3. disable_live_posting
# ---------------------------------------------------------------------------
class TestDisableLivePosting:
    @pytest.mark.asyncio
    async def test_disable_returns_false(self):
        from app.api.services.balance_pilot_service import disable_live_posting
        with patch("app.api.services.balance_pilot_service.set_tenant_setting",
                   new=AsyncMock(return_value=True)):
            result = await disable_live_posting("t1", "admin", "Emergency stop")
        assert result["enabled"] is False
        assert result["disabled_by"] == "admin"
        assert result["reason"] == "Emergency stop"


# ---------------------------------------------------------------------------
# 4. get_pilot_status
# ---------------------------------------------------------------------------
class TestGetPilotStatus:
    @pytest.mark.asyncio
    async def test_not_enabled_by_default(self):
        from app.api.services.balance_pilot_service import get_pilot_status
        with patch("app.api.services.balance_pilot_service.get_tenant_setting",
                   new=AsyncMock(return_value=False)):
            result = await get_pilot_status("t1")
        assert result["tenant_enabled"] is False
        assert result["live_posting_active"] is False

    @pytest.mark.asyncio
    async def test_live_posting_active_requires_both_gates(self):
        from app.api.services.balance_pilot_service import get_pilot_status
        import os
        # tenant enabled but global gate closed
        with patch("app.api.services.balance_pilot_service.get_tenant_setting",
                   new=AsyncMock(return_value=True)), \
             patch.dict(os.environ, {"POSTED_LEDGER_WRITES_ENABLED": "false"}):
            result = await get_pilot_status("t1")
        assert result["tenant_enabled"] is True
        assert result["global_gate_open"] is False
        assert result["live_posting_active"] is False

    @pytest.mark.asyncio
    async def test_live_posting_active_when_both_gates_open(self):
        from app.api.services.balance_pilot_service import get_pilot_status
        import os
        with patch("app.api.services.balance_pilot_service.get_tenant_setting",
                   new=AsyncMock(return_value=True)), \
             patch.dict(os.environ, {"POSTED_LEDGER_WRITES_ENABLED": "true"}):
            result = await get_pilot_status("t1")
        assert result["live_posting_active"] is True


# ---------------------------------------------------------------------------
# 5. Routes in routes_posting
# ---------------------------------------------------------------------------
class TestPilotRoutes:
    def test_pilot_routes_in_file(self):
        import pathlib
        src = pathlib.Path("app/api/routes_posting.py").read_text(encoding="utf-8")
        assert "/balance/pilot/status"   in src
        assert "/balance/pilot/preflight" in src
        assert "/balance/pilot/enable"   in src
        assert "/balance/pilot/disable"  in src

    def test_enable_requires_tenants_manage(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_posting.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "balance_pilot_enable":
                assert "tenants:manage" in ast.unparse(node)
                return
        pytest.fail("balance_pilot_enable not found")

    def test_status_requires_posting_read(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_posting.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "balance_pilot_status":
                assert "posting:read" in ast.unparse(node)
                return
        pytest.fail("balance_pilot_status not found")


# ---------------------------------------------------------------------------
# 6. dry_run_posting_service regression
# ---------------------------------------------------------------------------
class TestDryRunRegression:
    def test_dry_run_service_importable(self):
        from app.api.services.posting_service import dry_run_posting_service
        assert callable(dry_run_posting_service)

    def test_dry_run_route_exists(self):
        import pathlib
        src = pathlib.Path("app/api/routes_posting.py").read_text(encoding="utf-8")
        assert "/balance/dry-run/" in src

    def test_service_importable(self):
        import importlib
        mod = importlib.import_module("app.api.services.balance_pilot_service")
        assert hasattr(mod, "run_preflight_check")
        assert hasattr(mod, "enable_live_posting")
        assert hasattr(mod, "disable_live_posting")
        assert hasattr(mod, "get_pilot_status")
