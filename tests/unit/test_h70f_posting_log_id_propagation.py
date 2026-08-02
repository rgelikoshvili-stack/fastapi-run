"""tests/unit/test_h70f_posting_log_id_propagation.py

H70F — Caller-level tests: apply_posting_service must inject posting_log_id
into the payload dict before calling _write_ledger_entries, so that
journal_entry_sources receives source_type='posting_log' during real posting.

No DB, no network. All asyncpg connections mocked.
"""
import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── constants ─────────────────────────────────────────────────────────────────

_FAKE_LOG_ID = "b1a2c3d4-e5f6-7890-abcd-ef0123456789"
_DRAFT_ID = 999
_TENANT = "tenant_h70f_test"

_DRAFT_ROW = {
    "id": _DRAFT_ID,
    "tenant_id": _TENANT,
    "date": "2026-06-18",
    "description": "H70F propagation test",
    "partner": "Test Supplier GEO",
    "amount": 500.0,
    "status": "approved",
    "currency": "GEL",
    "lines_json": [
        {"account_code": "7110", "debit": 500.0, "credit": 0.0, "label": "Salary Expense"},
        {"account_code": "3310", "debit": 0.0, "credit": 500.0, "label": "Salary Payable"},
    ],
}


# ── helpers ───────────────────────────────────────────────────────────────────

class _TrMock:
    """asyncpg transaction stub — supports both explicit start/commit and async ctx mgr."""
    async def start(self): pass
    async def commit(self): pass
    async def rollback(self): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False


def _make_conn(fetchrow_side=None, fetchval_side=None):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(side_effect=list(fetchrow_side or []))
    conn.fetchval = AsyncMock(side_effect=list(fetchval_side or []))
    conn.execute = AsyncMock()
    conn.transaction = MagicMock(return_value=_TrMock())
    return conn


@asynccontextmanager
async def _conn_ctx(conn):
    yield conn


def _patches(conn, captured_write, ledger_enabled="true"):
    return [
        patch("app.api.services.posting_service.get_conn", lambda: _conn_ctx(conn)),
        patch("app.api.services.posting_service._write_ledger_entries",
              side_effect=captured_write),
        patch("app.api.services.posting_service.log_event"),
        patch("app.api.services.posting_service.structured_log"),
        patch.dict(os.environ, {"POSTED_LEDGER_WRITES_ENABLED": ledger_enabled}),
    ]


# ── H70F propagation tests ────────────────────────────────────────────────────

class TestH70FPostingLogIdPropagation:
    """Verify apply_posting_service injects posting_log_id before _write_ledger_entries."""

    @pytest.mark.asyncio
    async def test_posting_log_id_injected_into_ledger_payload(self):
        """Core H70F assertion: payload passed to _write_ledger_entries carries posting_log_id."""
        conn = _make_conn(
            fetchrow_side=[_DRAFT_ROW, None],      # draft row, then no existing posting
            fetchval_side=[None, _FAKE_LOG_ID],    # no period lock, then posting_logs INSERT id
        )
        captured = {}

        async def _capture(c, draft, payload, tenant_id, target, entry_hash):
            captured["payload"] = dict(payload)

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in _patches(conn, _capture):
                stack.enter_context(p)
            from app.api.services.posting_service import apply_posting_service
            result = await apply_posting_service(
                draft_id=_DRAFT_ID, target="mock",
                tenant_id=_TENANT, force=True, actor="test",
            )

        assert result["ok"] is True, f"posting failed unexpectedly: {result}"
        assert "payload" in captured, "_write_ledger_entries was never called"
        assert "posting_log_id" in captured["payload"], (
            "H70F FIX REGRESSION: payload['posting_log_id'] not set before _write_ledger_entries"
        )
        assert captured["payload"]["posting_log_id"] == str(_FAKE_LOG_ID)

    @pytest.mark.asyncio
    async def test_posting_log_id_value_is_str(self):
        """posting_log_id in the payload must be a str, not int or UUID object."""
        conn = _make_conn(
            fetchrow_side=[_DRAFT_ROW, None],
            fetchval_side=[None, _FAKE_LOG_ID],
        )
        captured = {}

        async def _capture(c, draft, payload, tenant_id, target, entry_hash):
            captured["pl_id"] = payload.get("posting_log_id")

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in _patches(conn, _capture):
                stack.enter_context(p)
            from app.api.services.posting_service import apply_posting_service
            await apply_posting_service(
                _DRAFT_ID, "mock", _TENANT, force=True, actor="test"
            )

        val = captured.get("pl_id")
        assert isinstance(val, str), f"posting_log_id must be str, got {type(val)}: {val!r}"
        assert val == str(_FAKE_LOG_ID)

    @pytest.mark.asyncio
    async def test_posting_log_id_not_injected_when_log_id_none(self):
        """ON CONFLICT DO NOTHING returns None — posting_log_id must NOT be set in payload."""
        conn = _make_conn(
            fetchrow_side=[_DRAFT_ROW, None],
            fetchval_side=[None, None],   # posting_logs INSERT → None (conflict)
        )
        captured = {}

        async def _capture(c, draft, payload, tenant_id, target, entry_hash):
            captured["has_key"] = "posting_log_id" in payload

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in _patches(conn, _capture):
                stack.enter_context(p)
            from app.api.services.posting_service import apply_posting_service
            await apply_posting_service(
                _DRAFT_ID, "mock", _TENANT, force=True, actor="test"
            )

        assert not captured.get("has_key", False), (
            "posting_log_id must NOT be injected when log_id is None"
        )

    @pytest.mark.asyncio
    async def test_write_ledger_called_exactly_once_on_success(self):
        """_write_ledger_entries is called exactly once per successful posting."""
        conn = _make_conn(
            fetchrow_side=[_DRAFT_ROW, None],
            fetchval_side=[None, _FAKE_LOG_ID],
        )
        call_count = {"n": 0}

        async def _capture(c, draft, payload, tenant_id, target, entry_hash):
            call_count["n"] += 1

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in _patches(conn, _capture):
                stack.enter_context(p)
            from app.api.services.posting_service import apply_posting_service
            result = await apply_posting_service(
                _DRAFT_ID, "mock", _TENANT, force=True, actor="test"
            )

        assert result["ok"] is True
        assert call_count["n"] == 1, f"_write_ledger_entries must be called once, got {call_count['n']}"

    @pytest.mark.asyncio
    async def test_ledger_not_written_when_flag_disabled(self):
        """When POSTED_LEDGER_WRITES_ENABLED=false, _write_ledger_entries is NOT called."""
        conn = _make_conn(
            fetchrow_side=[_DRAFT_ROW, None],
            fetchval_side=[None, _FAKE_LOG_ID],
        )
        call_count = {"n": 0}

        async def _capture(*args, **kwargs):
            call_count["n"] += 1

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in _patches(conn, _capture, ledger_enabled="false"):
                stack.enter_context(p)
            from app.api.services.posting_service import apply_posting_service
            result = await apply_posting_service(
                _DRAFT_ID, "mock", _TENANT, force=True, actor="test"
            )

        assert result["ok"] is True
        assert call_count["n"] == 0, "_write_ledger_entries must NOT run when flag is false"


