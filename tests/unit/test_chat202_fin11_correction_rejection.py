"""FIN-11: generic rejection must not bypass independent correction review.

Synthetic RED-first regression, no live ledger, ERP or database.
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.services import approval_service


@pytest.mark.asyncio
@pytest.mark.parametrize("entry_type,source_link", [
    ("reversal", 41),
    ("adjustment", 41),
    ("normal", 41),  # legacy/forged type cannot conceal source linkage
    ("standard", 41),
    ("reversal", None),  # also reject broken legacy correction identities
])
async def test_generic_rejection_cannot_override_maker_checker(entry_type, source_link):
    draft = {
        "id": 202, "tenant_id": "tenant-a", "status": "pending_approval",
        "entry_type": entry_type, "reversal_of_draft_id": source_link,
        "confidence": 0.95, "amount": 10,
    }
    txn = MagicMock()
    txn.start = AsyncMock()
    txn.rollback = AsyncMock()
    txn.commit = AsyncMock()
    conn = MagicMock()
    conn.transaction.return_value = txn

    async def fetchrow(sql, *args):
        if "SELECT * FROM journal_drafts" in str(sql):
            return draft
        raise AssertionError("FIN11_GENERIC_REJECT_MUST_NOT_WRITE_CORRECTION")

    conn.fetchrow = AsyncMock(side_effect=fetchrow)

    @asynccontextmanager
    async def fake_conn():
        yield conn

    with patch.object(approval_service, "get_conn", new=fake_conn), \
         patch.object(approval_service, "structured_log"):
        result = await approval_service.reject_draft_service(
            202, "reason", tenant_id="tenant-a",
        )
    assert result["ok"] is False
    assert result["error"]["code"] == "FIN11_MAKER_CHECKER_NOT_CONFIGURED"
    assert conn.fetchrow.await_count == 1
    txn.rollback.assert_awaited_once()
    txn.commit.assert_not_awaited()
