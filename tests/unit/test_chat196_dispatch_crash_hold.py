"""Chat196 FIN-12 red-first tests: no vendor-certified dispatch and safe crash HOLD.

No provider, worker, callback or real DB access. This module remains unregistered.
"""
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from app.api.db import authenticated_tenant_context
from app.api.services.posting_outbox_crash_hold_service import (
    CrashHoldUnavailable, classify_after_crash, record_outcome_hold,
)

INTENT="dd17459f-b2f7-4ae0-bdba-4df9bd49c251"


@pytest.mark.parametrize("state", [
    "prepared", "in_flight", "unknown", "confirmed", "rejected",
    "other", None, True, 1,
])
def test_recovery_classification_never_dispatches_or_retries(state):
    decision=classify_after_crash(state)
    assert decision["dispatch_allowed"] is False
    assert decision["retry_allowed"] is False
    assert decision["confirm_allowed"] is False
    assert decision["ledger_write_allowed"] is False
    assert decision["provider_verified"] is False
    assert decision["next_action"] == (
        "MANUAL_OUTCOME_HOLD" if state in ("in_flight", "unknown")
        else "NO_RECOVERY_AUTHORITY"
    )


@pytest.mark.asyncio
async def test_tenant_must_match_authenticated_scope_without_db_access():
    conn=AsyncMock()
    conn.is_in_transaction=lambda: True
    with pytest.raises(CrashHoldUnavailable, match="FIN12_CRASH_TENANT_UNAUTHORIZED"):
        await record_outcome_hold(conn,tenant_id="t_alpha",outbox_id=INTENT,
                                  opener_subject="accountant-1",opener_role="accountant",
                                  reason="worker_crash")
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(CrashHoldUnavailable, match="FIN12_CRASH_TENANT_UNAUTHORIZED"):
            await record_outcome_hold(conn,tenant_id="t_beta",outbox_id=INTENT,
                                      opener_subject="accountant-1",opener_role="accountant",
                                      reason="worker_crash")
    conn.fetchrow.assert_not_awaited()
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_autocommit_recovery_record():
    conn=AsyncMock()
    conn.is_in_transaction=lambda: False
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(CrashHoldUnavailable,match="FIN12_CRASH_TRANSACTION_REQUIRED"):
            await record_outcome_hold(conn,tenant_id="t_alpha",outbox_id=INTENT,
                                      opener_subject="accountant-1",opener_role="accountant",
                                      reason="timeout")
    conn.fetchrow.assert_not_awaited()
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("subject,role,reason", [
    ("anon","accountant","timeout"),
    (" system ","admin","worker_crash"),
    ("checker","cfo","worker_crash"),
    ("maker","viewer","worker_crash"),
    ("maker","accountant","unknown"),
])
async def test_invalid_actor_or_recovery_reason_denied_before_db(subject,role,reason):
    conn=AsyncMock()
    conn.is_in_transaction=lambda: True
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(CrashHoldUnavailable):
            await record_outcome_hold(conn,tenant_id="t_alpha",outbox_id=INTENT,
                                      opener_subject=subject,opener_role=role,
                                      reason=reason)
    conn.fetchrow.assert_not_awaited()
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_ambiguous_prepared_intent_never_claims_crash_or_writes():
    conn=AsyncMock()
    conn.is_in_transaction=lambda: True
    conn.fetchrow.return_value={
        "id": UUID(INTENT), "tenant_id": "t_alpha",
        "state": "prepared", "source_type": "journal_draft",
        "source_id": "41", "target_system": "balance",
        "idempotency_key": "a"*64, "payload_sha256": "b"*64,
        "provider_receipt_id": None, "provider_verified_at": None,
    }
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(CrashHoldUnavailable,match="FIN12_CRASH_SOURCE_NOT_AMBIGUOUS"):
            await record_outcome_hold(conn,tenant_id="t_alpha",outbox_id=INTENT,
                                      opener_subject="accountant-1",
                                      opener_role="accountant",reason="worker_crash")
    assert conn.fetchrow.await_count == 1
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_intent_returns_hold_only_and_is_not_mutated():
    conn=AsyncMock()
    conn.is_in_transaction=lambda: True
    row={
        "id": UUID(INTENT), "tenant_id": "t_alpha",
        "state": "unknown", "source_type": "journal_draft",
        "source_id": "41", "target_system": "balance",
        "idempotency_key": "a"*64, "payload_sha256": "b"*64,
        "provider_receipt_id": None, "provider_verified_at": None,
    }
    conn.fetchrow.side_effect=[row, {"id": UUID("ed0cf3e4-e8a7-429d-aa59-7166d30ff040")}]
    with authenticated_tenant_context("t_alpha"):
        result=await record_outcome_hold(conn,tenant_id="t_alpha",outbox_id=INTENT,
                                         opener_subject="accountant-1",
                                         opener_role="accountant",reason="missing_lease")
    assert result["state"] == "manual_hold"
    assert result["provider_verified"] is False
    assert result["retry_allowed"] is False
    assert result["dispatch_allowed"] is False
    assert result["confirm_allowed"] is False
    assert result["ledger_write_allowed"] is False
    assert conn.fetchrow.await_count == 2
    conn.execute.assert_not_awaited()
