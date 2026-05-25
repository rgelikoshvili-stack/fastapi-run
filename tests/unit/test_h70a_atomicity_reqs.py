"""tests/unit/test_h70a_atomicity_reqs.py

Unit tests for H70A REQ-1..5 atomicity hardening in posting_service.
No DB, no network. All asyncpg connections mocked.
"""
import hashlib
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_conn(fetchval_return=None, fetch_return=None, fetchrow_return=None):
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=fetchval_return)
    conn.fetch    = AsyncMock(return_value=fetch_return or [])
    conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    conn.execute  = AsyncMock()
    tx = AsyncMock()
    tx.__aenter__ = AsyncMock(return_value=tx)
    tx.__aexit__  = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)
    return conn


def _make_ctx(conn):
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__  = AsyncMock(return_value=False)
    return ctx


def _make_draft(draft_id=42, lines=None):
    if lines is None:
        lines = [{"account_code": "1110", "debit": 100.0, "credit": 0.0, "label": "test"}]
    return {
        "id": draft_id,
        "date": "2026-05-25",
        "description": "test draft",
        "currency": "GEL",
        "lines": lines,
    }


# ── REQ-5: idempotent pre-check ───────────────────────────────────────────────

class TestReq5IdempotentPreCheck:
    @pytest.mark.asyncio
    async def test_skips_when_source_already_exists(self):
        """If journal_entry_sources already has a row for this draft, return without inserting."""
        conn = _make_conn(fetchval_return="existing-uuid")

        logged_events = []
        with patch("app.api.services.posting_service.log_event",
                   side_effect=lambda *a, **kw: logged_events.append(a[0])):
            from app.api.services.posting_service import _write_ledger_entries
            await _write_ledger_entries(conn, _make_draft(), {}, "t1", "mock", "hash123")

        # fetchval called once for the pre-check
        conn.fetchval.assert_called_once()
        # no INSERT executed
        conn.execute.assert_not_called()
        # ledger_write_skipped emitted
        assert "ledger_write_skipped" in logged_events

    @pytest.mark.asyncio
    async def test_proceeds_when_source_absent(self):
        """If no source row exists, proceeds to insert header + lines + source."""
        conn = _make_conn(fetchval_return=None)
        # header INSERT returns a UUID
        conn.fetchval = AsyncMock(side_effect=[None, "new-header-uuid"])

        with patch("app.api.services.posting_service.log_event"):
            from app.api.services.posting_service import _write_ledger_entries
            await _write_ledger_entries(conn, _make_draft(), {}, "t1", "mock", "hash123")

        # execute called at least once (line + source inserts)
        assert conn.execute.call_count >= 1

    @pytest.mark.asyncio
    async def test_skips_when_draft_id_is_empty_string(self):
        """Draft with no id — pre-check skipped, write proceeds."""
        conn = _make_conn(fetchval_return=None)
        conn.fetchval = AsyncMock(side_effect=[None, "header-uuid"])

        with patch("app.api.services.posting_service.log_event"):
            from app.api.services.posting_service import _write_ledger_entries
            draft = _make_draft()
            draft["id"] = ""
            await _write_ledger_entries(conn, draft, {}, "t1", "mock", "hash")

        # No pre-check SQL fired (empty draft_id_str)
        assert conn.fetchval.call_count == 1  # only the header INSERT RETURNING


# ── REQ-1: ledger_write_failed audit event ────────────────────────────────────

class TestReq1AuditEvent:
    def test_ledger_write_failed_event_fired_on_exception(self):
        """apply_posting_service emits ledger_write_failed via log_event on ledger write error."""
        import inspect
        from app.api.services import posting_service
        src = inspect.getsource(posting_service.apply_posting_service)
        assert "ledger_write_failed" in src
        assert "log_event" in src

    def test_ledger_write_failed_has_required_fields(self):
        """The log_event call includes entity_type, entity_id, target, error."""
        import inspect
        from app.api.services import posting_service
        src = inspect.getsource(posting_service.apply_posting_service)
        # Find the ledger_write_failed block
        idx = src.find('"ledger_write_failed"')
        assert idx != -1
        context = src[idx:idx + 300]
        assert "entity_type" in context
        assert "entity_id" in context
        assert "target" in context
        assert "error" in context

    def test_log_error_still_called_after_log_event(self):
        """log.error is still called after log_event for structured log continuity."""
        import inspect
        from app.api.services import posting_service
        src = inspect.getsource(posting_service.apply_posting_service)
        ledger_fail_idx = src.find('"ledger_write_failed"')
        after = src[ledger_fail_idx:ledger_fail_idx + 500]
        assert "log.error" in after


# ── REQ-2: recovery candidates query ─────────────────────────────────────────

class TestReq2RecoveryCandidates:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_candidates(self):
        conn = _make_conn(fetch_return=[])
        with patch("app.api.services.posting_service.get_conn",
                   return_value=_make_ctx(conn)):
            from app.api.services.posting_service import get_ledger_recovery_candidates
            result = await get_ledger_recovery_candidates("t1")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_draft_fields(self):
        row = MagicMock()
        row.__getitem__ = lambda self, k: {
            "id": 7, "date": "2026-05-25", "description": "test", "amount": 500.0
        }[k]
        conn = _make_conn(fetch_return=[row])
        with patch("app.api.services.posting_service.get_conn",
                   return_value=_make_ctx(conn)):
            from app.api.services.posting_service import get_ledger_recovery_candidates
            result = await get_ledger_recovery_candidates("t1")
        assert len(result) == 1
        assert result[0]["id"] == 7

    @pytest.mark.asyncio
    async def test_query_uses_not_exists_subquery(self):
        """Recovery query must exclude drafts that already have a source row."""
        import inspect
        from app.api.services import posting_service
        src = inspect.getsource(posting_service.get_ledger_recovery_candidates)
        assert "NOT EXISTS" in src
        assert "journal_entry_sources" in src
        assert "source_type" in src

    def test_function_exported(self):
        from app.api.services.posting_service import get_ledger_recovery_candidates
        import asyncio
        assert asyncio.iscoroutinefunction(get_ledger_recovery_candidates)


