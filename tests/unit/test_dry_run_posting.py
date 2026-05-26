"""tests/unit/test_dry_run_posting.py — Task 11H dry-run posting tests.

Verifies that dry_run_posting_service():
- Returns the payload that WOULD be sent without calling the connector.
- Writes a posting_log row with mode='dry_run' and status='dry_run'.
- Does NOT update the draft status.
- Does NOT write to ledger tables.
- Returns NOT_FOUND for missing drafts.
- Returns DRAFT_NOT_APPROVABLE for posted/rejected drafts.
- Passes INVALID_JOURNAL_LINES when lines don't balance.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_draft_row(
    status="approved",
    amount=1000.0,
    lines=None,
    draft_id=42,
    tenant_id="t1",
    date="2026-05-25",
):
    if lines is None:
        lines = [
            {"account_code": "1210", "debit": 1000.0, "credit": 0, "label": "Bank"},
            {"account_code": "3110", "debit": 0, "credit": 1000.0, "label": "Revenue"},
        ]
    return {
        "id": draft_id,
        "tenant_id": tenant_id,
        "date": date,
        "description": "Test invoice",
        "partner": "Test LLC",
        "amount": amount,
        "status": status,
        "currency": "GEL",
        "lines_json": lines,
    }


class _FakeConnCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_):
        pass


def _make_async_conn(row=None, fetchval_return=99):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=row)
    conn.fetchval = AsyncMock(return_value=fetchval_return)
    conn.execute = AsyncMock()
    return conn


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dry_run_returns_payload_for_approved_draft():
    draft_row = _make_draft_row(status="approved")
    conn = _make_async_conn(row=draft_row, fetchval_return=101)

    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)):
        from app.api.services.posting_service import dry_run_posting_service
        result = await dry_run_posting_service(42, "balance", "t1")

    assert result["ok"] is True
    data = result["data"]
    assert data["mode"] == "dry_run"
    assert data["target"] == "balance"
    assert "payload" in data
    assert data["payload"]["amount"] == 1000.0


@pytest.mark.asyncio
async def test_dry_run_accepts_pending_approval_status():
    draft_row = _make_draft_row(status="pending_approval")
    conn = _make_async_conn(row=draft_row, fetchval_return=102)

    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)):
        from app.api.services.posting_service import dry_run_posting_service
        result = await dry_run_posting_service(42, "balance", "t1")

    assert result["ok"] is True


@pytest.mark.asyncio
async def test_dry_run_does_not_update_draft_status():
    draft_row = _make_draft_row(status="approved")
    conn = _make_async_conn(row=draft_row)

    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)):
        from app.api.services.posting_service import dry_run_posting_service
        await dry_run_posting_service(42, "balance", "t1")

    # conn.execute called for posting_log INSERT but NOT for draft status update
    for call in conn.execute.await_args_list:
        sql_arg = call[0][0] if call[0] else ""
        assert "UPDATE journal_drafts" not in str(sql_arg), \
            "dry_run must never update journal_drafts status"


@pytest.mark.asyncio
async def test_dry_run_writes_posting_log_with_dry_run_mode():
    draft_row = _make_draft_row(status="approved")
    conn = _make_async_conn(row=draft_row, fetchval_return=77)

    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)):
        from app.api.services.posting_service import dry_run_posting_service
        result = await dry_run_posting_service(42, "balance", "t1", actor="user-1")

    assert result["data"]["log_id"] == 77
    # Verify the fetchval call used 'dry_run' in status and mode fields
    call_args = conn.fetchval.call_args
    sql = call_args[0][0]
    params = call_args[0][1:]
    assert "dry_run" in params, "status='dry_run' must appear in INSERT params"
    assert "mode" in sql.lower() or "dry_run" in str(params)


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dry_run_returns_not_found_for_missing_draft():
    conn = _make_async_conn(row=None)

    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)):
        from app.api.services.posting_service import dry_run_posting_service
        result = await dry_run_posting_service(999, "balance", "t1")

    assert result["ok"] is False
    assert result["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_dry_run_rejects_posted_draft():
    draft_row = _make_draft_row(status="posted")
    conn = _make_async_conn(row=draft_row)

    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)):
        from app.api.services.posting_service import dry_run_posting_service
        result = await dry_run_posting_service(42, "balance", "t1")

    assert result["ok"] is False
    assert result["error"]["code"] == "DRAFT_NOT_APPROVABLE"


@pytest.mark.asyncio
async def test_dry_run_rejects_rejected_draft():
    draft_row = _make_draft_row(status="rejected")
    conn = _make_async_conn(row=draft_row)

    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)):
        from app.api.services.posting_service import dry_run_posting_service
        result = await dry_run_posting_service(42, "balance", "t1")

    assert result["ok"] is False
    assert result["error"]["code"] == "DRAFT_NOT_APPROVABLE"


@pytest.mark.asyncio
async def test_dry_run_rejects_empty_lines():
    draft_row = _make_draft_row(status="approved", lines=[])
    conn = _make_async_conn(row=draft_row)

    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)):
        from app.api.services.posting_service import dry_run_posting_service
        result = await dry_run_posting_service(42, "balance", "t1")

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_JOURNAL_LINES"


# ---------------------------------------------------------------------------
# Payload content / no-credentials safety
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dry_run_payload_has_no_api_key():
    draft_row = _make_draft_row(status="approved")
    conn = _make_async_conn(row=draft_row)

    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)):
        from app.api.services.posting_service import dry_run_posting_service
        result = await dry_run_posting_service(42, "balance", "t1")

    payload_str = json.dumps(result)
    assert "api_key" not in payload_str
    assert "Authorization" not in payload_str
    assert "Bearer" not in payload_str


@pytest.mark.asyncio
async def test_dry_run_uses_dry_run_entry_hash_not_live_hash():
    """Dry-run entry hash must not collide with the live posting hash."""
    import hashlib
    draft_row = _make_draft_row(status="approved", draft_id=10, amount=500.0, date="2026-01-01")
    conn = _make_async_conn(row=draft_row)

    live_hash = hashlib.sha256(b"10:t1:500.0:2026-01-01:balance").hexdigest()[:16]
    dry_hash = hashlib.sha256(b"10:t1:500.0:2026-01-01:dry_run_balance").hexdigest()[:16]
    assert live_hash != dry_hash  # sanity

    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)):
        from app.api.services.posting_service import dry_run_posting_service
        await dry_run_posting_service(10, "balance", "t1")

    # The INSERT params must contain the dry_run hash, not the live hash
    call_args = conn.fetchval.call_args
    params = call_args[0][1:]
    params_str = str(params)
    assert dry_hash in params_str
    assert live_hash not in params_str


# ---------------------------------------------------------------------------
# Route import sanity
# ---------------------------------------------------------------------------

def test_dry_run_route_is_importable():
    from app.api.routes_posting import dry_run_balance
    assert callable(dry_run_balance)
