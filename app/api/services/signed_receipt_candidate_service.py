"""FIN-12 Chat194: cryptographic integrity of SYNTHETIC receipt candidates only.

INERT: no router, no worker, no provider, no ledger, no change to outbox
state. This reference Ed25519 envelope is NOT a claim that Balance.ge,
1C or Oris supplies such signed receipts. Only externally verified vendor
contracts, pinned production keys and approved roles could enable one.

A proof here means ONLY that a synthetic payload was signed by the supplied
pinned TEST key and matches a tenant-bound durable outbox source.
It MUST NOT be treated as real-world vendor confirmation.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.api.db import _q, require_current_tenant_id

_PREFIX = b"BridgeHub:FIN12:TEST-ONLY-receipt-v1\n"
_FIELDS = frozenset({
    "version", "key_id", "issued_at", "tenant_id", "outbox_id",
    "source_id", "target_system", "idempotency_key", "payload_sha256",
    "provider_receipt_id", "outcome",
})
_SHA = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_:.\-/]{1,200}$")
_TARGETS = frozenset({"balance", "onec", "oris"})


class SyntheticReceiptUntrusted(ValueError):
    """Untrusted or unverifiable synthetic receipt is always a hold."""


def _deny(code: str):
    raise SyntheticReceiptUntrusted(code)


def canonical_synthetic_message(envelope) -> bytes:
    """Domain-separated deterministic test envelope; no vendor signing standard."""
    if not isinstance(envelope, dict):
        _deny("FIN12_RECEIPT_ENVELOPE_INVALID")
    try:
        encoded = json.dumps(
            envelope, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError):
        _deny("FIN12_RECEIPT_ENVELOPE_INVALID")
    if len(encoded) > 8192:
        _deny("FIN12_RECEIPT_ENVELOPE_TOO_LARGE")
    return _PREFIX + encoded


def _scope(tenant_id: str) -> None:
    try:
        require_current_tenant_id(tenant_id)
    except (TypeError, ValueError):
        _deny("FIN12_RECEIPT_TENANT_UNAUTHORIZED")


def _canonical_uuid(value) -> str:
    if not isinstance(value, (str, UUID)):
        _deny("FIN12_RECEIPT_INTENT_ID_INVALID")
    try:
        canonical = str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        _deny("FIN12_RECEIPT_INTENT_ID_INVALID")
    if str(value) != canonical:
        _deny("FIN12_RECEIPT_INTENT_ID_INVALID")
    return canonical


def _safe_str(value):
    return isinstance(value, str) and _SAFE_ID.fullmatch(value) is not None


def _checked_envelope(envelope, *, now: datetime, expected_key_id: str):
    if (not isinstance(envelope, dict) or frozenset(envelope) != _FIELDS
            or type(envelope.get("version")) is not int
            or envelope["version"] != 1):
        _deny("FIN12_RECEIPT_ENVELOPE_UNSUPPORTED")
    if (not isinstance(expected_key_id, str)
            or not expected_key_id.startswith("synthetic-")
            or not _safe_str(expected_key_id)
            or envelope["key_id"] != expected_key_id):
        _deny("FIN12_RECEIPT_SIGNER_NOT_PINNED")
    if envelope.get("target_system") not in _TARGETS:
        _deny("FIN12_RECEIPT_TARGET_UNSUPPORTED")
    if envelope.get("outcome") not in ("accepted", "rejected"):
        _deny("FIN12_RECEIPT_OUTCOME_UNSUPPORTED")
    for field in ("tenant_id", "source_id", "provider_receipt_id"):
        if not _safe_str(envelope.get(field)):
            _deny("FIN12_RECEIPT_IDENTITY_INVALID")
    _canonical_uuid(envelope.get("outbox_id"))
    for field in ("idempotency_key", "payload_sha256"):
        if not isinstance(envelope.get(field), str) or not _SHA.fullmatch(envelope[field]):
            _deny("FIN12_RECEIPT_HASH_INVALID")
    if not isinstance(now, datetime) or now.tzinfo is None:
        _deny("FIN12_RECEIPT_CLOCK_UNTRUSTED")
    if now.utcoffset() != timedelta(0):
        _deny("FIN12_RECEIPT_CLOCK_UNTRUSTED")
    stamp = envelope.get("issued_at")
    if (not isinstance(stamp, str)
            or re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", stamp) is None):
        _deny("FIN12_RECEIPT_TIMESTAMP_INVALID")
    try:
        issued = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        _deny("FIN12_RECEIPT_TIMESTAMP_INVALID")
    if not now - timedelta(minutes=10) <= issued <= now + timedelta(minutes=2):
        _deny("FIN12_RECEIPT_TIMESTAMP_OUT_OF_WINDOW")


def _checked_source(source, envelope):
    try:
        row = dict(source)
    except (TypeError, ValueError):
        _deny("FIN12_RECEIPT_SOURCE_UNAVAILABLE")
    if (str(row.get("id")) != envelope["outbox_id"]
            or row.get("tenant_id") != envelope["tenant_id"]
            or row.get("source_type") != "journal_draft"
            or row.get("source_id") != envelope["source_id"]
            or row.get("target_system") != envelope["target_system"]
            or row.get("idempotency_key") != envelope["idempotency_key"]
            or row.get("payload_sha256") != envelope["payload_sha256"]
            or row.get("state") not in ("unknown", "in_flight")
            or row.get("provider_receipt_id") is not None
            or row.get("provider_verified_at") is not None):
        _deny("FIN12_RECEIPT_SOURCE_MISMATCH")


def verify_synthetic_receipt_candidate(
    *, envelope, signature_b64: str,
    trusted_key_id: str, trusted_public_key: bytes,
    source, now: datetime,
) -> dict:
    """Integrity proof, NOT provider verification and NEVER posting authority.

    trusted_key_id/public_key MUST come from a trusted internal test fixture,
    not from the envelope, a public endpoint or a user/LLM tool. The production
    vendor-authentication contract is not specified or supported here.
    """
    if not isinstance(envelope, dict):
        _deny("FIN12_RECEIPT_ENVELOPE_INVALID")
    _scope(envelope.get("tenant_id"))
    _checked_envelope(envelope, now=now, expected_key_id=trusted_key_id)
    _checked_source(source, envelope)
    if (not isinstance(trusted_public_key, bytes) or len(trusted_public_key) != 32
            or not isinstance(signature_b64, str) or len(signature_b64) > 128):
        _deny("FIN12_RECEIPT_SIGNATURE_UNTRUSTED")
    try:
        signature = base64.b64decode(signature_b64, validate=True)
        if len(signature) != 64 or base64.b64encode(signature).decode() != signature_b64:
            _deny("FIN12_RECEIPT_SIGNATURE_UNTRUSTED")
        Ed25519PublicKey.from_public_bytes(trusted_public_key).verify(
            signature, canonical_synthetic_message(envelope)
        )
    except (ValueError, InvalidSignature, binascii.Error):
        _deny("FIN12_RECEIPT_SIGNATURE_UNTRUSTED")
    return {
        "outbox_id": envelope["outbox_id"],
        "tenant_id": envelope["tenant_id"],
        "provider_receipt_id": envelope["provider_receipt_id"],
        "outcome": envelope["outcome"],
        "key_id": envelope["key_id"],
        "envelope_sha256": hashlib.sha256(
            canonical_synthetic_message(envelope)
        ).hexdigest(),
        "signature_sha256": hashlib.sha256(signature).hexdigest(),
        "synthetic_integrity_ok": True,
        "vendor_authenticated": False,
        "provider_verified": False,
        "confirm_allowed": False,
        "dispatch_allowed": False,
        "retry_allowed": False,
        "ledger_write_allowed": False,
    }


async def record_synthetic_receipt_candidate(
    conn, *, tenant_id: str, intent_id,
    envelope, signature_b64: str,
    trusted_key_id: str, trusted_public_key: bytes, now: datetime,
) -> dict:
    """Append synthetic integrity observation, never to the real receipt table.

    Requires the caller's existing trusted tenant transaction and an independent
    temporary draft schema; no runtime routing or external side effects.
    """
    _scope(tenant_id)
    if conn.is_in_transaction() is not True:
        _deny("FIN12_RECEIPT_TRANSACTION_REQUIRED")
    uid = _canonical_uuid(intent_id)
    if not isinstance(envelope, dict) or envelope.get("tenant_id") != tenant_id:
        _deny("FIN12_RECEIPT_TENANT_UNAUTHORIZED")
    try:
        row = await conn.fetchrow(_q("""
            SELECT id,tenant_id,source_type,source_id,target_system,
                   idempotency_key,payload_sha256,state,
                   provider_receipt_id,provider_verified_at
              FROM posting_outbox_intents
             WHERE id=%s AND tenant_id=%s
        """), UUID(uid), tenant_id)
    except Exception:
        _deny("FIN12_RECEIPT_SOURCE_STORAGE_UNAVAILABLE")
    if row is None:
        _deny("FIN12_RECEIPT_SOURCE_NOT_FOUND")
    proof = verify_synthetic_receipt_candidate(
        envelope=envelope, signature_b64=signature_b64,
        trusted_key_id=trusted_key_id, trusted_public_key=trusted_public_key,
        source=row, now=now,
    )
    try:
        saved = await conn.fetchrow(_q("""
            INSERT INTO posting_outbox_receipt_candidates
                (tenant_id,outbox_id,source_id,target_system,
                 idempotency_key,payload_sha256,provider_receipt_id,outcome,
                 signer_key_id,envelope_sha256,signature_sha256)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """), tenant_id, UUID(uid), envelope["source_id"],
            envelope["target_system"], envelope["idempotency_key"],
            envelope["payload_sha256"], envelope["provider_receipt_id"],
            envelope["outcome"], envelope["key_id"],
            proof["envelope_sha256"], proof["signature_sha256"])
    except Exception:
        _deny("FIN12_RECEIPT_CANDIDATE_STORAGE_CONFLICT")
    if saved is None:
        _deny("FIN12_RECEIPT_CANDIDATE_STORAGE_CONFLICT")
    return {"candidate_id": str(saved["id"]), **proof}
