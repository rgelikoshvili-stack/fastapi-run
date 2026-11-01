"""Chat200 FIN-12: read-only local ledger/outbox anomaly detection.

NOT a new posting path, vendor receipt validator, recovery workflow or
proof of atomic commit.  An authenticated tenant-scoped caller may inspect a
source with the SAME active DB transaction and record no writes.  If the ledger
already has a posted source while ERP intent remains unverified, this is a
manual-investigation HOLD; NEVER silently accept, delete, backfill or retry it.

Standalone/unregistered: no router, worker, network access, DDL, or real ERP.
"""
from __future__ import annotations

from app.api.services.posting_outbox_intent_service import (
    PostingOutboxUnavailable, _ids, _canonical_payload, _attest_stored_intent,
)
from app.api.db import _q


class LocalAtomicityUnavailable(ValueError):
    """No release/dispatch authority can be inferred from partial local state."""


def _deny(code):
    raise LocalAtomicityUnavailable(code)


async def inspect_local_ledger_outbox_pair(
    conn, *, tenant_id: str, source_id: str, target_system: str, payload: dict
) -> dict:
    """Inspect source linkage inside the CALLER's transaction, without mutation.

    Absence of ledger is NOT proof of atomic commit, provider outcome, complete
    source history or safe retry. An already posted ledger with no independently
    vendor-authenticated outbox receipt is a manual HOLD.
    """
    try:
        _ids(tenant_id, source_id, target_system)
    except PostingOutboxUnavailable:
        _deny("FIN12_LOCAL_TENANT_UNAUTHORIZED")
    if conn.is_in_transaction() is not True:
        _deny("FIN12_LOCAL_TRANSACTION_REQUIRED")
    try:
        canonical = _canonical_payload(payload)
        if payload.get("tenant_id") not in (None, tenant_id):
            _deny("FIN12_LOCAL_TENANT_UNAUTHORIZED")
    except PostingOutboxUnavailable:
        _deny("FIN12_LOCAL_OUTBOX_INTEGRITY_FAILED")

    try:
        row = await conn.fetchrow(_q("""
            SELECT id,tenant_id,source_type,source_id,target_system,state,
                   idempotency_key,payload_sha256,payload_json
            FROM posting_outbox_intents
            WHERE tenant_id=%s AND source_type='journal_draft'
              AND source_id=%s AND target_system=%s
        """), tenant_id, source_id, target_system)
    except Exception:
        _deny("FIN12_LOCAL_OUTBOX_READ_UNAVAILABLE")
    if row is None:
        _deny("FIN12_LOCAL_OUTBOX_NOT_FOUND")
    try:
        verified_local = _attest_stored_intent(
            row, tenant_id=tenant_id, source_id=source_id,
            target_system=target_system, canonical_payload=canonical,
        )
    except PostingOutboxUnavailable:
        _deny("FIN12_LOCAL_OUTBOX_INTEGRITY_FAILED")

    # A preexisting terminal state is NOT vendor proof in the absence of a
    # verified contract/receipt. Never convert this to release authority.
    if verified_local["state"] in ("confirmed", "rejected"):
        _deny("FIN12_LOCAL_TERMINAL_VENDOR_UNVERIFIED")
    try:
        sources = await conn.fetch(_q("""
            SELECT s.journal_entry_id,h.status,h.tenant_id AS header_tenant,
                   h.source_type AS header_source_type
              FROM journal_entry_sources s
              LEFT JOIN journal_entry_headers h
                ON h.id=s.journal_entry_id AND h.tenant_id=s.tenant_id
             WHERE s.tenant_id=%s AND s.source_type='journal_draft'
               AND s.source_id=%s
             LIMIT 2
        """), tenant_id, source_id)
    except Exception:
        _deny("FIN12_LOCAL_LEDGER_READ_UNAVAILABLE")

    if len(sources) > 1:
        _deny("FIN12_LOCAL_DUPLICATE_LEDGER_SOURCE")
    if sources:
        # Even an orphaned/invalid/posted/reversed local link is not proof
        # that an ERP mutation was accepted. Historical data remains intact.
        _deny("FIN12_LOCAL_LEDGER_OUTBOX_UNVERIFIED")

    return {
        "intent_id": verified_local["intent_id"],
        "state": verified_local["state"],
        "ledger_source_present": False,
        "local_outbox_integrity_checked": True,
        "local_atomic_commit_proven": False,
        "provider_verified": False,
        "dispatch_allowed": False,
        "retry_allowed": False,
        "confirm_allowed": False,
        "ledger_write_allowed": False,
        "next_action": (
            "MANUAL_OUTCOME_HOLD"
            if verified_local["state"] in ("unknown", "in_flight")
            else "VENDOR_CONTRACT_HOLD"
        ),
    }
