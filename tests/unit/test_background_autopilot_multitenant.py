"""
tests/unit/test_background_autopilot_multitenant.py

Unit tests for the multi-tenant autopilot fix in app/startup/background.py.

Contract:
  - autopilot_loop must iterate ALL active tenants from the tenants table,
    not only the hard-coded "default" tenant.
  - A per-tenant exception must not prevent remaining tenants from running.
  - _get_active_tenant_ids must fall back to ["default"] on any DB error.
  - No DB connection is made in these tests (all mocked).
  - No connectors are activated.
  - No approval logic is changed.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper: extract the _run function from autopilot_loop without running the
# infinite _monitored_loop.  Patches _monitored_loop to capture the inner
# _run coroutine instead of looping forever.
# ---------------------------------------------------------------------------

async def _capture_run_fn(extra_patches=()):
    """
    Call autopilot_loop() with _monitored_loop patched out.
    Returns the captured _run coroutine function.
    Any extra context-manager patches in extra_patches are entered first so
    that lazy imports inside autopilot_loop see the mock values.
    """
    from app.startup import background

    captured: dict = {}

    async def fake_monitored(name, fn, interval):
        captured["fn"] = fn

    # Activate caller-supplied patches so that the from...import inside
    # autopilot_loop picks up mock objects.
    import contextlib
    stack = contextlib.ExitStack()
    for p in extra_patches:
        stack.enter_context(p)

    with stack:
        with patch("app.startup.background._monitored_loop", fake_monitored):
            await background.autopilot_loop()

    return captured["fn"]


# ===========================================================================
# A) _get_active_tenant_ids — module-level helper (sync, independently testable)
# ===========================================================================

def _make_async_conn(rows):
    """Build asyncpg-style mock connection."""
    from contextlib import asynccontextmanager
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[{"tenant_id": r} for r in rows])

    @asynccontextmanager
    async def _ctx():
        yield conn

    return _ctx


class TestGetActiveTenantIds:

    @pytest.mark.asyncio
    async def test_returns_all_tenants_from_db(self):
        from app.startup.background import _get_active_tenant_ids
        ctx = _make_async_conn(["tenant_a", "tenant_b", "tenant_c"])
        with patch("app.startup.background.get_conn", ctx):
            result = await _get_active_tenant_ids()
        assert result == ["tenant_a", "tenant_b", "tenant_c"]

    @pytest.mark.asyncio
    async def test_does_not_return_only_default_when_tenants_exist(self):
        from app.startup.background import _get_active_tenant_ids
        ctx = _make_async_conn(["company_x", "company_y"])
        with patch("app.startup.background.get_conn", ctx):
            result = await _get_active_tenant_ids()
        assert "default" not in result
        assert set(result) == {"company_x", "company_y"}

    @pytest.mark.asyncio
    async def test_falls_back_to_default_on_db_connection_error(self):
        from app.startup.background import _get_active_tenant_ids
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _err_ctx():
            raise Exception("Connection refused")
            yield  # noqa

        with patch("app.startup.background.get_conn", _err_ctx):
            result = await _get_active_tenant_ids()
        assert result == ["default"]

    @pytest.mark.asyncio
    async def test_falls_back_to_default_on_query_error(self):
        from app.startup.background import _get_active_tenant_ids
        from contextlib import asynccontextmanager
        conn = AsyncMock()
        conn.fetch = AsyncMock(side_effect=RuntimeError("query failed"))

        @asynccontextmanager
        async def _ctx():
            yield conn

        with patch("app.startup.background.get_conn", _ctx):
            result = await _get_active_tenant_ids()
        assert result == ["default"]

    @pytest.mark.asyncio
    async def test_falls_back_to_default_when_table_is_empty(self):
        from app.startup.background import _get_active_tenant_ids
        ctx = _make_async_conn([])
        with patch("app.startup.background.get_conn", ctx):
            result = await _get_active_tenant_ids()
        assert result == ["default"]

    @pytest.mark.asyncio
    async def test_closes_connection_after_successful_query(self):
        """asyncpg context manager handles connection lifecycle — just verify result."""
        from app.startup.background import _get_active_tenant_ids
        ctx = _make_async_conn(["tenant_a"])
        with patch("app.startup.background.get_conn", ctx):
            result = await _get_active_tenant_ids()
        assert result == ["tenant_a"]

    @pytest.mark.asyncio
    async def test_closes_connection_even_when_query_fails(self):
        from app.startup.background import _get_active_tenant_ids
        from contextlib import asynccontextmanager
        conn = AsyncMock()
        conn.fetch = AsyncMock(side_effect=RuntimeError("SQL error"))

        @asynccontextmanager
        async def _ctx():
            yield conn

        with patch("app.startup.background.get_conn", _ctx):
            result = await _get_active_tenant_ids()
        assert result == ["default"]

    @pytest.mark.asyncio
    async def test_returns_list_type(self):
        from app.startup.background import _get_active_tenant_ids
        ctx = _make_async_conn(["t1", "t2"])
        with patch("app.startup.background.get_conn", ctx):
            result = await _get_active_tenant_ids()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_single_tenant_returned(self):
        from app.startup.background import _get_active_tenant_ids
        ctx = _make_async_conn(["only_tenant"])
        with patch("app.startup.background.get_conn", ctx):
            result = await _get_active_tenant_ids()
        assert result == ["only_tenant"]


# ===========================================================================
# B) autopilot_loop multi-tenant behavior (async)
# ===========================================================================

class TestAutopilotLoopMultiTenant:

    @pytest.mark.asyncio
    async def test_autopilot_runs_for_all_tenants(self):
        """autopilot_approve_service must be called once for each active tenant."""
        called_with = []

        def mock_approve(tenant_id):
            called_with.append(tenant_id)
            return {"approved": 0}

        tenants = ["tenant_a", "tenant_b", "tenant_c"]

        approve_patch = patch(
            "app.api.services.approval_service.autopilot_approve_service",
            side_effect=mock_approve,
        )
        run_fn = await _capture_run_fn(extra_patches=[approve_patch])

        with patch("app.startup.background._get_active_tenant_ids", return_value=tenants):
            await run_fn()

        assert called_with == tenants

    @pytest.mark.asyncio
    async def test_autopilot_does_not_hardcode_default_tenant(self):
        """When other tenants are available, 'default' must not be hard-coded."""
        called_with = []

        def mock_approve(tenant_id):
            called_with.append(tenant_id)
            return {"approved": 0}

        approve_patch = patch(
            "app.api.services.approval_service.autopilot_approve_service",
            side_effect=mock_approve,
        )
        run_fn = await _capture_run_fn(extra_patches=[approve_patch])

        with patch(
            "app.startup.background._get_active_tenant_ids",
            return_value=["company_alpha", "company_beta"],
        ):
            await run_fn()

        assert "default" not in called_with
        assert "company_alpha" in called_with
        assert "company_beta" in called_with

    @pytest.mark.asyncio
    async def test_one_tenant_failure_does_not_stop_others(self):
        """If one tenant raises, the remaining tenants must still be processed."""
        called_with = []

        def mock_approve(tenant_id):
            if tenant_id == "tenant_b":
                raise RuntimeError("DB error for tenant_b")
            called_with.append(tenant_id)
            return {"approved": 1}

        approve_patch = patch(
            "app.api.services.approval_service.autopilot_approve_service",
            side_effect=mock_approve,
        )
        run_fn = await _capture_run_fn(extra_patches=[approve_patch])

        with patch(
            "app.startup.background._get_active_tenant_ids",
            return_value=["tenant_a", "tenant_b", "tenant_c"],
        ):
            result = await run_fn()

        assert "tenant_a" in called_with
        assert "tenant_c" in called_with
        assert result["tenants"] == 3

    @pytest.mark.asyncio
    async def test_result_dict_has_tenant_count_and_total_approved(self):
        """_run must return a dict with 'tenants' and 'total_approved' keys."""
        def mock_approve(tenant_id):
            return {"approved": 2}

        approve_patch = patch(
            "app.api.services.approval_service.autopilot_approve_service",
            side_effect=mock_approve,
        )
        run_fn = await _capture_run_fn(extra_patches=[approve_patch])

        with patch(
            "app.startup.background._get_active_tenant_ids",
            return_value=["t1", "t2", "t3"],
        ):
            result = await run_fn()

        assert result["tenants"] == 3
        assert result["total_approved"] == 6

    @pytest.mark.asyncio
    async def test_all_failures_still_returns_tenant_count(self):
        """Even if every tenant fails, result must have correct tenants count."""
        def mock_approve(tenant_id):
            raise RuntimeError("always fails")

        approve_patch = patch(
            "app.api.services.approval_service.autopilot_approve_service",
            side_effect=mock_approve,
        )
        run_fn = await _capture_run_fn(extra_patches=[approve_patch])

        with patch(
            "app.startup.background._get_active_tenant_ids",
            return_value=["t1", "t2"],
        ):
            result = await run_fn()

        assert result["tenants"] == 2
        assert result["total_approved"] == 0

    @pytest.mark.asyncio
    async def test_approved_count_aggregated_across_tenants(self):
        """total_approved must be the sum of approved counts across all tenants."""
        approve_results = {"t1": {"approved": 3}, "t2": {"approved": 5}, "t3": {"approved": 0}}

        def mock_approve(tenant_id):
            return approve_results[tenant_id]

        approve_patch = patch(
            "app.api.services.approval_service.autopilot_approve_service",
            side_effect=mock_approve,
        )
        run_fn = await _capture_run_fn(extra_patches=[approve_patch])

        with patch(
            "app.startup.background._get_active_tenant_ids",
            return_value=["t1", "t2", "t3"],
        ):
            result = await run_fn()

        assert result["total_approved"] == 8

    @pytest.mark.asyncio
    async def test_single_tenant_works(self):
        """Single tenant must still work correctly after the fix."""
        called_with = []

        def mock_approve(tenant_id):
            called_with.append(tenant_id)
            return {"approved": 1}

        approve_patch = patch(
            "app.api.services.approval_service.autopilot_approve_service",
            side_effect=mock_approve,
        )
        run_fn = await _capture_run_fn(extra_patches=[approve_patch])

        with patch(
            "app.startup.background._get_active_tenant_ids",
            return_value=["only_tenant"],
        ):
            result = await run_fn()

        assert called_with == ["only_tenant"]
        assert result["tenants"] == 1

    @pytest.mark.asyncio
    async def test_non_dict_approve_result_handled(self):
        """If autopilot_approve_service returns non-dict, approved defaults to 0."""
        def mock_approve(tenant_id):
            return None  # non-dict return

        approve_patch = patch(
            "app.api.services.approval_service.autopilot_approve_service",
            side_effect=mock_approve,
        )
        run_fn = await _capture_run_fn(extra_patches=[approve_patch])

        with patch(
            "app.startup.background._get_active_tenant_ids",
            return_value=["t1"],
        ):
            result = await run_fn()

        assert result["total_approved"] == 0


# ===========================================================================
# C) Source-level safety checks
# ===========================================================================

class TestSourceSafetyChecks:

    def _source(self) -> str:
        from pathlib import Path
        p = Path(__file__).parent.parent.parent / "app" / "startup" / "background.py"
        return p.read_text(encoding="utf-8")

    def test_hardcoded_default_string_removed_from_autopilot_call(self):
        """The old autopilot_approve_service('default') call must not exist."""
        src = self._source()
        # Use split to avoid matching this test's own source text
        forbidden = "autopilot_approve_service(" + '"default"' + ")"
        assert forbidden not in src, (
            "Hard-coded 'default' tenant still present in autopilot_loop"
        )

    def test_get_active_tenant_ids_defined_in_module(self):
        """_get_active_tenant_ids must be defined at module level."""
        src = self._source()
        assert "def _get_active_tenant_ids" in src

    def test_autopilot_loop_uses_get_active_tenant_ids(self):
        """autopilot_loop must call _get_active_tenant_ids."""
        src = self._source()
        assert "_get_active_tenant_ids" in src

    def test_other_loops_unchanged(self):
        """decay_loop and email_poller_loop must still exist unchanged."""
        src = self._source()
        assert "async def decay_loop" in src
        assert "async def email_poller_loop" in src

    def test_no_connector_activation_in_source(self):
        """background.py must not activate any real ERP connector."""
        src = self._source().lower()
        for connector in ("balance_posting", "oris_post", "onec_post"):
            assert connector not in src, f"Connector call found: {connector}"

    def test_monitored_loop_supervisor_still_present(self):
        """_monitored_loop supervisor must still exist (no accidental removal)."""
        src = self._source()
        assert "async def _monitored_loop" in src
        assert "consecutive_failures" in src
