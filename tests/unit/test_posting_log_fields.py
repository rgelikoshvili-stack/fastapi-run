"""tests/unit/test_posting_log_fields.py — Task 11J / Gate 8: posting log fields.

Verifies that all live posting_logs INSERT statements include mode, actor,
connector so every log row is fully attributed.

Tests:
- apply_posting_service passes mode='live', actor, connector to posting_logs.
- connector_not_ready path also logs mode='live', actor, connector.
- post_draft_to_balance_service / onec / oris / mock all forward actor.
- Route handlers extract actor from request.state.user_id.
- dry_run already uses mode='dry_run' (regression guard).
"""
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


def _make_apply_conn(draft_id=10, tenant_id="t1"):
    """Return an AsyncMock connection for apply_posting_service.

    Call order inside apply_posting_service:
      fetchrow[0]  → journal_drafts SELECT FOR UPDATE
      fetchval[0]  → period_locks check (None = not locked)
      fetchrow[1]  → duplicate invoice check (None = no dup)
      fetchrow[2]  → re-post guard: posting_logs check (None = not posted)
      fetchval[1]  → INSERT posting_logs RETURNING id
    """
    conn = AsyncMock()
    draft_row = {
        "id": draft_id,
        "tenant_id": tenant_id,
        "date": "2026-05-25",
        "description": "Test",
        "partner": "LLC",
        "amount": 500.0,
        "status": "approved",
        "currency": "GEL",
        "lines_json": [
            {"account_code": "1210", "debit": 500.0, "credit": 0, "label": "Bank"},
            {"account_code": "3110", "debit": 0, "credit": 500.0, "label": "Revenue"},
        ],
    }
    conn.fetchrow = AsyncMock(side_effect=[
        draft_row,  # journal_drafts SELECT
        None,       # duplicate invoice check
        None,       # re-post guard (posting_logs)
    ])
    # fetchval[0] = None → period_locks (not locked)
    # fetchval[1] = 99   → INSERT posting_logs RETURNING id
    conn.fetchval = AsyncMock(side_effect=[None, 99])
    conn.execute = AsyncMock()

    tr = AsyncMock()
    tr.start = AsyncMock()
    tr.commit = AsyncMock()
    tr.rollback = AsyncMock()
    conn.transaction = MagicMock(return_value=tr)
    return conn


# ---------------------------------------------------------------------------
# apply_posting_service — live INSERT includes mode/actor/connector
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_apply_posting_logs_mode_live_on_connector_not_ready():
    """When connector is not ready, posting_log INSERT must include mode='live'."""
    conn = _make_apply_conn()

    readiness_not_ready = {"ok": False, "message": "api_key not set"}

    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.posting_service._get_connector_readiness",
               return_value=readiness_not_ready):
        from app.api.services.posting_service import apply_posting_service
        await apply_posting_service(10, "balance", "t1", actor="user-5")

    insert_call = conn.fetchval.call_args
    sql = insert_call[0][0]
    params = list(insert_call[0][1:])
    assert "mode" in sql.lower()
    assert "live" in params
    assert "user-5" in params
    assert "balance" in params


@pytest.mark.asyncio
async def test_apply_posting_logs_mode_live_on_success():
    """Successful posting INSERT must include mode='live', actor, connector."""
    conn = _make_apply_conn()

    readiness_ok = {"ok": True, "message": "ready"}
    mock_response = {"success": True, "id": "ext-123"}

    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.posting_service._get_connector_readiness",
               return_value=readiness_ok), \
         patch("app.api.services.posting_service._post_via_connector",
               return_value=mock_response):
        from app.api.services.posting_service import apply_posting_service
        await apply_posting_service(10, "balance", "t1", actor="user-7")

    insert_call = conn.fetchval.call_args
    sql = insert_call[0][0]
    params = list(insert_call[0][1:])
    assert "mode" in sql.lower()
    assert "live" in params
    assert "user-7" in params
    assert "balance" in params


@pytest.mark.asyncio
async def test_apply_posting_logs_actor_none_when_not_provided():
    """When actor is not passed, None is stored (not a placeholder)."""
    conn = _make_apply_conn()
    readiness_not_ready = {"ok": False, "message": "not ready"}

    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.posting_service._get_connector_readiness",
               return_value=readiness_not_ready):
        from app.api.services.posting_service import apply_posting_service
        await apply_posting_service(10, "balance", "t1")  # no actor

    params = list(conn.fetchval.call_args[0][1:])
    # actor should be None
    assert None in params


# ---------------------------------------------------------------------------
# Wrapper services forward actor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_draft_to_balance_service_forwards_actor():
    with patch("app.api.services.posting_service.apply_posting_service",
               new_callable=AsyncMock) as mock_apply:
        mock_apply.return_value = {"ok": True}
        from app.api.services.posting_service import post_draft_to_balance_service
        await post_draft_to_balance_service(10, tenant_id="t1", actor="bal-user")

    mock_apply.assert_awaited_once()
    call_kwargs = mock_apply.call_args[1]
    assert call_kwargs["actor"] == "bal-user"
    assert call_kwargs["tenant_id"] == "t1"


