"""Chat200 FIN-12 RED: locally posted ledger must not certify pending ERP intent.

No provider call, worker, live migration or production ledger mutation.
This tests an unregistered, strictly READ-ONLY diagnostic preflight.
"""
from unittest.mock import AsyncMock
from uuid import UUID
import hashlib
import pytest

from app.api.db import authenticated_tenant_context
from app.api.services.posting_outbox_intent_service import _ids, _canonical_payload
from app.api.services.fin12_local_atomicity_guard import (
    LocalAtomicityUnavailable, inspect_local_ledger_outbox_pair,
)


IID = UUID("dd17459f-b2f7-4ae0-bdba-4df9bd49c251")
PAYLOAD = {"tenant_id": "t_alpha", "currency": "GEL", "amount": "100.01"}


def _stored(source="draft200", **kw):
    canonical = _canonical_payload(PAYLOAD)
    with authenticated_tenant_context("t_alpha"):
        key = _ids("t_alpha", source, "balance")
    return {
        "id": IID, "tenant_id": "t_alpha", "source_type": "journal_draft",
        "source_id": source, "target_system": "balance", "state": "prepared",
        "idempotency_key": key,
        "payload_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "payload_json": PAYLOAD, **kw,
    }


def _conn(row=None, ledger=None, txn=True):
    conn = AsyncMock()
    conn.is_in_transaction = lambda: txn
    conn.fetchrow.return_value = _stored() if row is None else row
    conn.fetch.return_value = [] if ledger is None else ledger
    return conn


@pytest.mark.asyncio
async def test_empty_ledger_is_only_pending_diagnostic_not_vendor_authority():
    conn = _conn()
    with authenticated_tenant_context("t_alpha"):
        result = await inspect_local_ledger_outbox_pair(
            conn, tenant_id="t_alpha", source_id="draft200",
            target_system="balance", payload=PAYLOAD,
        )
    assert result["ledger_source_present"] is False
    assert result["local_outbox_integrity_checked"] is True
    assert result["local_atomic_commit_proven"] is False
    for flag in ("dispatch_allowed", "retry_allowed", "confirm_allowed",
                 "ledger_write_allowed", "provider_verified"):
        assert result[flag] is False
    conn.execute.assert_not_awaited()
    assert conn.fetchrow.await_count == 1
    assert conn.fetch.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("row", [
    {"journal_entry_id": IID, "status": "posted", "header_tenant": "t_alpha"},
    {"journal_entry_id": IID, "status": "correction", "header_tenant": "t_alpha"},
    {"journal_entry_id": None, "status": None, "header_tenant": None},
])
async def test_any_ledger_source_with_unverified_outbox_fails_closed(row):
    conn = _conn(ledger=[row])
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(LocalAtomicityUnavailable, match="FIN12_LOCAL_LEDGER_OUTBOX_UNVERIFIED"):
            await inspect_local_ledger_outbox_pair(
                conn, tenant_id="t_alpha", source_id="draft200",
                target_system="balance", payload=PAYLOAD,
            )
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_ledger_source_is_always_manual_hold():
    row = {"journal_entry_id": IID, "status": "posted", "header_tenant": "t_alpha"}
    conn = _conn(ledger=[row, row])
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(LocalAtomicityUnavailable, match="FIN12_LOCAL_DUPLICATE_LEDGER_SOURCE"):
            await inspect_local_ledger_outbox_pair(
                conn, tenant_id="t_alpha", source_id="draft200",
                target_system="balance", payload=PAYLOAD,
            )


@pytest.mark.asyncio
async def test_modified_outbox_payload_must_not_be_mistaken_for_empty_ledger():
    conn = _conn(row=_stored(payload_json={"amount": "999", "currency": "GEL"}))
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(LocalAtomicityUnavailable, match="FIN12_LOCAL_OUTBOX_INTEGRITY_FAILED"):
            await inspect_local_ledger_outbox_pair(
                conn, tenant_id="t_alpha", source_id="draft200",
                target_system="balance", payload=PAYLOAD,
            )
    conn.fetch.assert_not_awaited()
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirmed_state_cannot_be_certified_without_real_vendor_receipt():
    conn = _conn(row=_stored(state="confirmed"))
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(LocalAtomicityUnavailable, match="FIN12_LOCAL_TERMINAL_VENDOR_UNVERIFIED"):
            await inspect_local_ledger_outbox_pair(
                conn, tenant_id="t_alpha", source_id="draft200",
                target_system="balance", payload=PAYLOAD,
            )
    conn.fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_transaction_or_foreign_tenant_denied_before_sql():
    conn = _conn(txn=False)
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(LocalAtomicityUnavailable, match="FIN12_LOCAL_TRANSACTION_REQUIRED"):
            await inspect_local_ledger_outbox_pair(
                conn, tenant_id="t_alpha", source_id="draft200",
                target_system="balance", payload=PAYLOAD,
            )
    conn.is_in_transaction = lambda: True
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(LocalAtomicityUnavailable, match="FIN12_LOCAL_TENANT_UNAUTHORIZED"):
            await inspect_local_ledger_outbox_pair(
                conn, tenant_id="t_beta", source_id="draft200",
                target_system="balance", payload=PAYLOAD,
            )
    conn.fetchrow.assert_not_awaited()
    conn.fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_outbox_never_auto_retries_even_without_local_ledger():
    conn = _conn(row=_stored(state="unknown"))
    with authenticated_tenant_context("t_alpha"):
        result = await inspect_local_ledger_outbox_pair(
            conn, tenant_id="t_alpha", source_id="draft200",
            target_system="balance", payload=PAYLOAD,
        )
    assert result["next_action"] == "MANUAL_OUTCOME_HOLD"
    assert result["retry_allowed"] is False
    assert result["local_atomic_commit_proven"] is False
