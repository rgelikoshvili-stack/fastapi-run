"""Chat206 FIN-11 RED: keep maker creation audit row locked through review.

Read-only synthetic SQL-contract test; no real DB or ERP call.
"""
from unittest.mock import AsyncMock

import pytest

from app.api.services.correction_review_service import _require_original_maker


@pytest.mark.asyncio
async def test_maker_creation_audit_read_locks_row_until_transaction_end():
    conn = AsyncMock()
    conn.fetch.return_value = [{
        "actor": "auth:maker-71",
        "new_value": {"source_id": 41, "status": "pending_approval"},
    }]
    draft = {
        "id": 71,
        "entry_type": "reversal",
        "reversal_of_draft_id": 41,
    }
    await _require_original_maker(
        conn, "t_alpha", draft, "auth:maker-71",
    )
    conn.fetch.assert_awaited_once()
    sql = " ".join(str(conn.fetch.call_args.args[0]).upper().split())
    assert "TENANT_ID" in sql and "RESOURCE_ID" in sql
    assert "ORDER BY ID LIMIT 2 FOR SHARE" in sql
    conn.execute.assert_not_awaited()
