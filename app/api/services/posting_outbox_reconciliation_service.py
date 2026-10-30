"""FIN-12 Chat193: inert, tenant-scoped manual UNKNOWN investigation.

This module has NO router, worker, ERP connector, callback or network access.
An operator's claim or SHA-256 digest is NOT authenticated provider evidence.
Both open and review leave the original outbox state UNKNOWN: neither can
allow a retry, confirm a posting, or write to the financial ledger.

Caller-owned transaction, authenticated tenant/JWT subject and nonowner
database access are required. Never accept subject/role from untrusted body.
The candidate SQL remains a standalone, unapplied DRAFT.
"""
from __future__ import annotations

import re
from uuid import UUID

from app.api.authz import has_role_permission
from app.api.db import _q, require_current_tenant_id

_TARGETS = frozenset(("balance", "onec", "oris"))
_CLAIMS = frozenset(("claimed_accepted", "claimed_rejected", "undetermined"))
_SHA = re.compile(r"^[0-9a-f]{64}$")


class ManualReconciliationUnavailable(ValueError):
    """Fail closed: manual inspection cannot be mistaken for ERP confirmation."""


def _deny(code: str):
    raise ManualReconciliationUnavailable(code)


def _hold_decision(state) -> dict:
    return {
        "next_action": "MANUAL_RECONCILIATION_HOLD"
        if state == "unknown" else "NOT_ELIGIBLE",
        "retry_allowed": False,
        "dispatch_allowed": False,
        "confirm_allowed": False,
        "ledger_write_allowed": False,
        "provider_verified": False,
    }


def _actor(subject: str, role: str, phase: str) -> str:
    """Role/shape check only. Trusted JWT subject binding is a future gate."""
    if (not isinstance(subject, str) or not 1 <= len(subject) <= 200
            or subject != subject.strip()
            or subject.casefold() in ("system", "anon", "anonymous",
                                      "human", "default")
            or any(ord(ch) <= 32 or ord(ch) == 127 for ch in subject)):
        _deny("FIN12_RECON_AUTHENTICATED_ACTOR_REQUIRED")
    if phase == "opener":
        allowed, permission = {"accountant", "admin"}, "approval:write"
    elif phase == "reviewer":
        allowed, permission = {"cfo", "admin"}, "approval:cfo"
    else:
        _deny("FIN12_RECON_INVALID_PHASE")
    if role not in allowed or not has_role_permission(role, permission):
        _deny("FIN12_RECON_ROLE_FORBIDDEN")
    return subject


def _evidence(claimed_outcome: str, evidence_sha256: str) -> dict:
    """An unverified manual claim and digest, NOT a vendor-signed receipt."""
    if claimed_outcome not in _CLAIMS:
        _deny("FIN12_RECON_CLAIM_INVALID")
    if not isinstance(evidence_sha256, str) or not _SHA.fullmatch(evidence_sha256):
        _deny("FIN12_RECON_EVIDENCE_DIGEST_INVALID")
    return {
        "claimed_outcome": claimed_outcome,
        "evidence_sha256": evidence_sha256,
        "provider_verified": False,
    }


def _scope(conn, tenant_id: str, intent_id) -> UUID:
    try:
        require_current_tenant_id(tenant_id)
    except ValueError:
        _deny("FIN12_RECON_TENANT_UNAUTHORIZED")
    if conn.is_in_transaction() is not True:
        _deny("FIN12_RECON_TRANSACTION_REQUIRED")
    try:
        if not isinstance(intent_id, (str, UUID)):
            _deny("FIN12_RECON_ID_INVALID")
        uid = UUID(str(intent_id))
        if str(uid) != str(intent_id):
            _deny("FIN12_RECON_ID_INVALID")
        return uid
    except (ValueError, AttributeError, TypeError):
        _deny("FIN12_RECON_ID_INVALID")


async def _source(conn, *, tenant_id: str, intent_uuid: UUID) -> dict:
    row = await conn.fetchrow(_q("""
        SELECT id,tenant_id,state,source_type,source_id,target_system,
               idempotency_key,payload_sha256,
               provider_receipt_id,provider_verified_at
          FROM posting_outbox_intents
         WHERE id=%s AND tenant_id=%s
         FOR UPDATE
    """), intent_uuid, tenant_id)
    if row is None:
        _deny("FIN12_RECON_SOURCE_NOT_FOUND")
    source = dict(row)
    if source["state"] != "unknown":
        _deny("FIN12_RECON_SOURCE_NOT_UNKNOWN")
    if (source["tenant_id"] != tenant_id
            or source["source_type"] != "journal_draft"
            or source["target_system"] not in _TARGETS
            or not isinstance(source["source_id"], str)
            or not source["source_id"].strip()
            or not _SHA.fullmatch(source["idempotency_key"])
            or not _SHA.fullmatch(source["payload_sha256"])
            or source["provider_receipt_id"] is not None
            or source["provider_verified_at"] is not None):
        _deny("FIN12_RECON_SOURCE_INTEGRITY_UNAVAILABLE")
    return source


