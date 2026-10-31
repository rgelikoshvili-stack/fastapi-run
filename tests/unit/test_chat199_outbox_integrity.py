"""Chat199 FIN-12: local identity/payload integrity != vendor idempotency.

Regression-first, deterministic synthetic input only. No ERP/worker/secret.
"""
import hashlib
import json
from unittest.mock import AsyncMock
from uuid import UUID
import pytest

from app.api.db import authenticated_tenant_context
from app.api.services.posting_outbox_intent_service import (
    PostingOutboxUnavailable, prepare_posting_intent, _attest_stored_intent,
)

ID = UUID("dd17459f-b2f7-4ae0-bdba-4df9bd49c251")


def _identity(tenant="t_alpha", source="draft199", target="balance"):
    value = ["bridge-erp-intent-v1", tenant, "journal_draft", source, target]
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _row(payload=None, **changes):
    payload = payload if payload is not None else {"amount": "100.01", "currency": "GEL"}
    original = {
        "id": ID, "tenant_id": "t_alpha", "source_type": "journal_draft",
        "source_id": "draft199", "target_system": "balance",
        "state": "prepared", "idempotency_key": _identity(),
        "payload_json": json.dumps(payload, sort_keys=False),  # simulates JSONB text codec
        "payload_sha256": hashlib.sha256(_canonical(payload).encode()).hexdigest(),
    }
    return {**original, **changes}


def test_stored_payload_key_order_is_not_a_new_financial_mutation():
    payload = {"currency": "GEL", "amount": "100.01"}
    with authenticated_tenant_context("t_alpha"):
        result = _attest_stored_intent(
            _row(payload), tenant_id="t_alpha", source_id="draft199",
            target_system="balance", canonical_payload=_canonical(payload),
        )
    assert result["state"] == "prepared"
    assert result["dispatch_allowed"] is False
    assert result["retry_allowed"] is False
    assert result["vendor_idempotency_certified"] is False
    assert result["provider_verified"] is False
    assert result["local_integrity_checked"] is True


@pytest.mark.parametrize("delta", [
    {"tenant_id": "t_beta"},
    {"source_type": "provider_invoice"},
    {"source_id": "draft200"},
    {"target_system": "oris"},
    {"idempotency_key": "0"*64},
    {"payload_sha256": "f"*64},
    {"payload_json": '{"amount":"999.99","currency":"GEL"}'},
    {"payload_json": '{"currency":"GEL","amount":true}'},
    {"payload_json": '{"currency":"GEL","amount":1e1000}'},
    {"payload_json": '{"currency":"GEL","amount":"100.01"'},
    {"state": "unknown_wrong_state"},
    {"id": "not-a-uuid"},
])
def test_direct_sql_forgery_of_local_intent_fields_must_fail_closed(delta):
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(PostingOutboxUnavailable, match="OUTBOX_STORED_INTENT_INTEGRITY_FAILED"):
            _attest_stored_intent(
                _row(**delta), tenant_id="t_alpha", source_id="draft199",
                target_system="balance", canonical_payload=_canonical(
                    {"amount":"100.01","currency":"GEL"}
                ),
            )


@pytest.mark.parametrize("state", ["prepared","unknown","in_flight","confirmed","rejected"])
def test_local_integrity_never_authorizes_provider_dispatch_even_terminal_state(state):
    with authenticated_tenant_context("t_alpha"):
        result = _attest_stored_intent(
            _row(state=state), tenant_id="t_alpha", source_id="draft199",
            target_system="balance", canonical_payload=_canonical(
                {"amount":"100.01","currency":"GEL"}
            ),
        )
    assert result["dispatch_allowed"] is False
    assert result["retry_allowed"] is False
    assert result["confirm_allowed"] is False
    assert result["ledger_write_allowed"] is False
    assert result["provider_verified"] is False


@pytest.mark.asyncio
async def test_existing_forged_payload_with_expected_hash_cannot_be_reused():
    conn = AsyncMock()
    conn.is_in_transaction = lambda: True
    # first INSERT ON CONFLICT DOES NOTHING, then returns a malicious old row
    conn.fetchrow.side_effect = [None, _row(payload={"amount": "999.99", "currency": "GEL"},
                                               payload_sha256=_row()["payload_sha256"])]
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(PostingOutboxUnavailable, match="OUTBOX_STORED_INTENT_INTEGRITY_FAILED"):
            await prepare_posting_intent(
                conn, tenant_id="t_alpha", source_id="draft199",
                target_system="balance", payload={"amount":"100.01","currency":"GEL"},
            )
    assert conn.fetchrow.await_count == 2
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_payload_existing_row_is_read_only_and_still_on_external_hold():
    conn = AsyncMock()
    conn.is_in_transaction = lambda: True
    conn.fetchrow.side_effect = [None, _row()]
    with authenticated_tenant_context("t_alpha"):
        response = await prepare_posting_intent(
            conn, tenant_id="t_alpha", source_id="draft199",
            target_system="balance", payload={"amount":"100.01","currency":"GEL"},
        )
    assert response["intent_id"] == str(ID)
    assert response["local_integrity_checked"] is True
    assert response["dispatch_allowed"] is False
    assert response["provider_verified"] is False
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_wrong_tenant_fails_before_db_even_when_row_is_pretend_valid():
    conn = AsyncMock()
    conn.is_in_transaction = lambda: True
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(PostingOutboxUnavailable, match="OUTBOX_TENANT_UNAUTHORIZED"):
            await prepare_posting_intent(
                conn, tenant_id="t_beta", source_id="draft199",
                target_system="balance", payload={"amount":"100.01"},
            )
    conn.fetchrow.assert_not_awaited()