@pytest.mark.asyncio
async def test_post_draft_to_onec_service_forwards_actor():
    with patch("app.api.services.posting_service.apply_posting_service",
               new_callable=AsyncMock) as mock_apply:
        mock_apply.return_value = {"ok": True}
        from app.api.services.posting_service import post_draft_to_onec_service
        await post_draft_to_onec_service(11, tenant_id="t2", actor="onec-user")

    call_kwargs = mock_apply.call_args[1]
    assert call_kwargs["actor"] == "onec-user"


@pytest.mark.asyncio
async def test_post_draft_to_oris_service_forwards_actor():
    with patch("app.api.services.posting_service.apply_posting_service",
               new_callable=AsyncMock) as mock_apply:
        mock_apply.return_value = {"ok": True}
        from app.api.services.posting_service import post_draft_to_oris_service
        await post_draft_to_oris_service(12, tenant_id="t3", actor="oris-user")

    call_kwargs = mock_apply.call_args[1]
    assert call_kwargs["actor"] == "oris-user"


@pytest.mark.asyncio
async def test_mock_posting_service_forwards_actor():
    with patch("app.api.services.posting_service.apply_posting_service",
               new_callable=AsyncMock) as mock_apply:
        mock_apply.return_value = {"ok": True}
        from app.api.services.posting_service import mock_posting_service
        await mock_posting_service(13, tenant_id="t4", actor="mock-user")

    call_kwargs = mock_apply.call_args[1]
    assert call_kwargs["actor"] == "mock-user"


# ---------------------------------------------------------------------------
# Route handlers extract actor from request.state
# ---------------------------------------------------------------------------

def _make_starlette_request(user_id="req-actor", tenant_id="t1"):
    """Build a minimal real Starlette Request (needed to satisfy slowapi isinstance check)."""
    from starlette.requests import Request as StarletteRequest
    from starlette.datastructures import Headers
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/posting/balance/10",
        "query_string": b"",
        "headers": [],
    }
    req = StarletteRequest(scope)
    req.state.user_id = user_id
    req.state.tenant_id = tenant_id
    return req


@pytest.mark.asyncio
async def test_route_balance_passes_actor_to_service():
    req = _make_starlette_request(user_id="route-user-1")
    with patch("app.api.routes_posting.post_draft_to_balance_service",
               new_callable=AsyncMock) as mock_svc, \
         patch("app.api.routes_posting.require_permission"), \
         patch("app.api.routes_posting.resolve_tenant_id", return_value="t1"):
        mock_svc.return_value = {"ok": True}
        from app.api.routes_posting import post_draft_to_balance
        await post_draft_to_balance(req, draft_id=10)

    call_kwargs = mock_svc.call_args[1]
    assert call_kwargs["actor"] == "route-user-1"


@pytest.mark.asyncio
async def test_route_apply_passes_actor_to_service():
    req = _make_starlette_request(user_id="route-user-2")
    with patch("app.api.routes_posting.apply_posting_service",
               new_callable=AsyncMock) as mock_svc, \
         patch("app.api.routes_posting.require_permission"), \
         patch("app.api.routes_posting.resolve_tenant_id", return_value="t1"), \
         patch("app.api.routes_posting.idempotency_check", new_callable=AsyncMock,
               return_value=None), \
         patch("app.api.routes_posting.idempotency_store", new_callable=AsyncMock):
        mock_svc.return_value = {"ok": True}
        from app.api.routes_posting import apply_posting
        await apply_posting(req, draft_id=10, target="balance", force=False)

    call_kwargs = mock_svc.call_args[1]
    assert call_kwargs["actor"] == "route-user-2"


# ---------------------------------------------------------------------------
# Regression: dry-run still uses mode='dry_run'
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dry_run_mode_is_dry_run_not_live():
    """Dry-run posting_log INSERT must use mode='dry_run', not 'live'."""
    draft_row = {
        "id": 42,
        "tenant_id": "t1",
        "date": "2026-05-25",
        "description": "Test",
        "partner": "LLC",
        "amount": 1000.0,
        "status": "approved",
        "currency": "GEL",
        "lines_json": [
            {"account_code": "1210", "debit": 1000.0, "credit": 0, "label": "Bank"},
            {"account_code": "3110", "debit": 0, "credit": 1000.0, "label": "Revenue"},
        ],
    }
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=draft_row)
    conn.fetchval = AsyncMock(return_value=77)
    conn.execute = AsyncMock()

    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)):
        from app.api.services.posting_service import dry_run_posting_service
        await dry_run_posting_service(42, "balance", "t1", actor="dr-user")

    insert_call = conn.fetchval.call_args
    params = list(insert_call[0][1:])
    assert "dry_run" in params
    assert "live" not in params
