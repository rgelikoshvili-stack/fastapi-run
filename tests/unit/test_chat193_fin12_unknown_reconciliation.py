"""FIN-12 Chat193: UNKNOWN outcome manual investigation remains a HOLD.

These tests exercise only inert service logic; no vendor, network or live DB.
"""
from unittest.mock import AsyncMock

import pytest

from app.api.db import authenticated_tenant_context
from app.api.services.posting_outbox_reconciliation_service import (
    ManualReconciliationUnavailable, _actor, _evidence, _hold_decision,
    open_unknown_reconciliation, review_unknown_reconciliation,
)


@pytest.mark.parametrize("state", ["prepared", "in_flight", "unknown",
                                   "confirmed", "rejected", "bad", None])
def test_observation_never_authorizes_external_retry_or_terminal_posting(state):
    decision = _hold_decision(state)
    assert decision["dispatch_allowed"] is False
    assert decision["confirm_allowed"] is False
    assert decision["retry_allowed"] is False
    assert decision["ledger_write_allowed"] is False
    assert decision["next_action"] in ("MANUAL_RECONCILIATION_HOLD", "NOT_ELIGIBLE")


@pytest.mark.parametrize("subject,role,phase", [
    ("", "accountant", "opener"),
    ("anon", "accountant", "opener"),
    ("system", "admin", "opener"),
    ("maker-1", "viewer", "opener"),
    (" maker-1 ", "accountant", "opener"),
    ("cfo-1", "reviewer", "reviewer"),
    ("cfo-1", "accountant", "reviewer"),
    ("admin-1", "superuser", "reviewer"),
])
def test_unverified_actor_or_role_denied(subject, role, phase):
    with pytest.raises(ManualReconciliationUnavailable):
        _actor(subject, role, phase)


@pytest.mark.parametrize("claim", ["claimed_accepted","claimed_rejected","undetermined"])
def test_operator_claim_is_unverified_evidence_not_provider_receipt(claim):
    record = _evidence(claim, "a"*64)
    assert record["claimed_outcome"] == claim
    assert record["evidence_sha256"] == "a"*64
    assert record["provider_verified"] is False


@pytest.mark.parametrize("claim,digest", [
    ("accepted", "a"*64), ("confirmed", "a"*64),
    ("unknown", "a"*64), ("claimed_accepted", "g"*64),
    ("claimed_rejected", "A"*64), ("undetermined", ""),
])
def test_unsupported_claim_or_untrusted_digest_denied(claim, digest):
    with pytest.raises(ManualReconciliationUnavailable):
        _evidence(claim, digest)


@pytest.mark.asyncio
async def test_no_tenant_context_or_cross_tenant_denied_before_db_write():
    conn = AsyncMock()
    conn.is_in_transaction = lambda: True
    with pytest.raises(ManualReconciliationUnavailable, match="FIN12_RECON_TENANT_UNAUTHORIZED"):
        await open_unknown_reconciliation(
            conn, tenant_id="t_alpha", intent_id="dd17459f-b2f7-4ae0-bdba-4df9bd49c251",
            opener_subject="acct-1", opener_role="accountant",
            claimed_outcome="undetermined", evidence_sha256="a"*64,
        )
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(ManualReconciliationUnavailable, match="FIN12_RECON_TENANT_UNAUTHORIZED"):
            await open_unknown_reconciliation(
                conn, tenant_id="t_beta", intent_id="dd17459f-b2f7-4ae0-bdba-4df9bd49c251",
                opener_subject="acct-1", opener_role="accountant",
                claimed_outcome="undetermined", evidence_sha256="a"*64,
            )
    conn.fetchrow.assert_not_awaited()
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_autocommit_and_invalid_intent_fail_before_db_touch():
    conn = AsyncMock()
    conn.is_in_transaction = lambda: False
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(ManualReconciliationUnavailable, match="FIN12_RECON_TRANSACTION_REQUIRED"):
            await open_unknown_reconciliation(
                conn, tenant_id="t_alpha", intent_id="dd17459f-b2f7-4ae0-bdba-4df9bd49c251",
                opener_subject="acct-1", opener_role="accountant",
                claimed_outcome="undetermined", evidence_sha256="a"*64,
            )
    conn.fetchrow.assert_not_awaited()
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_self_review_refused_without_writes():
    conn = AsyncMock()
    conn.is_in_transaction = lambda: True
    intent = {
        "id": "dd17459f-b2f7-4ae0-bdba-4df9bd49c251",
        "tenant_id": "t_alpha", "state": "unknown",
        "source_type": "journal_draft", "source_id": "41",
        "target_system": "balance", "idempotency_key": "b"*64,
        "payload_sha256": "c"*64,
        "provider_receipt_id": None, "provider_verified_at": None,
    }
    case = {
        "id": 8, "tenant_id": "t_alpha",
        "outbox_id": intent["id"], "state": "open",
        "opener_subject": "acct-1", "opener_role": "accountant",
        "claimed_outcome": "undetermined", "evidence_sha256": "a"*64,
        "source_id": "41", "target_system": "balance",
        "idempotency_key": "b"*64, "payload_sha256": "c"*64,
    }
    conn.fetchrow.side_effect = [intent, case]
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(ManualReconciliationUnavailable, match="FIN12_RECON_SELF_REVIEW_DENIED"):
            await review_unknown_reconciliation(
                conn, tenant_id="t_alpha", intent_id=intent["id"],
                reviewer_subject="acct-1", reviewer_role="cfo",
            )
    conn.execute.assert_not_awaited()
