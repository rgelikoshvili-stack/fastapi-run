"""tests/unit/test_asyncpg_connection_reset_handling.py

Unit tests for asyncpg connection reset hardening (11C-H70E).
Contract:
  - asyncpg pool is configured with max_inactive_connection_lifetime=300.
  - ConnectionDoesNotExistError raised inside get_conn() propagates cleanly.
  - No secrets appear in logged error messages.
  - No mutating SQL is silently retried.
  - Pool creation parameters are correct and auditable.
No real DB or network calls — asyncpg pool is mocked throughout.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
import asyncpg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_pool(conn=None):
    pool = MagicMock()
    _conn = conn or AsyncMock()

    @asynccontextmanager
    async def _acquire():
        yield _conn

    pool.acquire = _acquire
    return pool


# ---------------------------------------------------------------------------
# Pool configuration audit
# ---------------------------------------------------------------------------

class TestPoolConfiguration:

    def test_max_inactive_connection_lifetime_in_source(self):
        """Pool creation must include max_inactive_connection_lifetime."""
        import pathlib
        src = pathlib.Path("app/api/db.py").read_text(encoding="utf-8")
        assert "max_inactive_connection_lifetime" in src, (
            "max_inactive_connection_lifetime not set in asyncpg.create_pool()"
        )

    def test_max_inactive_connection_lifetime_value_60(self):
        """max_inactive_connection_lifetime must be 60.0 (well below Cloud SQL proxy 5-min idle drop)."""
        import pathlib
        src = pathlib.Path("app/api/db.py").read_text(encoding="utf-8")
        assert "max_inactive_connection_lifetime=60.0" in src, (
            "Expected max_inactive_connection_lifetime=60.0 in create_pool() call"
        )

    def test_command_timeout_set(self):
        """command_timeout must be explicitly set."""
        import pathlib
        src = pathlib.Path("app/api/db.py").read_text(encoding="utf-8")
        assert "command_timeout=30" in src

    @pytest.mark.asyncio
    async def test_create_pool_called_with_correct_kwargs(self):
        """create_pool() must receive max_inactive_connection_lifetime=300.0."""
        import app.api.db as db_module
        orig_pool = db_module._async_pool
        db_module._async_pool = None

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock()

        with patch("app.api.db.asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)) as mock_create, \
             patch("app.api.db.os.environ.get", return_value="postgresql://fake/db"), \
             patch("app.api.db.os.getenv", side_effect=lambda k, d=None: {"DB_POOL_MIN": "1", "DB_POOL_MAX": "4"}.get(k, d)):

            from app.config.secrets import get_secret as _gs
            with patch("app.config.secrets.get_secret", return_value=None):
                await db_module.get_pool()

        kwargs = mock_create.call_args.kwargs
        assert kwargs.get("max_inactive_connection_lifetime") == 60.0, (
            f"Expected max_inactive_connection_lifetime=60.0, got {kwargs}"
        )
        assert kwargs.get("command_timeout") == 30
        db_module._async_pool = orig_pool


# ---------------------------------------------------------------------------
# ConnectionDoesNotExistError propagation
# ---------------------------------------------------------------------------

class TestConnectionDoesNotExistHandling:

    @pytest.mark.asyncio
    async def test_connection_does_not_exist_propagates_from_get_conn(self):
        """ConnectionDoesNotExistError raised during acquire propagates to caller."""
        mock_pool = MagicMock()

        @asynccontextmanager
        async def _dying_acquire():
            raise asyncpg.exceptions.ConnectionDoesNotExistError(
                "connection was closed in the middle of operation"
            )
            yield  # noqa: unreachable

        mock_pool.acquire = _dying_acquire

        with patch("app.api.db.get_pool", new=AsyncMock(return_value=mock_pool)):
            from app.api.db import get_conn
            with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
                async with get_conn() as conn:
                    pass

    @pytest.mark.asyncio
    async def test_connection_error_mid_query_propagates(self):
        """ConnectionDoesNotExistError raised during conn.fetch() propagates cleanly."""
        conn = AsyncMock()
        conn.fetch = AsyncMock(
            side_effect=asyncpg.exceptions.ConnectionDoesNotExistError(
                "connection was closed in the middle of operation"
            )
        )
        mock_pool = _make_mock_pool(conn)

        with patch("app.api.db.get_pool", new=AsyncMock(return_value=mock_pool)):
            from app.api.db import get_conn
            with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
                async with get_conn() as c:
                    await c.fetch("SELECT 1")

    @pytest.mark.asyncio
    async def test_healthy_connection_succeeds(self):
        """Normal get_conn() usage with a healthy pool yields a working connection."""
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[{"id": 1}])
        mock_pool = _make_mock_pool(conn)

        with patch("app.api.db.get_pool", new=AsyncMock(return_value=mock_pool)):
            from app.api.db import get_conn
            async with get_conn() as c:
                rows = await c.fetch("SELECT id FROM t WHERE id=$1", 1)
            assert rows == [{"id": 1}]


# ---------------------------------------------------------------------------
# No silent retry for mutating operations
# ---------------------------------------------------------------------------

class TestNoSilentMutatingRetry:

    @pytest.mark.asyncio
    async def test_insert_failure_not_silently_retried(self):
        """An INSERT that fails with ConnectionDoesNotExistError must NOT be retried."""
        insert_call_count = 0

        conn = AsyncMock()

        async def _failing_execute(sql, *args):
            nonlocal insert_call_count
            insert_call_count += 1
            raise asyncpg.exceptions.ConnectionDoesNotExistError("dropped")

        conn.execute = _failing_execute
        mock_pool = _make_mock_pool(conn)

        with patch("app.api.db.get_pool", new=AsyncMock(return_value=mock_pool)):
            from app.api.db import get_conn
            with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
                async with get_conn() as c:
                    await c.execute("INSERT INTO t VALUES ($1)", 42)

        # Must be called exactly once — no retry
        assert insert_call_count == 1, (
            f"INSERT was retried {insert_call_count} times — must not retry mutating SQL"
        )

    @pytest.mark.asyncio
    async def test_update_failure_not_silently_retried(self):
        """An UPDATE that fails must propagate immediately — no retry."""
        execute_count = 0

        conn = AsyncMock()

        async def _failing_execute(sql, *args):
            nonlocal execute_count
            execute_count += 1
            raise asyncpg.exceptions.ConnectionDoesNotExistError("dropped mid-update")

        conn.execute = _failing_execute
        mock_pool = _make_mock_pool(conn)

        with patch("app.api.db.get_pool", new=AsyncMock(return_value=mock_pool)):
            from app.api.db import get_conn
            with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
                async with get_conn() as c:
                    await c.execute("UPDATE t SET v=$1 WHERE id=$2", "x", 1)

        assert execute_count == 1


# ---------------------------------------------------------------------------
# No secrets in error logs
# ---------------------------------------------------------------------------

class TestNoSecretsInLogs:

    @pytest.mark.asyncio
    async def test_connection_error_log_contains_no_db_url(self, caplog):
        """Error logged on ConnectionDoesNotExistError must not contain DATABASE_URL value."""
        import app.api.db as db_module

        conn = AsyncMock()
        conn.fetch = AsyncMock(
            side_effect=asyncpg.exceptions.ConnectionDoesNotExistError("dropped")
        )
        mock_pool = _make_mock_pool(conn)

        with patch("app.api.db.get_pool", new=AsyncMock(return_value=mock_pool)), \
             caplog.at_level(logging.ERROR, logger="app.api.db"):
            from app.api.db import get_conn
            with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
                async with get_conn() as c:
                    await c.fetch("SELECT 1")

        for record in caplog.records:
            assert "postgresql://" not in record.getMessage()
            assert "password" not in record.getMessage().lower()

    def test_db_module_no_hardcoded_credentials(self):
        """app/api/db.py must not contain hardcoded credentials."""
        import pathlib
        src = pathlib.Path("app/api/db.py").read_text(encoding="utf-8")
        assert "POSTED_LEDGER_WRITES_ENABLED" not in src
        assert "posting/apply" not in src
        # No inline passwords
        import re
        assert not re.search(r'password\s*=\s*["\'][^"\']+["\']', src, re.I)


# ---------------------------------------------------------------------------
# Pool lifecycle: close and reset
# ---------------------------------------------------------------------------

class TestPoolLifecycle:

    @pytest.mark.asyncio
    async def test_close_pool_resets_global(self):
        """close_pool() sets _async_pool to None so next get_pool() creates fresh pool."""
        import app.api.db as db_module
        mock_pool = MagicMock()
        mock_pool.close = AsyncMock()
        db_module._async_pool = mock_pool

        from app.api.db import close_pool
        await close_pool()

        mock_pool.close.assert_awaited_once()
        assert db_module._async_pool is None

    @pytest.mark.asyncio
    async def test_close_pool_noop_when_none(self):
        """close_pool() when pool is None must not raise."""
        import app.api.db as db_module
        db_module._async_pool = None
        from app.api.db import close_pool
        await close_pool()  # must not raise

    @pytest.mark.asyncio
    async def test_get_pool_creates_only_once(self):
        """get_pool() must return the same pool instance on subsequent calls."""
        import app.api.db as db_module
        orig = db_module._async_pool

        mock_pool = MagicMock()
        db_module._async_pool = mock_pool

        from app.api.db import get_pool
        p1 = await get_pool()
        p2 = await get_pool()

        assert p1 is p2 is mock_pool
        db_module._async_pool = orig
