"""Chat191: FIN-11 alternate mutation and legacy-reference safety regressions.

Only mocked, isolated transactions; no live DB or provider calls.
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request, HTTPException


def _request():
    req = Request({"type": "http", "method": "POST", "path": "/approval/test",
                   "headers": [], "query_string": b""})
    req.state.user_id = "trusted-test-checker"
    req.state.tenant_id = "t_alpha"
    return req


def _conn_scope(conn):
    @asynccontextmanager
    async def scoped():
        yield conn
    return scoped


@pytest.mark.asyncio
async def test_update_route_cannot_edit_financially_terminal_or_linked_draft():
    from app.api import routes_approval as routes
    conn = AsyncMock()
    conn.fetchrow.return_value = None  # blocked by safe WHERE predicate
    with patch.object(routes, "require_permission"), \
         patch.object(routes, "resolve_tenant_id", return_value="t_alpha"), \
         patch.object(routes, "get_conn", _conn_scope(conn)):
        result = await routes.update_draft(
            101, routes.DraftUpdateRequest(amount=900.0), _request()
        )
    assert result["ok"] is False
    assert result["error"]["code"] == "DRAFT_MUTATION_BLOCKED"
    statement = str(conn.fetchrow.call_args.args[0])
    assert "reversal_of_draft_id IS NULL" in statement
    assert "entry_type" in statement
    assert "status IN" in statement
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_route_sql_refuses_posted_and_correction_drafts():
    from app.api import routes_approval as routes
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    with patch.object(routes, "require_permission"), \
         patch.object(routes, "resolve_tenant_id", return_value="t_alpha"), \
         patch.object(routes, "get_conn", _conn_scope(conn)):
        with pytest.raises(HTTPException) as caught:
            await routes.delete_draft(101, _request())
    assert caught.value.status_code in (404, 409)
    statement = str(conn.fetchrow.call_args.args[0])
    assert "status IN" in statement
    assert "reversal_of_draft_id IS NULL" in statement
    assert "entry_type" in statement


@pytest.mark.asyncio
async def test_legacy_linked_normal_correction_cannot_be_autoapproved_by_generic_service():
    from app.api.services import approval_service as svc
    conn = AsyncMock()
    conn.fetchrow.return_value = {
        "id": 101, "status": "pending_approval", "entry_type": "normal",
        "reversal_of_draft_id": 41, "confidence": 0.95,
        "amount": 1, "date": None
    }
    tr = AsyncMock()
    conn.transaction = MagicMock(return_value=tr)
    with patch.object(svc, "get_conn", _conn_scope(conn)), \
         patch.object(svc, "structured_log"):
        result = await svc.approve_draft_service(101, "t_alpha")
    assert result["ok"] is False
    assert result["error"]["code"] == "FIN11_MAKER_CHECKER_NOT_CONFIGURED"
    tr.rollback.assert_awaited_once()
    tr.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_direct_correction_cannot_approve_legacy_linked_reference():
    from app.api.services import correct_draft_service as svc
    conn = AsyncMock()
    conn.fetchrow.return_value = {
        "id": 101, "entry_type": "normal",
        "reversal_of_draft_id": 41
    }
    tr = AsyncMock()
    conn.transaction = MagicMock(return_value=tr)
    with patch.object(svc, "get_conn", _conn_scope(conn)):
        result = await svc.correct_draft(
            101, {"reason": "changed"}, user="checker", tenant_id="t_alpha"
        )
    assert result["ok"] is False
    assert result["error"]["code"] == "FIN11_MAKER_CHECKER_NOT_CONFIGURED"
    tr.rollback.assert_awaited_once()
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_cfo_cannot_approve_legacy_linked_normal_reference():
    from app.api import routes_approval as routes
    conn = AsyncMock()
    conn.fetchrow.return_value = {
        "id": 101, "entry_type": "normal",
        "reversal_of_draft_id": 41,
        "status": "awaiting_cfo",
    }
    tr = MagicMock()
    tr.__aenter__ = AsyncMock(return_value=tr)
    tr.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tr)
    with patch.object(routes, "require_permission"), \
         patch.object(routes, "resolve_tenant_id", return_value="t_alpha"), \
         patch.object(routes, "get_conn", _conn_scope(conn)):
        with pytest.raises(HTTPException) as raised:
            await routes.cfo_approve(101, _request())
    assert raised.value.status_code == 409
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_posted_original_cannot_be_corrected_in_place():
    from app.api.services import correct_draft_service as svc
    conn = AsyncMock()
    conn.fetchrow.return_value = {
        "id": 101, "entry_type": "normal", "reversal_of_draft_id": None,
        "status": "posted", "account_code": "1120", "reason": "",
        "debit_account": "1120", "credit_account": "6110",
        "description": "posted", "partner": "", "amount": 100,
        "classification_source": "human",
    }
    tr = AsyncMock()
    conn.transaction = MagicMock(return_value=tr)
    with patch.object(svc, "get_conn", _conn_scope(conn)):
        result = await svc.correct_draft(
            101, {"account_code": "1110"}, user="checker", tenant_id="t_alpha"
        )
    assert result["ok"] is False
    assert result["error"]["code"] == "DRAFT_MUTATION_BLOCKED"
    tr.rollback.assert_awaited_once()
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_linked_normal_reference_is_ambiguous_not_ordinary_adjustment():
    from app.api.services.reversal_service import _reversal_already_exists
    conn = AsyncMock()
    conn.fetchrow.return_value = {"id": 71, "entry_type": "normal"}
    with pytest.raises(ValueError, match="FIN11_AMBIGUOUS_CORRECTION_HISTORY"):
        await _reversal_already_exists(conn, 41, "t_alpha")
    sql = str(conn.fetchrow.call_args.args[0])
    assert "entry_type <> 'adjustment'" in sql or "entry_type NOT IN ('adjustment')" in sql
