"""Chat202 FIN-11: a failed period lookup must not authorize approval.

Regression-first. No real database, posting, vendor or migration.
"""
from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.services import approval_service


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [
    RuntimeError("period-lock database unavailable"),
    PermissionError("period-lock SELECT forbidden"),
    TimeoutError("period-lock query timeout"),
])
async def test_approval_fails_closed_when_period_lock_lookup_fails(failure):
    """Do not UPDATE approved/awaiting_cfo or commit after an unknown period."""
    draft = {
        "id": 202, "tenant_id": "tenant-a", "entry_type": "normal",
        "reversal_of_draft_id": None, "status": "pending_approval",
        "confidence": 0.95, "amount": 50.0, "date": date(2026, 10, 31),
    }
    conn = MagicMock()
    transaction = MagicMock()
    transaction.start = AsyncMock()
    transaction.rollback = AsyncMock()
    transaction.commit = AsyncMock()
    conn.transaction.return_value = transaction

    async def fake_fetchrow(query, *args):
        if "SELECT * FROM journal_drafts" in str(query):
            return draft
        raise AssertionError("UNSAFE_APPROVAL_SQL_AFTER_PERIOD_LOOKUP_FAILURE")

    conn.fetchrow = AsyncMock(side_effect=fake_fetchrow)

    @asynccontextmanager
    async def isolated_conn():
        yield conn

    with (
        patch.object(approval_service, "get_conn", new=isolated_conn),
        patch.object(approval_service, "structured_log"),
        patch.object(approval_service, "evaluate_decision", return_value={}),
        patch(
            "app.api.routes_period_lock.is_period_locked",
            new_callable=AsyncMock, side_effect=failure,
        ) as period_lookup,
        patch(
            "app.api.services.tenant_config_service.get_tenant_setting",
            new_callable=AsyncMock, return_value=10000.0,
        ),
    ):
        result = await approval_service.approve_draft_service(202, "tenant-a")

    assert result["ok"] is False
    assert result["error"]["code"] == "PERIOD_LOCK_UNAVAILABLE"
    period_lookup.assert_awaited_once()
    assert conn.fetchrow.await_count == 1  # only locked draft SELECT
    transaction.rollback.assert_awaited_once()
    transaction.commit.assert_not_awaited()