# ── Idempotency: duplicate posting still blocked ──────────────────────────────

class TestH70FIdempotencyUnchanged:

    @pytest.mark.asyncio
    async def test_duplicate_posting_blocked_before_ledger_write(self):
        """When posting_logs already has 'posted' status, apply returns
        POSTING_DUPLICATE_BLOCKED — _write_ledger_entries must NOT be called."""
        existing_log = {"id": 55, "status": "posted", "response_json": {"ok": True}}
        conn = _make_conn(
            fetchrow_side=[_DRAFT_ROW, existing_log],  # draft, then existing posting found
            fetchval_side=[None],                       # period lock only
        )
        call_count = {"n": 0}

        async def _capture(*args, **kwargs):
            call_count["n"] += 1

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in _patches(conn, _capture):
                stack.enter_context(p)
            from app.api.services.posting_service import apply_posting_service
            result = await apply_posting_service(
                _DRAFT_ID, "mock", _TENANT, force=True, actor="test"
            )

        assert result["ok"] is False
        assert result.get("error", {}).get("code") == "POSTING_DUPLICATE_BLOCKED"
        assert call_count["n"] == 0, "_write_ledger_entries must NOT be called on duplicate"

    @pytest.mark.asyncio
    async def test_draft_not_approved_rejected_before_ledger_write(self):
        """A draft with status='drafted' must be rejected before ledger write."""
        pending_draft = dict(_DRAFT_ROW, status="drafted")
        conn = _make_conn(
            fetchrow_side=[pending_draft, None],
            fetchval_side=[None],
        )
        call_count = {"n": 0}

        async def _capture(*args, **kwargs):
            call_count["n"] += 1

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in _patches(conn, _capture):
                stack.enter_context(p)
            from app.api.services.posting_service import apply_posting_service
            result = await apply_posting_service(
                _DRAFT_ID, "mock", _TENANT, force=True, actor="test"
            )

        assert result["ok"] is False
        assert "DRAFT_NOT_APPROVED" in str(result)
        assert call_count["n"] == 0


# ── Source-code structure assertions ─────────────────────────────────────────

class TestH70FSourceStructure:

    def test_h70f_marker_present_in_source(self):
        """H70F comment must be in posting_service.py to mark the fix."""
        import inspect
        from app.api.services import posting_service
        src = inspect.getsource(posting_service)
        assert "H70F" in src, "H70F fix marker missing from posting_service.py"

    def test_payload_posting_log_id_assignment_present(self):
        """Source must contain payload['posting_log_id'] = str(log_id) pattern."""
        import inspect
        from app.api.services import posting_service
        src = inspect.getsource(posting_service)
        assert 'payload["posting_log_id"]' in src or "payload['posting_log_id']" in src

    def test_none_guard_present(self):
        """The assignment must be guarded: if log_id is not None."""
        import inspect
        from app.api.services import posting_service
        src = inspect.getsource(posting_service)
        assert "if log_id is not None" in src

    def test_write_ledger_still_receives_full_draft(self):
        """_write_ledger_entries signature still accepts draft, payload, tenant_id, target, hash."""
        import inspect
        from app.api.services import posting_service
        sig = inspect.signature(posting_service._write_ledger_entries)
        params = list(sig.parameters.keys())
        for required in ("draft", "payload", "tenant_id", "target", "entry_hash"):
            assert required in params, f"param {required!r} missing from _write_ledger_entries"

    def test_posting_log_id_read_in_write_fn(self):
        """_write_ledger_entries must still read posting_log_id from payload."""
        import inspect
        from app.api.services import posting_service
        src = inspect.getsource(posting_service._write_ledger_entries)
        assert "posting_log_id" in src
        assert 'payload.get("posting_log_id")' in src or "payload.get('posting_log_id')" in src
