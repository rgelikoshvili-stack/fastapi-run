"""FIN-12: durable, tenant-scoped ERP mutation *intents* (NO DISPATCH).

Only a reviewed source transaction can prepare an intent. No connector or
network call is present. UNKNOWN outcomes always require independent vendor
reconciliation, never an automatic external retry. The source-table migration
is a separate unapplied Draft and does not activate any posting flow.
"""
import hashlib
import json

from app.api.db import _q, require_current_tenant_id, _validate_tenant_id

_TARGETS = frozenset({"balance", "onec", "oris"})


class PostingOutboxUnavailable(ValueError):
    pass


def _deny(code="OUTBOX_INTENT_INVALID"):
    raise PostingOutboxUnavailable(code)


def _canonical_payload(payload):
    if not isinstance(payload, dict) or not payload:
        _deny()
    try:
        text = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        _deny()
    if len(text) > 1024 * 1024:
        _deny()
    return text


def _ids(tenant_id, source_id, target_system):
    try:
        _validate_tenant_id(tenant_id)
        require_current_tenant_id(tenant_id)
    except ValueError:
        _deny("OUTBOX_TENANT_UNAUTHORIZED")
    if (not isinstance(source_id, str) or not source_id.strip()
            or source_id != source_id.strip() or len(source_id) > 256):
        _deny()
    if target_system not in _TARGETS:
        _deny()
    identity = json.dumps(
        ["bridge-erp-intent-v1", tenant_id, "journal_draft", source_id, target_system],
        separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _attest_stored_intent(row, *, tenant_id, source_id, target_system,
                          canonical_payload):
    """Fail closed on forged/stale DB idempotency or stored JSONB mismatch.

    A successful check certifies ONLY local identity+payload consistency,
    never provider-certified idempotency, receipt or permission to dispatch.
    Does not mutate records or make any external calls.
    """
    from uuid import UUID

    try:
        stored = dict(row)
        recorded = stored["payload_json"]
        if isinstance(recorded, str):
            recorded = json.loads(recorded)
        # PostgreSQL JSONB may reorder object keys. The exact canonical
        # encoding used by the original producer must be reconstructed.
        stored_canonical = _canonical_payload(recorded)
        expected_key = _ids(tenant_id, source_id, target_system)
        expected_sha = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
        stored_sha = hashlib.sha256(stored_canonical.encode("utf-8")).hexdigest()
        uid = str(UUID(str(stored["id"])))
    except (ValueError, TypeError, KeyError, AttributeError,
            OverflowError, PostingOutboxUnavailable):
        _deny("OUTBOX_STORED_INTENT_INTEGRITY_FAILED")
    if (stored.get("tenant_id") != tenant_id
            or stored.get("source_type") != "journal_draft"
            or stored.get("source_id") != source_id
            or stored.get("target_system") != target_system
            or stored.get("idempotency_key") != expected_key
            or stored.get("payload_sha256") != stored_sha
            or stored.get("state") not in (
                "prepared", "in_flight", "unknown", "confirmed", "rejected"
            )):
        _deny("OUTBOX_STORED_INTENT_INTEGRITY_FAILED")
    if stored_sha != expected_sha:
        _deny("OUTBOX_INTENT_CONFLICT")
    return {
        "intent_id": uid, "state": stored["state"],
        "idempotency_key": expected_key, "payload_sha256": stored_sha,
        "local_integrity_checked": True,
        "provider_verified": False, "vendor_idempotency_certified": False,
        "dispatch_allowed": False, "retry_allowed": False,
        "confirm_allowed": False, "ledger_write_allowed": False,
    }


async def prepare_posting_intent(conn, *, tenant_id, source_id, target_system, payload):
    """Record before any vendor request, within the caller's DB transaction.

    Concurrent same-source requests converge on one durable intent. A changed
    amount/payload cannot silently reuse an idempotency key. No live I/O.
    """
    key = _ids(tenant_id, source_id, target_system)
    if conn.is_in_transaction() is not True:
        _deny("OUTBOX_TRANSACTION_REQUIRED")
    canonical = _canonical_payload(payload)
    if payload.get("tenant_id") not in (None, tenant_id):
        _deny("OUTBOX_TENANT_UNAUTHORIZED")
    payload_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    try:
        row = await conn.fetchrow(_q("""
            INSERT INTO posting_outbox_intents(
                tenant_id, source_type, source_id, target_system,
                idempotency_key, payload_sha256, payload_json
            ) VALUES (%s,'journal_draft',%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (tenant_id,source_type,source_id,target_system)
            DO NOTHING
            RETURNING id, tenant_id, source_type, source_id, target_system,
                      state, idempotency_key, payload_sha256, payload_json
        """), tenant_id, source_id, target_system, key, payload_sha, canonical)
        if row is None:
            row = await conn.fetchrow(_q("""
                SELECT id, tenant_id, source_type, source_id, target_system,
                       state, idempotency_key, payload_sha256, payload_json
                FROM posting_outbox_intents
                WHERE tenant_id=%s AND source_type='journal_draft'
                  AND source_id=%s AND target_system=%s
            """), tenant_id, source_id, target_system)
    except Exception:
        _deny("OUTBOX_STORAGE_UNAVAILABLE")
    if row is None:
        _deny("OUTBOX_INTENT_CONFLICT")
    return _attest_stored_intent(
        row, tenant_id=tenant_id, source_id=source_id,
        target_system=target_system, canonical_payload=canonical,
    )


def delivery_decision(state):
    """Never blindly retry a live external mutation; no dispatch worker exists."""
    if state == "unknown":
        return "RECONCILIATION_REQUIRED"
    if state == "prepared":
        return "VENDOR_IDEMPOTENCY_APPROVAL_REQUIRED"
    if state == "in_flight":
        return "OUTCOME_PENDING"
    if state in {"confirmed", "rejected"}:
        return "NO_ACTION"
    return "HOLD_UNRECOGNIZED_STATE"
