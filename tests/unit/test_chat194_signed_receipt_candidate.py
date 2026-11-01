"""Chat194 FIN-12 RED tests: synthetic signed receipt != real ERP acceptance.

All keys and timestamps are disposable synthetic test material only.
No provider/network/production/ERP interaction.
"""
import base64
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.api.db import authenticated_tenant_context
from app.api.services.signed_receipt_candidate_service import (
    SyntheticReceiptUntrusted, canonical_synthetic_message,
    verify_synthetic_receipt_candidate, record_synthetic_receipt_candidate,
)

_TEST_SECRET = bytes(range(1, 33))  # inert deterministic TEST fixture, never a production secret.
_TEST_SIGNER = Ed25519PrivateKey.from_private_bytes(_TEST_SECRET)
_PIN = _TEST_SIGNER.public_key().public_bytes_raw()
_NOW = datetime(2026, 10, 30, 17, 0, tzinfo=timezone.utc)
_ID = "dd17459f-b2f7-4ae0-bdba-4df9bd49c251"


def _source(**changes):
    base = {
        "id": UUID(_ID), "tenant_id": "t_alpha", "source_type": "journal_draft",
        "source_id": "draft41", "target_system": "balance",
        "idempotency_key": "a" * 64, "payload_sha256": "b" * 64,
        "state": "unknown", "provider_receipt_id": None, "provider_verified_at": None,
    }
    return {**base, **changes}


def _envelope(**changes):
    payload = {
        "version": 1, "key_id": "synthetic-issuer-1", "issued_at": "2026-10-30T17:00:00Z",
        "tenant_id": "t_alpha", "outbox_id": _ID, "source_id": "draft41",
        "target_system": "balance", "idempotency_key": "a"*64,
        "payload_sha256": "b"*64, "provider_receipt_id": "fake-receipt-41",
        "outcome": "accepted",
    }
    return {**payload, **changes}


def _sign(envelope, key=_TEST_SIGNER):
    return base64.b64encode(key.sign(canonical_synthetic_message(envelope))).decode("ascii")


def _verify(envelope, signature, *, source=None, tenant="t_alpha", **kwargs):
    key_id = kwargs.pop("trusted_key_id", "synthetic-issuer-1")
    key_data = kwargs.pop("trusted_public_key", _PIN)
    with authenticated_tenant_context(tenant):
        return verify_synthetic_receipt_candidate(
            envelope=envelope, signature_b64=signature,
            trusted_key_id=key_id, trusted_public_key=key_data,
            source=source if source is not None else _source(),
            now=_NOW, **kwargs,
        )


def test_valid_synthetic_signature_never_claims_erp_receipt_or_approval():
    env = _envelope()
    proof = _verify(env, _sign(env))
    assert proof["synthetic_integrity_ok"] is True
    assert proof["vendor_authenticated"] is False
    assert proof["provider_verified"] is False
    assert proof["dispatch_allowed"] is False
    assert proof["retry_allowed"] is False
    assert proof["confirm_allowed"] is False
    assert proof["ledger_write_allowed"] is False
    assert proof["outbox_id"] == _ID
    assert len(proof["envelope_sha256"]) == 64
    assert len(proof["signature_sha256"]) == 64


@pytest.mark.parametrize("name,val", [
    ("tenant_id", "t_beta"), ("outbox_id", "dd17459f-b2f7-4ae0-bdba-4df9bd49c252"),
    ("source_id", "draft42"), ("target_system", "onec"),
    ("idempotency_key", "c"*64), ("payload_sha256", "d"*64),
    ("provider_receipt_id", ""), ("outcome", "posted"),
    ("issued_at", "2026-10-01T00:00:00Z"), ("issued_at", "2026-10-31T17:00:00Z"),
    ("version", 2), ("key_id", "unknown-issuer"),
])
def test_mutated_envelope_denied_even_if_resigned_by_synthetic_test_key(name, val):
    env = _envelope(**{name: val})
    with pytest.raises(SyntheticReceiptUntrusted):
        _verify(env, _sign(env))


@pytest.mark.parametrize("source", [
    _source(tenant_id="t_beta"), _source(state="prepared"),
    _source(state="confirmed"), _source(provider_verified_at=_NOW),
    _source(provider_receipt_id="already-present"), _source(idempotency_key="0"*64),
    _source(target_system="oris"), _source(source_type="not-journal"),
])
def test_source_or_terminal_state_mismatch_never_becomes_verified(source):
    env = _envelope()
    with pytest.raises(SyntheticReceiptUntrusted):
        _verify(env, _sign(env), source=source)


def test_signature_tampering_and_untrusted_key_denied():
    env = _envelope()
    sig = _sign(env)
    with pytest.raises(SyntheticReceiptUntrusted):
        _verify(env, base64.b64encode(b"X"*64).decode())
    with pytest.raises(SyntheticReceiptUntrusted):
        _verify({**env,"provider_receipt_id":"forged"}, sig)
    with pytest.raises(SyntheticReceiptUntrusted):
        _verify(env, sig, trusted_public_key=b"X"*32)
    with pytest.raises(SyntheticReceiptUntrusted):
        _verify(env, sig, trusted_key_id="rotated-other")
    with pytest.raises(SyntheticReceiptUntrusted):
        _verify(env, "@@@")
    with pytest.raises(SyntheticReceiptUntrusted):
        _verify({**env, "trusted_public_key": "attacker-key"}, _sign(env))


def test_invalid_context_and_unsupported_provider_never_authorized():
    env = _envelope()
    with pytest.raises(SyntheticReceiptUntrusted, match="FIN12_RECEIPT_TENANT_UNAUTHORIZED"):
        verify_synthetic_receipt_candidate(
            envelope=env, signature_b64=_sign(env),
            trusted_key_id="synthetic-issuer-1", trusted_public_key=_PIN,
            source=_source(), now=_NOW,
        )
    with pytest.raises(SyntheticReceiptUntrusted):
        _verify(env, _sign(env), tenant="t_beta")


@pytest.mark.asyncio
async def test_receipt_candidate_requires_caller_transaction_before_db_read():
    conn = AsyncMock()
    conn.is_in_transaction = lambda: False
    env = _envelope()
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(SyntheticReceiptUntrusted, match="FIN12_RECEIPT_TRANSACTION_REQUIRED"):
            await record_synthetic_receipt_candidate(
                conn, tenant_id="t_alpha", intent_id=_ID,
                envelope=env, signature_b64=_sign(env),
                trusted_key_id="synthetic-issuer-1", trusted_public_key=_PIN,
                now=_NOW,
            )
    conn.fetchrow.assert_not_awaited()
    conn.execute.assert_not_awaited()
