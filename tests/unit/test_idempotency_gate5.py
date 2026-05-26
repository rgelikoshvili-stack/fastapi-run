"""tests/unit/test_idempotency_gate5.py — Task 11K / Gate 5: idempotency.

Verifies:
- dry_run_posting_service() returns the existing log_id when ON CONFLICT
  DO NOTHING fires (entry_hash already in posting_logs).
- The fallback SELECT is called only when the INSERT returns None.
- X-Idempotent-Key header on /balance/dry-run returns cached response.
- X-Idempotent-Key header stores result after first dry-run call.
- entry_hash differs between targets (no cross-target collision).
- entry_hash differs between dry-run and live posting for the same draft.
"""
import hashlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeConnCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_):
        pass


def _make_draft_row(draft_id=42, status="approved", amount=1000.0):
    return {
        "id": draft_id,
        "tenant_id": "t1",
        "date": "2026-05-25",
        "description": "Test invoice",
        "partner": "Test LLC",
        "amount": amount,
        "status": status,
        "currency": "GEL",
        "lines_json": [
            {"account_code": "1210", "debit": 1000.0, "credit": 0, "label": "Bank"},
            {"account_code": "3110", "debit": 0, "credit": 1000.0, "label": "Revenue"},
        ],
    }


# ---------------------------------------------------------------------------
# entry_hash fallback when ON CONFLICT fires
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dry_run_returns_existing_log_id_on_conflict():
    """When INSERT returns None (ON CONFLICT), the service fetches the existing log_id."""
    draft_row = _make_draft_row()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=draft_row)
    # First fetchval = None (ON CONFLICT fired), second fetchval = 77 (existing row)
    conn.fetchval = AsyncMock(side_effect=[None, 77])
    conn.execute = AsyncMock()

    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)):
        from app.api.services.posting_service import dry_run_posting_service
        result = await dry_run_posting_service(42, "balance", "t1")

    assert result["ok"] is True
    assert result["data"]["log_id"] == 77
    # fetchval called twice: INSERT then SELECT fallback
    assert conn.fetchval.await_count == 2


@pytest.mark.asyncio
async def test_dry_run_does_not_call_fallback_when_insert_succeeds():
    """When INSERT returns a valid log_id, the fallback SELECT is NOT called."""
    draft_row = _make_draft_row()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=draft_row)
    conn.fetchval = AsyncMock(return_value=55)  # INSERT returned a real id
    conn.execute = AsyncMock()

    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)):
        from app.api.services.posting_service import dry_run_posting_service
        result = await dry_run_posting_service(42, "balance", "t1")

    assert result["data"]["log_id"] == 55
    assert conn.fetchval.await_count == 1  # only the INSERT, no fallback


@pytest.mark.asyncio
async def test_dry_run_fallback_sql_uses_entry_hash():
    """The fallback SELECT must filter by entry_hash (not draft_id)."""
    draft_row = _make_draft_row()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=draft_row)
    conn.fetchval = AsyncMock(side_effect=[None, 88])
    conn.execute = AsyncMock()

    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)):
        from app.api.services.posting_service import dry_run_posting_service
        await dry_run_posting_service(42, "balance", "t1")

    # Second fetchval call should be the fallback SELECT
    fallback_call = conn.fetchval.await_args_list[1]
    sql = fallback_call[0][0]
    assert "entry_hash" in sql.lower()


# ---------------------------------------------------------------------------
# entry_hash uniqueness
# ---------------------------------------------------------------------------

def test_entry_hash_differs_between_targets():
    """Same draft posted to 'balance' vs 'onec' must have different hashes."""
    from app.api.services.posting_service import _compute_entry_hash
    h_balance = _compute_entry_hash(10, "t1", 500.0, "2026-01-01", "balance")
    h_onec    = _compute_entry_hash(10, "t1", 500.0, "2026-01-01", "onec")
    assert h_balance != h_onec


def test_dry_run_hash_differs_from_live_hash():
    """dry_run_balance must not collide with the live balance hash."""
    from app.api.services.posting_service import _compute_entry_hash
    h_live     = _compute_entry_hash(10, "t1", 500.0, "2026-01-01", "balance")
    h_dry_run  = _compute_entry_hash(10, "t1", 500.0, "2026-01-01", "dry_run_balance")
    assert h_live != h_dry_run


