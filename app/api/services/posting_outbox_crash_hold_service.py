"""Chat196 FIN-12 — INERT crash ambiguity quarantine; NEVER dispatch or retry.

Existing in_flight/unknown intents can be marked for independent investigation.
This module is NOT connected to any router, worker or ERP API; it makes no
network calls. No lease expiration or vendor identity is inferred from created_at.
An authenticated tenant-bound caller must supply the real JWT subject/role
through a separately audited trusted boundary before any future activation.
The candidate SQL is UNAPPLIED; no real provider result is ever asserted.
"""
from __future__ import annotations

import re
from uuid import UUID

from app.api.authz import has_role_permission
from app.api.db import _q, require_current_tenant_id

_TARGETS = frozenset(("balance", "onec", "oris"))
_REASONS = frozenset(("worker_crash", "timeout", "missing_lease", "manual_investigation"))
_HASH = re.compile(r"^[0-9a-f]{64}$")


class CrashHoldUnavailable(ValueError):
    """Fail-closed recovery evidence or tenant scope is not trustworthy."""


def _deny(code: str) -> None:
    raise CrashHoldUnavailable(code)


def classify_after_crash(state) -> dict:
    """Diagnostic only; no recovery classification ever authorizes a vendor call."""
    ambiguous = isinstance(state, str) and state in ("in_flight", "unknown")
    return {
        "next_action": "MANUAL_OUTCOME_HOLD" if ambiguous else "NO_RECOVERY_AUTHORITY",
        "dispatch_allowed": False,
        "retry_allowed": False,
        "confirm_allowed": False,
        "ledger_write_allowed": False,
        "provider_verified": False,
    }


def _scope(conn, tenant_id: str, outbox_id) -> UUID:
    try:
        require_current_tenant_id(tenant_id)
    except (ValueError, TypeError):
        _deny("FIN12_CRASH_TENANT_UNAUTHORIZED")
    if conn.is_in_transaction() is not True:
        _deny("FIN12_CRASH_TRANSACTION_REQUIRED")
    if not isinstance(outbox_id, (str, UUID)):
        _deny("FIN12_CRASH_ID_INVALID")
    try:
        uid = UUID(str(outbox_id))
    except (ValueError, TypeError, AttributeError):
        _deny("FIN12_CRASH_ID_INVALID")
    if str(uid) != str(outbox_id):
        _deny("FIN12_CRASH_ID_INVALID")
    return uid


def _checked_actor(subject: str, role: str, reason: str) -> str:
    """Permission check only. JWT-to-subject binding remains an external gate."""
    if (not isinstance(subject, str) or not 1 <= len(subject) <= 200
            or subject != subject.strip()
            or subject.casefold() in {"anon", "anonymous", "human", "system", "default"}
            or any(ord(ch) <= 32 or ord(ch) == 127 for ch in subject)):
        _deny("FIN12_CRASH_AUTHENTICATED_ACTOR_REQUIRED")
    if (role not in ("accountant", "admin")
            or not has_role_permission(role, "approval:write")):
        _deny("FIN12_CRASH_ROLE_FORBIDDEN")
    if not isinstance(reason, str) or reason not in _REASONS:
        _deny("FIN12_CRASH_REASON_UNVERIFIED")
    return subject


async def record_outcome_hold(conn, *, tenant_id: str, outbox_id,
                              opener_subject: str, opener_role: str,
                              reason: str) -> dict:
    """Append a single immutable case. Does not update the outbox/ledger/ERP.

    No automatic dispatch or lease renewal. The caller must roll back the
    whole transaction on error, including any DB trigger/insert failure.
    """
    uid = _scope(conn, tenant_id, outbox_id)
    actor = _checked_actor(opener_subject, opener_role, reason)
    source_row = await conn.fetchrow(_q("""
        SELECT id,tenant_id,state,source_type,source_id,target_system,
               idempotency_key,payload_sha256,
               provider_receipt_id,provider_verified_at
          FROM posting_outbox_intents
         WHERE tenant_id=%s AND id=%s
    """), tenant_id, uid)
    if source_row is None:
        _deny("FIN12_CRASH_SOURCE_NOT_FOUND")
    src = dict(source_row)
    if src["state"] not in ("in_flight", "unknown"):
        _deny("FIN12_CRASH_SOURCE_NOT_AMBIGUOUS")
    if (src["tenant_id"] != tenant_id
            or src["source_type"] != "journal_draft"
            or not isinstance(src["source_id"], str)
            or not src["source_id"].strip()
            or src["target_system"] not in _TARGETS
            or not isinstance(src["idempotency_key"], str)
            or not _HASH.fullmatch(src["idempotency_key"])
            or not isinstance(src["payload_sha256"], str)
            or not _HASH.fullmatch(src["payload_sha256"])
            or src["provider_receipt_id"] is not None
            or src["provider_verified_at"] is not None):
        _deny("FIN12_CRASH_SOURCE_INTEGRITY_UNAVAILABLE")
    row = await conn.fetchrow(_q("""
        INSERT INTO posting_outbox_crash_holds (
            tenant_id,outbox_id,source_id,target_system,idempotency_key,
            payload_sha256,observed_state,reason,opener_subject,opener_role
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (tenant_id,outbox_id) DO NOTHING
        RETURNING id
    """), tenant_id, uid, src["source_id"], src["target_system"],
        src["idempotency_key"], src["payload_sha256"], src["state"],
        reason, actor, opener_role)
    if row is None:
        _deny("FIN12_CRASH_ALREADY_HELD")
    return {
        "hold_id": str(row["id"]),
        "intent_id": str(uid),
        "state": "manual_hold",
        **classify_after_crash(src["state"]),
    }
