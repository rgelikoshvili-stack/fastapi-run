"""Chat203 FIN-11: reclassification must not edit posted/linked/terminal drafts.

RED-first, isolated route/SQL-contract regression. No database or ERP I/O.
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from starlette.requests import Request

from app.api import routes_approval as route


def _request():
    request = Request({
        "type": "http", "method": "POST", "path": "/approval/reclassify",
        "headers": [], "query_string": b"",
    })
    request.state.tenant_id = "tenant-a"
    return request


def _must_scope_mutable_draft(sql):
    """Selection and UPDATE must both deny terminal/linked corrections."""
    statement = " ".join(str(sql).lower().split())
    assert "tenant_id" in statement
    assert "status in (" in statement
    for status in ("drafted", "pending_approval", "pending_human_review", "needs_correction"):
        assert f"'{status}'" in statement
    assert "entry_type in (" in statement
    assert "'normal'" in statement and "'standard'" in statement
    assert "reversal_of_draft_id is null" in statement
    return statement


def _fake_connection(rows, updated):
    conn = AsyncMock()

    async def select(sql, *args):
        statement = _must_scope_mutable_draft(sql)
        assert "select id, description, amount" in statement
        assert args == ("tenant-a",)
        return rows

    async def conditional_update(sql, *args):
        statement = _must_scope_mutable_draft(sql)
        assert "update journal_drafts" in statement
        assert "returning id" in statement
        # A draft reclassified in another transaction must be rechecked
        # atomically, not updated from a stale selection.
        assert "debit_account is null" in statement
        assert "credit_account is null" in statement
        assert args[-2:] == (77, "tenant-a")
        return updated

    conn.fetch = AsyncMock(side_effect=select)
    conn.fetchrow = AsyncMock(side_effect=conditional_update)
    conn.execute = AsyncMock(side_effect=AssertionError("unconditional UPDATE forbidden"))
    return conn


async def _run(conn):
    @asynccontextmanager
    async def scoped_conn():
        yield conn

    with patch.object(route, "require_permission"), \
         patch.object(route, "resolve_tenant_id", return_value="tenant-a"), \
         patch.object(route, "get_conn", scoped_conn), \
         patch("app.knowledge.journal_builder.classify_transaction",
               return_value={"account": "7210"}):
        return await route.reclassify_unclassified(_request())


@pytest.mark.asyncio
async def test_reclassify_select_must_exclude_posted_terminal_and_linked():
    conn = _fake_connection([], None)
    result = await _run(conn)
    assert result["ok"] is True
    assert result["data"]["reclassified"] == 0
    conn.fetchrow.assert_not_awaited()
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_reclassify_update_must_recheck_mutability_and_count_success():
    conn = _fake_connection(
        [{"id": 77, "description": "ordinary pending draft", "amount": 15}],
        {"id": 77},
    )
    result = await _run(conn)
    assert result["ok"] is True
    assert result["data"]["reclassified"] == 1
    assert result["data"]["total_unclassified"] == 1
    conn.fetchrow.assert_awaited_once()
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_reclassify_concurrent_status_change_is_not_counted():
    conn = _fake_connection(
        [{"id": 77, "description": "draft subsequently posted", "amount": 15}],
        None,
    )
    result = await _run(conn)
    assert result["ok"] is True
    assert result["data"]["reclassified"] == 0
    assert result["data"]["total_unclassified"] == 1
    conn.fetchrow.assert_awaited_once()
    conn.execute.assert_not_awaited()