def test_entry_hash_same_inputs_produce_same_hash():
    """Same inputs must always produce identical hashes (deterministic)."""
    from app.api.services.posting_service import _compute_entry_hash
    h1 = _compute_entry_hash(42, "tenant-x", 1000.0, "2026-05-25", "balance")
    h2 = _compute_entry_hash(42, "tenant-x", 1000.0, "2026-05-25", "balance")
    assert h1 == h2


def test_entry_hash_different_amounts_differ():
    from app.api.services.posting_service import _compute_entry_hash
    h1 = _compute_entry_hash(42, "t1", 100.0, "2026-05-25", "balance")
    h2 = _compute_entry_hash(42, "t1", 200.0, "2026-05-25", "balance")
    assert h1 != h2


# ---------------------------------------------------------------------------
# X-Idempotent-Key on dry-run route
# ---------------------------------------------------------------------------

def _make_starlette_request(user_id="actor", tenant_id="t1", headers=None):
    from starlette.requests import Request as StarletteRequest
    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode(), v.encode()))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/posting/balance/dry-run/42",
        "query_string": b"",
        "headers": raw_headers,
    }
    req = StarletteRequest(scope)
    req.state.user_id = user_id
    req.state.tenant_id = tenant_id
    return req


@pytest.mark.asyncio
async def test_dry_run_route_returns_cached_on_idem_key_hit():
    """When X-Idempotent-Key matches a cached response, service is NOT called."""
    cached = {"ok": True, "data": {"log_id": 33, "mode": "dry_run"}, "message": "cached"}
    req = _make_starlette_request(headers={"X-Idempotent-Key": "key-abc"})

    with patch("app.api.routes_posting.idempotency_check",
               new_callable=AsyncMock, return_value=cached) as mock_check, \
         patch("app.api.routes_posting.dry_run_posting_service",
               new_callable=AsyncMock) as mock_svc, \
         patch("app.api.routes_posting.require_permission"), \
         patch("app.api.routes_posting.resolve_tenant_id", return_value="t1"):
        from app.api.routes_posting import dry_run_balance
        result = await dry_run_balance(req, draft_id=42)

    assert result == cached
    mock_svc.assert_not_awaited()
    mock_check.assert_awaited_once()


@pytest.mark.asyncio
async def test_dry_run_route_stores_result_on_first_call():
    """On first call with X-Idempotent-Key, result is stored for future calls."""
    fresh_result = {"ok": True, "data": {"log_id": 44, "mode": "dry_run"}, "message": "ok"}
    req = _make_starlette_request(headers={"X-Idempotent-Key": "key-new"})

    with patch("app.api.routes_posting.idempotency_check",
               new_callable=AsyncMock, return_value=None) as mock_check, \
         patch("app.api.routes_posting.idempotency_store",
               new_callable=AsyncMock) as mock_store, \
         patch("app.api.routes_posting.dry_run_posting_service",
               new_callable=AsyncMock, return_value=fresh_result), \
         patch("app.api.routes_posting.require_permission"), \
         patch("app.api.routes_posting.resolve_tenant_id", return_value="t1"):
        from app.api.routes_posting import dry_run_balance
        result = await dry_run_balance(req, draft_id=42)

    assert result == fresh_result
    mock_store.assert_awaited_once()
    store_args = mock_store.call_args[0]
    assert store_args[1] == "key-new"
    assert "dry_run" in store_args[2]  # endpoint key contains 'dry_run'


@pytest.mark.asyncio
async def test_dry_run_route_no_idem_key_skips_store():
    """Without X-Idempotent-Key header, idempotency store is NOT called."""
    fresh_result = {"ok": True, "data": {"log_id": 55}, "message": "ok"}
    req = _make_starlette_request()  # no headers → no idem key

    with patch("app.api.routes_posting.idempotency_store",
               new_callable=AsyncMock) as mock_store, \
         patch("app.api.routes_posting.dry_run_posting_service",
               new_callable=AsyncMock, return_value=fresh_result), \
         patch("app.api.routes_posting.require_permission"), \
         patch("app.api.routes_posting.resolve_tenant_id", return_value="t1"):
        from app.api.routes_posting import dry_run_balance
        await dry_run_balance(req, draft_id=42)

    mock_store.assert_not_awaited()
