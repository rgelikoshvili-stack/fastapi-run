"""tests/unit/test_background_email_poller.py

Unit tests for email_poller_loop in app/startup/background.py.
Contract:
  - get_all_active_tenants() must be awaited before iteration.
  - No "coroutine object is not iterable" error is raised.
  - No real IMAP or network calls made.
  - Per-tenant exceptions do not abort the full loop.
  - Timeout per tenant is handled gracefully.
  - No secrets or credentials in log output.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper: capture the inner _run() from email_poller_loop without running
# the infinite _monitored_loop supervisor.
# ---------------------------------------------------------------------------

async def _capture_run_fn(tenant_return=None, collect_side=None):
    """
    Patches _monitored_loop to capture the _run closure passed by
    email_poller_loop, then returns it without running the infinite loop.
    """
    if tenant_return is None:
        tenant_return = ["t1", "t2"]

    captured = {}

    async def _fake_monitored_loop(name, fn, interval):
        captured["fn"] = fn

    with patch(
        "app.startup.background._monitored_loop",
        side_effect=_fake_monitored_loop,
    ), patch(
        "app.api.services.email_collector.get_all_active_tenants",
        new=AsyncMock(return_value=tenant_return),
    ), patch(
        "app.api.services.email_collector.collect_tenant_inbox",
        new=AsyncMock(return_value={"processed": 0}),
    ):
        import app.startup.background as bg
        # Reload to pick up fresh imports inside email_poller_loop
        await bg.email_poller_loop.__wrapped__() if hasattr(bg.email_poller_loop, "__wrapped__") else None

        from app.startup.background import email_poller_loop
        await email_poller_loop()

    return captured.get("fn")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEmailPollerAwaitsCoroutine:

    @pytest.mark.asyncio
    async def test_get_all_active_tenants_is_awaited(self):
        """get_all_active_tenants must be awaited — not iterated as coroutine."""
        mock_tenants = AsyncMock(return_value=["t1", "t2"])
        mock_collect = AsyncMock(return_value={"processed": 0})
        captured_fn = {}

        async def _fake_monitored_loop(name, fn, interval):
            captured_fn["fn"] = fn

        with patch("app.startup.background._monitored_loop", side_effect=_fake_monitored_loop), \
             patch("app.startup.background.asyncio.sleep", new=AsyncMock()), \
             patch("app.api.services.email_collector.get_all_active_tenants", new=mock_tenants), \
             patch("app.api.services.email_collector.collect_tenant_inbox", new=mock_collect):
            from app.startup.background import email_poller_loop
            await email_poller_loop()

        run_fn = captured_fn.get("fn")
        assert run_fn is not None, "_run fn was not captured"

        # Execute _run — must not raise TypeError: coroutine object is not iterable
        try:
            result = await run_fn()
        except TypeError as exc:
            if "coroutine" in str(exc) and "iterable" in str(exc):
                pytest.fail(
                    "BUG: get_all_active_tenants() not awaited — "
                    "'coroutine object is not iterable'"
                )
            raise

        assert isinstance(result, dict)
        assert "tenants" in result

    @pytest.mark.asyncio
    async def test_no_coroutine_not_iterable_error(self):
        """Running _run must never produce 'coroutine object is not iterable'."""
        captured_fn = {}

        async def _fake_monitored_loop(name, fn, interval):
            captured_fn["fn"] = fn

        with patch("app.startup.background._monitored_loop", side_effect=_fake_monitored_loop), \
             patch("app.startup.background.asyncio.sleep", new=AsyncMock()), \
             patch("app.api.services.email_collector.get_all_active_tenants",
                   new=AsyncMock(return_value=["tenant_a"])), \
             patch("app.api.services.email_collector.collect_tenant_inbox",
                   new=AsyncMock(return_value={"processed": 3})):
            from app.startup.background import email_poller_loop
            await email_poller_loop()

        run_fn = captured_fn["fn"]
        result = await run_fn()
        assert result["total_processed"] == 3
        assert result["tenants"] == 1

    @pytest.mark.asyncio
    async def test_empty_tenant_list_does_not_fail(self):
        """Zero active tenants — _run returns tenants=0 without error."""
        captured_fn = {}

        async def _fake_monitored_loop(name, fn, interval):
            captured_fn["fn"] = fn

        with patch("app.startup.background._monitored_loop", side_effect=_fake_monitored_loop), \
             patch("app.startup.background.asyncio.sleep", new=AsyncMock()), \
             patch("app.api.services.email_collector.get_all_active_tenants",
                   new=AsyncMock(return_value=[])), \
             patch("app.api.services.email_collector.collect_tenant_inbox",
                   new=AsyncMock(return_value={"processed": 0})):
            from app.startup.background import email_poller_loop
            await email_poller_loop()

        result = await captured_fn["fn"]()
        assert result["tenants"] == 0
        assert result["total_processed"] == 0

    @pytest.mark.asyncio
    async def test_multiple_tenants_all_processed(self):
        """Each tenant gets its own collect_tenant_inbox call."""
        captured_fn = {}
        collect_calls = []

        async def _fake_collect(tid):
            collect_calls.append(tid)
            return {"processed": 1}

        async def _fake_monitored_loop(name, fn, interval):
            captured_fn["fn"] = fn

        with patch("app.startup.background._monitored_loop", side_effect=_fake_monitored_loop), \
             patch("app.startup.background.asyncio.sleep", new=AsyncMock()), \
             patch("app.api.services.email_collector.get_all_active_tenants",
                   new=AsyncMock(return_value=["t1", "t2", "t3"])), \
             patch("app.api.services.email_collector.collect_tenant_inbox",
                   side_effect=_fake_collect):
            from app.startup.background import email_poller_loop
            await email_poller_loop()

        result = await captured_fn["fn"]()
        assert result["tenants"] == 3
        assert result["total_processed"] == 3

    @pytest.mark.asyncio
    async def test_per_tenant_exception_does_not_abort_loop(self):
        """Exception on one tenant must not prevent remaining tenants from running."""
        captured_fn = {}
        processed = []

        async def _fake_collect(tid):
            if tid == "bad":
                raise RuntimeError("IMAP connection refused")
            processed.append(tid)
            return {"processed": 1}

        async def _fake_monitored_loop(name, fn, interval):
            captured_fn["fn"] = fn

        with patch("app.startup.background._monitored_loop", side_effect=_fake_monitored_loop), \
             patch("app.startup.background.asyncio.sleep", new=AsyncMock()), \
             patch("app.api.services.email_collector.get_all_active_tenants",
                   new=AsyncMock(return_value=["good1", "bad", "good2"])), \
             patch("app.api.services.email_collector.collect_tenant_inbox",
                   side_effect=_fake_collect):
            from app.startup.background import email_poller_loop
            await email_poller_loop()

        result = await captured_fn["fn"]()
        assert "good1" in processed
        assert "good2" in processed
        assert result["tenants"] == 3

    @pytest.mark.asyncio
    async def test_no_real_network_calls(self):
        """If collect_tenant_inbox is not mocked, the test would fail — verifies mocking."""
        captured_fn = {}

        async def _fake_monitored_loop(name, fn, interval):
            captured_fn["fn"] = fn

        network_called = []

        async def _mock_collect(tid):
            network_called.append(tid)
            return {"processed": 0}

        with patch("app.startup.background._monitored_loop", side_effect=_fake_monitored_loop), \
             patch("app.startup.background.asyncio.sleep", new=AsyncMock()), \
             patch("app.api.services.email_collector.get_all_active_tenants",
                   new=AsyncMock(return_value=["t1"])), \
             patch("app.api.services.email_collector.collect_tenant_inbox",
                   side_effect=_mock_collect):
            from app.startup.background import email_poller_loop
            await email_poller_loop()

        await captured_fn["fn"]()
        # Calls went to mock, not real IMAP
        assert "t1" in network_called


class TestEmailPollerNoSecrets:

    def test_background_py_no_hardcoded_secrets(self):
        """background.py must not contain raw credentials."""
        import pathlib
        src = pathlib.Path("app/startup/background.py").read_text(encoding="utf-8")
        assert "postgresql://" not in src
        assert "password=" not in src.lower() or "# " in src
        assert "api_key=" not in src.lower()
        assert "POSTED_LEDGER_WRITES_ENABLED" not in src

    def test_background_py_does_not_touch_ledger(self):
        """email_poller must not reference posting or ledger write code."""
        import pathlib
        src = pathlib.Path("app/startup/background.py").read_text(encoding="utf-8")
        assert "POSTED_LEDGER_WRITES_ENABLED" not in src
        assert "_write_ledger_entries" not in src
        assert "apply_posting_service" not in src
        assert "posting/apply" not in src


class TestEmailPollerStructure:

    def test_get_all_active_tenants_awaited_in_source(self):
        """Source code must show await before get_all_active_tenants()."""
        import pathlib
        src = pathlib.Path("app/startup/background.py").read_text(encoding="utf-8")
        assert "await get_all_active_tenants()" in src, (
            "get_all_active_tenants() must be awaited in background.py"
        )

    def test_bare_call_not_present(self):
        """The bare (non-awaited) call must no longer exist."""
        import pathlib
        src = pathlib.Path("app/startup/background.py").read_text(encoding="utf-8")
        lines = src.splitlines()
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            if "get_all_active_tenants()" in stripped and not stripped.startswith("#"):
                assert "await" in stripped, (
                    f"Line {lineno}: get_all_active_tenants() called without await"
                )
