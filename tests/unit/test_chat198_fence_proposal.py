"""Chat198 FIN-12: one-shot *offline* lease/fence proposal — no dispatch.

No external ERP calls, background workers, live migrations or provider secrets.
"""
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from app.api.db import authenticated_tenant_context
from app.api.services.posting_outbox_fence_proposal_service import (
    FenceProposalUnavailable, fence_proposal_decision, prepare_fence_proposal,
)

_ID = "dd17459f-b2f7-4ae0-bdba-4df9bd49c251"
_PROPOSAL = UUID("b0c984b0-c8d5-4a95-913a-2ba824f627d2")


@pytest.mark.parametrize("status,expired,epoch", [
    ("prepared", False, 1), ("prepared", True, 1),
    ("prepared", True, 999), ("unknown", True, 2),
    ("in_flight", True, 2), ("confirmed", False, 1),
    ("rejected", False, 1), ("bad", True, 0),
    (None, True, 1), (True, True, 1),
])
def test_expired_fence_or_stale_epoch_never_reauthorizes_dispatch(status,expired,epoch):
    result = fence_proposal_decision(status, expired=expired, epoch=epoch)
    assert result["dispatch_allowed"] is False
    assert result["retry_allowed"] is False
    assert result["confirm_allowed"] is False
    assert result["ledger_write_allowed"] is False
    assert result["lease_authoritative"] is False
    assert result["provider_idempotency_certified"] is False
    assert result["next_action"] in ("VENDOR_CONTRACT_HOLD", "NOT_ELIGIBLE")


@pytest.mark.asyncio
async def test_fence_proposal_requires_tenant_context_and_transaction_before_sql():
    conn = AsyncMock()
    conn.is_in_transaction = lambda: True
    with pytest.raises(FenceProposalUnavailable, match="FIN12_FENCE_TENANT_UNAUTHORIZED"):
        await prepare_fence_proposal(conn, tenant_id="t_alpha", outbox_id=_ID,
                                     owner_subject="acct:1", owner_role="accountant")
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(FenceProposalUnavailable, match="FIN12_FENCE_TENANT_UNAUTHORIZED"):
            await prepare_fence_proposal(conn, tenant_id="t_beta", outbox_id=_ID,
                                         owner_subject="acct:1", owner_role="accountant")
    conn.fetchrow.assert_not_awaited()
    conn.execute.assert_not_awaited()
    conn.is_in_transaction = lambda: False
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(FenceProposalUnavailable, match="FIN12_FENCE_TRANSACTION_REQUIRED"):
            await prepare_fence_proposal(conn, tenant_id="t_alpha", outbox_id=_ID,
                                         owner_subject="acct:1", owner_role="accountant")
    conn.fetchrow.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("subject,role", [
    ("", "accountant"), ("system","accountant"), ("anon","admin"),
    (" acct:1 ", "accountant"), ("acct:1", "viewer"),
    ("acct:1", "cfo"), ("acct:1", "superuser"),
])
async def test_unverified_actor_or_role_cannot_create_fence(subject,role):
    conn = AsyncMock()
    conn.is_in_transaction = lambda: True
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(FenceProposalUnavailable):
            await prepare_fence_proposal(conn, tenant_id="t_alpha", outbox_id=_ID,
                                         owner_subject=subject,owner_role=role)
    conn.fetchrow.assert_not_awaited()
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_fence_not_allowed_for_unknown_or_in_flight_source():
    conn = AsyncMock()
    conn.is_in_transaction = lambda: True
    conn.fetchrow.return_value = {
        "id": UUID(_ID), "tenant_id":"t_alpha", "state":"unknown",
        "source_type":"journal_draft", "source_id":"draft41",
        "target_system":"balance", "idempotency_key":"a"*64,
        "payload_sha256":"b"*64, "provider_receipt_id":None,
        "provider_verified_at":None,
    }
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(FenceProposalUnavailable,match="FIN12_FENCE_SOURCE_NOT_PREPARED"):
            await prepare_fence_proposal(conn, tenant_id="t_alpha", outbox_id=_ID,
                                         owner_subject="acct:1",owner_role="accountant")
    assert conn.fetchrow.await_count == 1
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_proposal_returns_hold_only_not_lease_or_erp_mutation():
    conn = AsyncMock()
    conn.is_in_transaction = lambda: True
    source = {
        "id":UUID(_ID), "tenant_id":"t_alpha", "state":"prepared",
        "source_type":"journal_draft", "source_id":"draft41",
        "target_system":"balance", "idempotency_key":"a"*64,
        "payload_sha256":"b"*64, "provider_receipt_id":None,
        "provider_verified_at":None,
    }
    conn.fetchrow.side_effect = [
        source, {"id":_PROPOSAL,"fence_epoch":1},
    ]
    with authenticated_tenant_context("t_alpha"):
        result=await prepare_fence_proposal(
            conn, tenant_id="t_alpha", outbox_id=_ID,
            owner_subject="acct:1", owner_role="accountant",
        )
    assert result["proposal_id"] == str(_PROPOSAL)
    assert result["fence_epoch"] == 1
    assert result["dispatch_allowed"] is False
    assert result["provider_idempotency_certified"] is False
    assert result["lease_authoritative"] is False
    assert conn.fetchrow.await_count == 2
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_repeated_or_expired_proposal_cannot_create_second_epoch():
    conn = AsyncMock()
    conn.is_in_transaction = lambda: True
    source = {
        "id":UUID(_ID), "tenant_id":"t_alpha", "state":"prepared",
        "source_type":"journal_draft", "source_id":"draft41",
        "target_system":"balance", "idempotency_key":"a"*64,
        "payload_sha256":"b"*64, "provider_receipt_id":None,
        "provider_verified_at":None,
    }
    conn.fetchrow.side_effect = [source, None]  # one-shot UNIQUE conflict
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(FenceProposalUnavailable, match="FIN12_FENCE_ALREADY_PROPOSED"):
            await prepare_fence_proposal(conn,tenant_id="t_alpha",outbox_id=_ID,
                                         owner_subject="acct:2",owner_role="accountant")
    conn.execute.assert_not_awaited()
