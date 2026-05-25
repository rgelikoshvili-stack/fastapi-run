"""tests/unit/test_h70a_g8b_posting_log_source.py

Unit tests for H70A-G8B: posting_log source traceability in _write_ledger_entries.
No DB, no network. All asyncpg connections mocked.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_conn(fetchval_side=None, fetchval_return=None):
    conn = AsyncMock()
    if fetchval_side is not None:
        conn.fetchval = AsyncMock(side_effect=fetchval_side)
    else:
        conn.fetchval = AsyncMock(return_value=fetchval_return)
    conn.fetch    = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute  = AsyncMock()
    tx = AsyncMock()
    tx.__aenter__ = AsyncMock(return_value=tx)
    tx.__aexit__  = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)
    return conn


def _make_draft(draft_id=42, lines=None):
    if lines is None:
        lines = [
            {"account_code": "1110", "debit": 500.0, "credit": 0.0,   "label": "DR"},
            {"account_code": "3100", "debit": 0.0,   "credit": 500.0, "label": "CR"},
        ]
    return {
        "id": draft_id,
        "date": "2026-05-25",
        "description": "G8B test",
        "currency": "GEL",
        "lines": lines,
    }


_TEST_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


# ── helpers to inspect execute calls ─────────────────────────────────────────

def _source_types_inserted(conn) -> list[str]:
    """Return the source_type strings from all INSERT INTO journal_entry_sources calls."""
    result = []
    for call in conn.execute.call_args_list:
        sql_arg = call.args[0] if call.args else ""
        if "journal_entry_sources" in sql_arg:
            # source_type is the 3rd positional arg after (tenant_id, header_id, ...)
            # SQL: VALUES (%s, %s, 'journal_draft', %s)  → literal in SQL
            # OR: VALUES (%s, %s, 'posting_log', %s)     → literal in SQL
            if "'journal_draft'" in sql_arg or "journal_draft" in sql_arg:
                result.append("journal_draft")
            elif "'posting_log'" in sql_arg or "posting_log" in sql_arg:
                result.append("posting_log")
    return result


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestPostingLogSourceTraceability:

    @pytest.mark.asyncio
    async def test_first_write_creates_journal_draft_source(self):
        """Without posting_log_id, exactly one source row is written: journal_draft."""
        conn = _make_conn(fetchval_side=[None, "header-uuid"])
        with patch("app.api.services.posting_service.log_event"):
            from app.api.services.posting_service import _write_ledger_entries
            await _write_ledger_entries(
                conn, _make_draft(), {}, "t1", "mock", "hash1"
            )
        src_types = _source_types_inserted(conn)
        assert "journal_draft" in src_types
        assert "posting_log" not in src_types

    @pytest.mark.asyncio
    async def test_first_write_creates_posting_log_source_when_id_provided(self):
        """When payload has posting_log_id, both journal_draft and posting_log sources written."""
        conn = _make_conn(fetchval_side=[None, "header-uuid"])
        payload = {"posting_log_id": _TEST_UUID, "exchange_rate": 1.0}
        with patch("app.api.services.posting_service.log_event"):
            from app.api.services.posting_service import _write_ledger_entries
            await _write_ledger_entries(
                conn, _make_draft(), payload, "t1", "mock", "hash2"
            )
        src_types = _source_types_inserted(conn)
        assert "journal_draft" in src_types
        assert "posting_log" in src_types

    @pytest.mark.asyncio
    async def test_first_write_without_posting_log_id_still_succeeds(self):
        """Omitting posting_log_id must not raise an error."""
        conn = _make_conn(fetchval_side=[None, "header-uuid"])
        with patch("app.api.services.posting_service.log_event"):
            from app.api.services.posting_service import _write_ledger_entries
            await _write_ledger_entries(
                conn, _make_draft(), {}, "t1", "mock", "hash3"
            )
        assert conn.execute.call_count >= 1  # at least journal_draft source

    @pytest.mark.asyncio
    async def test_invalid_posting_log_id_is_silently_ignored(self):
        """A non-UUID string in payload.posting_log_id must not raise; no posting_log row written."""
        conn = _make_conn(fetchval_side=[None, "header-uuid"])
        payload = {"posting_log_id": "not-a-uuid"}
        with patch("app.api.services.posting_service.log_event"):
            from app.api.services.posting_service import _write_ledger_entries
            await _write_ledger_entries(
                conn, _make_draft(), payload, "t1", "mock", "hash4"
            )
        src_types = _source_types_inserted(conn)
        assert "journal_draft" in src_types
        assert "posting_log" not in src_types

    @pytest.mark.asyncio
    async def test_retry_does_not_duplicate_posting_log_source(self):
        """If journal_draft source already exists, the entire write is skipped (idempotent).
        This prevents duplicate posting_log sources on retry.
        """
        conn = _make_conn(fetchval_return="existing-uuid")  # pre-check finds existing source
        events = []
        with patch("app.api.services.posting_service.log_event",
                   side_effect=lambda *a, **kw: events.append(a[0])):
            from app.api.services.posting_service import _write_ledger_entries
            payload = {"posting_log_id": _TEST_UUID}
            await _write_ledger_entries(
                conn, _make_draft(), payload, "t1", "mock", "hash5"
            )
        # No INSERTs at all — skipped before write
        conn.execute.assert_not_called()
        assert "ledger_write_skipped" in events

    @pytest.mark.asyncio
    async def test_tenant_isolation_posting_log_source_uses_tenant_id(self):
        """The posting_log source INSERT must be scoped to the provided tenant_id."""
        conn = _make_conn(fetchval_side=[None, "header-uuid"])
        tenant = "tenant_isolation_test"
        payload = {"posting_log_id": _TEST_UUID}
        with patch("app.api.services.posting_service.log_event"):
            from app.api.services.posting_service import _write_ledger_entries
            await _write_ledger_entries(
                conn, _make_draft(), payload, tenant, "mock", "hash6"
            )
        # Find the posting_log INSERT call and verify tenant is the first arg
        for call in conn.execute.call_args_list:
            sql_arg = call.args[0] if call.args else ""
            if "journal_entry_sources" in sql_arg and "posting_log" in sql_arg:
                positional_args = call.args[1:]
                assert tenant in positional_args, (
                    f"tenant_id {tenant!r} not found in posting_log INSERT args: {positional_args}"
                )
                break
        else:
            pytest.fail("posting_log INSERT not found in execute calls")

    @pytest.mark.asyncio
    async def test_posting_log_source_id_matches_provided_uuid(self):
        """The source_id for posting_log row must equal the provided posting_log_id."""
        conn = _make_conn(fetchval_side=[None, "header-uuid"])
        pl_id = str(uuid.uuid4())
        payload = {"posting_log_id": pl_id}
        with patch("app.api.services.posting_service.log_event"):
            from app.api.services.posting_service import _write_ledger_entries
            await _write_ledger_entries(
                conn, _make_draft(), payload, "t1", "mock", "hash7"
            )
        # The source_id arg (4th positional arg to execute after sql, tenant, header_id) = pl_id
        for call in conn.execute.call_args_list:
            sql_arg = call.args[0] if call.args else ""
            if "journal_entry_sources" in sql_arg and "posting_log" in sql_arg:
                positional_args = call.args[1:]
                assert str(pl_id) in [str(a) for a in positional_args], (
                    f"posting_log_id {pl_id!r} not in args: {positional_args}"
                )
                break
        else:
            pytest.fail("posting_log INSERT not found in execute calls")

    @pytest.mark.asyncio
    async def test_header_posting_log_id_field_populated(self):
        """When posting_log_id is given, it must appear in the header INSERT args."""
        conn = _make_conn(fetchval_side=[None, "header-uuid"])
        pl_id = _TEST_UUID
        payload = {"posting_log_id": pl_id}
        with patch("app.api.services.posting_service.log_event"):
            from app.api.services.posting_service import _write_ledger_entries
            await _write_ledger_entries(
                conn, _make_draft(), payload, "t1", "mock", "hash8"
            )
        # Check fetchval (header INSERT) includes the UUID
        header_call = conn.fetchval.call_args_list[-1]
        all_args = list(header_call.args[1:])
        uuid_args = [a for a in all_args if isinstance(a, uuid.UUID)]
        assert len(uuid_args) == 1
        assert str(uuid_args[0]) == pl_id.lower()

    @pytest.mark.asyncio
    async def test_header_posting_log_id_is_null_when_not_provided(self):
        """When no posting_log_id in payload, header INSERT gets None for that column."""
        conn = _make_conn(fetchval_side=[None, "header-uuid"])
        with patch("app.api.services.posting_service.log_event"):
            from app.api.services.posting_service import _write_ledger_entries
            await _write_ledger_entries(
                conn, _make_draft(), {}, "t1", "mock", "hash9"
            )
        header_call = conn.fetchval.call_args_list[-1]
        all_args = list(header_call.args[1:])
        # Last arg is posting_log_id (None when not provided)
        assert all_args[-1] is None

    def test_structural_posting_log_source_in_write_fn(self):
        """Source code of _write_ledger_entries references posting_log source insert."""
        import inspect
        from app.api.services import posting_service
        src = inspect.getsource(posting_service._write_ledger_entries)
        assert "posting_log" in src
        assert "posting_log_id" in src


# ── Verify existing REQ tests are unaffected ─────────────────────────────────

class TestExistingReqsUnaffected:
    def test_all_five_req_symbols_still_present(self):
        import inspect
        from app.api.services import posting_service
        src = inspect.getsource(posting_service)
        assert "ledger_write_skipped" in src
        assert "ledger_write_failed" in src
        assert "get_ledger_recovery_candidates" in src
        assert "retry_ledger_write" in src
        assert "ledger_write_recovered" in src