async def open_unknown_reconciliation(
    conn, *, tenant_id: str, intent_id,
    opener_subject: str, opener_role: str,
    claimed_outcome: str, evidence_sha256: str,
) -> dict:
    """Open one immutable observation per UNKNOWN intent. No ERP or status write."""
    intent_uuid = _scope(conn, tenant_id, intent_id)
    opener = _actor(opener_subject, opener_role, "opener")
    claim = _evidence(claimed_outcome, evidence_sha256)
    source = await _source(conn, tenant_id=tenant_id, intent_uuid=intent_uuid)

    inserted = await conn.fetchrow(_q("""
        INSERT INTO posting_outbox_reconciliation_cases
          (tenant_id,outbox_id,source_id,target_system,idempotency_key,
           payload_sha256,opener_subject,opener_role,claimed_outcome,
           evidence_sha256)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (tenant_id,outbox_id) DO NOTHING
        RETURNING id
    """), tenant_id, intent_uuid, source["source_id"],
        source["target_system"], source["idempotency_key"],
        source["payload_sha256"], opener, opener_role,
        claim["claimed_outcome"], claim["evidence_sha256"])
    if inserted is None:
        _deny("FIN12_RECON_ALREADY_OPEN")
    case_id = inserted["id"]

    # Must commit atomically with case insertion, otherwise rollback.
    await conn.execute(_q("""
        INSERT INTO posting_outbox_reconciliation_events
          (tenant_id,case_id,action,actor_subject,actor_role,evidence_sha256)
        VALUES (%s,%s,'opened',%s,%s,%s)
    """), tenant_id, case_id, opener, opener_role, claim["evidence_sha256"])
    return {
        "case_id": case_id, "intent_id": str(intent_uuid), "state": "open",
        **_hold_decision("unknown"),
    }


async def review_unknown_reconciliation(
    conn, *, tenant_id: str, intent_id,
    reviewer_subject: str, reviewer_role: str,
) -> dict:
    """Independent readback ONLY: reviewed HOLD never settles provider outcome."""
    intent_uuid = _scope(conn, tenant_id, intent_id)
    reviewer = _actor(reviewer_subject, reviewer_role, "reviewer")
    source = await _source(conn, tenant_id=tenant_id, intent_uuid=intent_uuid)
    row = await conn.fetchrow(_q("""
        SELECT id,tenant_id,outbox_id,source_id,target_system,idempotency_key,
               payload_sha256,opener_subject,opener_role,claimed_outcome,
               evidence_sha256,state
          FROM posting_outbox_reconciliation_cases
         WHERE tenant_id=%s AND outbox_id=%s FOR UPDATE
    """), tenant_id, intent_uuid)
    if row is None:
        _deny("FIN12_RECON_CASE_NOT_FOUND")
    case = dict(row)
    if case["state"] != "open":
        _deny("FIN12_RECON_ALREADY_REVIEWED")
    if case["opener_subject"].casefold() == reviewer.casefold():
        _deny("FIN12_RECON_SELF_REVIEW_DENIED")
    if (case["tenant_id"] != tenant_id
            or str(case["outbox_id"]) != str(intent_uuid)
            or case["source_id"] != source["source_id"]
            or case["target_system"] != source["target_system"]
            or case["idempotency_key"] != source["idempotency_key"]
            or case["payload_sha256"] != source["payload_sha256"]):
        _deny("FIN12_RECON_SOURCE_CHANGED")
    _evidence(case["claimed_outcome"], case["evidence_sha256"])

    # Reviewer records HOLD, never 'accepted', 'rejected', or vendor success.
    await conn.execute(_q("""
        INSERT INTO posting_outbox_reconciliation_events
          (tenant_id,case_id,action,actor_subject,actor_role,evidence_sha256)
        VALUES (%s,%s,'reviewed_hold',%s,%s,%s)
    """), tenant_id, case["id"], reviewer, reviewer_role,
        case["evidence_sha256"])
    updated = await conn.fetchrow(_q("""
        UPDATE posting_outbox_reconciliation_cases
           SET state='reviewed_hold',reviewer_subject=%s,reviewer_role=%s,
               reviewed_at=NOW()
         WHERE tenant_id=%s AND id=%s AND state='open'
        RETURNING id
    """), reviewer, reviewer_role, tenant_id, case["id"])
    if updated is None:
        _deny("FIN12_RECON_CONCURRENT_REVIEW")
    return {
        "case_id": case["id"], "intent_id": str(intent_uuid),
        "state": "reviewed_hold", **_hold_decision("unknown"),
    }