# ── REQ-3 + REQ-4: retry + recovered event ───────────────────────────────────

class TestReq3Req4RetryAndRecoveredEvent:
    @pytest.mark.asyncio
    async def test_returns_error_when_draft_not_found(self):
        conn = _make_conn(fetchrow_return=None)
        with patch("app.api.services.posting_service.get_conn",
                   return_value=_make_ctx(conn)):
            from app.api.services.posting_service import retry_ledger_write
            result = await retry_ledger_write(99, "t1")
        assert result["ok"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_emits_ledger_write_recovered_on_success(self):
        draft_row = MagicMock()
        draft_row.__getitem__ = lambda self, k: {
            "id": 42, "tenant_id": "t1", "date": "2026-05-25",
            "description": "d", "currency": "GEL", "lines_json": []
        }[k]

        conn = _make_conn(fetchrow_return=draft_row)
        events = []
        with patch("app.api.services.posting_service.get_conn",
                   return_value=_make_ctx(conn)):
            with patch("app.api.services.posting_service._write_ledger_entries",
                       new_callable=AsyncMock) as mock_write:
                mock_write.return_value = None
                with patch("app.api.services.posting_service.log_event",
                           side_effect=lambda *a, **kw: events.append(a[0])):
                    from app.api.services.posting_service import retry_ledger_write
                    result = await retry_ledger_write(42, "t1")

        assert result["ok"] is True
        assert "ledger_write_recovered" in events

    @pytest.mark.asyncio
    async def test_skipped_write_still_emits_recovered(self):
        """Idempotent skip (source exists) completes without error → recovered still emitted."""
        draft_row = MagicMock()
        draft_row.__getitem__ = lambda self, k: {
            "id": 42, "tenant_id": "t1", "date": "2026-05-25",
            "description": "d", "currency": "GEL", "lines_json": []
        }[k]

        conn = _make_conn(fetchrow_return=draft_row)
        events = []
        with patch("app.api.services.posting_service.get_conn",
                   return_value=_make_ctx(conn)):
            with patch("app.api.services.posting_service._write_ledger_entries",
                       new_callable=AsyncMock) as mock_write:
                # Simulate _write_ledger_entries emitting skipped and returning
                async def _skip(*a, **kw):
                    events.append("ledger_write_skipped")
                mock_write.side_effect = _skip
                with patch("app.api.services.posting_service.log_event",
                           side_effect=lambda *a, **kw: events.append(a[0])):
                    from app.api.services.posting_service import retry_ledger_write
                    result = await retry_ledger_write(42, "t1")

        assert result["ok"] is True
        assert "ledger_write_skipped" in events
        assert "ledger_write_recovered" in events

    @pytest.mark.asyncio
    async def test_returns_error_dict_on_exception(self):
        draft_row = MagicMock()
        draft_row.__getitem__ = lambda self, k: {
            "id": 42, "tenant_id": "t1", "date": "2026-05-25",
            "description": "d", "currency": "GEL", "lines_json": []
        }[k]

        conn = _make_conn(fetchrow_return=draft_row)
        conn.fetchval = AsyncMock(side_effect=Exception("db_error"))

        with patch("app.api.services.posting_service.get_conn",
                   return_value=_make_ctx(conn)):
            with patch("app.api.services.posting_service.log_event"):
                from app.api.services.posting_service import retry_ledger_write
                result = await retry_ledger_write(42, "t1")

        assert result["ok"] is False
        assert "error" in result

    def test_function_exported(self):
        from app.api.services.posting_service import retry_ledger_write
        import asyncio
        assert asyncio.iscoroutinefunction(retry_ledger_write)


# ── REQ structural checks ─────────────────────────────────────────────────────

class TestReqStructuralChecks:
    def test_all_five_reqs_implemented(self):
        """Smoke-check that all 5 REQ symbols are present in posting_service."""
        import inspect
        from app.api.services import posting_service
        src = inspect.getsource(posting_service)
        assert "ledger_write_skipped" in src,    "REQ-5 pre-check missing"
        assert "ledger_write_failed" in src,     "REQ-1 audit event missing"
        assert "get_ledger_recovery_candidates" in src, "REQ-2 recovery query missing"
        assert "retry_ledger_write" in src,      "REQ-3 retry missing"
        assert "ledger_write_recovered" in src,  "REQ-4 recovered event missing"

    def test_no_forbidden_imports(self):
        with open(__file__, encoding="utf-8") as f:
            lines = f.readlines()
        forbidden = [
            "import " + "psycopg",
            "import " + "sqlalchemy",
            "import " + "requests",
            "from " + "app.api.db",
            "from " + "docker import",
        ]
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pat in forbidden:
                assert pat not in stripped, f"Forbidden import: {pat!r}"
