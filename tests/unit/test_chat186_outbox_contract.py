"""FIN-12: no external ERP retry or unverified dispatch, stable intent IDs."""
import pytest
from app.api.services.posting_outbox_intent_service import (
    delivery_decision, prepare_posting_intent, PostingOutboxUnavailable,
)
from app.api.db import authenticated_tenant_context
from unittest.mock import AsyncMock


@pytest.mark.parametrize("state,expected", [
    ("prepared","VENDOR_IDEMPOTENCY_APPROVAL_REQUIRED"),
    ("in_flight","OUTCOME_PENDING"),
    ("unknown","RECONCILIATION_REQUIRED"),
    ("confirmed","NO_ACTION"),
    ("rejected","NO_ACTION"),
    ("unexpected","HOLD_UNRECOGNIZED_STATE"),
])
def test_state_machine_never_advertises_automatic_live_retry(state,expected):
    assert delivery_decision(state) == expected


@pytest.mark.asyncio
async def test_missing_or_forged_tenant_denied_before_database_write():
    conn=AsyncMock()
    conn.is_in_transaction=lambda:True
    with pytest.raises(PostingOutboxUnavailable):
        await prepare_posting_intent(conn,tenant_id="t_alpha",source_id="17",
                                     target_system="balance",payload={"amount":12})
    conn.fetchrow.assert_not_called()
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(PostingOutboxUnavailable):
            await prepare_posting_intent(conn,tenant_id="t_beta",source_id="17",
                                         target_system="balance",payload={"amount":12})
        with pytest.raises(PostingOutboxUnavailable):
            await prepare_posting_intent(conn,tenant_id="t_alpha",source_id="17",
                                         target_system="balance",payload={"amount":float('nan')})
        with pytest.raises(PostingOutboxUnavailable):
            await prepare_posting_intent(conn,tenant_id="t_alpha",source_id="17",
                                         target_system="balance",
                                         payload={"amount":12,"tenant_id":"t_beta"})
    conn.fetchrow.assert_not_called()


@pytest.mark.asyncio
async def test_autocommit_and_demo_target_cannot_enqueue():
    conn=AsyncMock()
    conn.is_in_transaction=lambda:False
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(PostingOutboxUnavailable,match="OUTBOX_TRANSACTION_REQUIRED"):
            await prepare_posting_intent(conn,tenant_id="t_alpha",source_id="17",
                                         target_system="balance",payload={"amount":12})
        with pytest.raises(PostingOutboxUnavailable):
            await prepare_posting_intent(conn,tenant_id="t_alpha",source_id="17",
                                         target_system="mock",payload={"amount":12})
    conn.fetchrow.assert_not_called()
