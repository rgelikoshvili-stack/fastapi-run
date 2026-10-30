"""FIN-11 independent correction-review evidence — INERT Draft-only service.

No API router or worker imports this service. The candidate SQL is unapplied.
The calling boundary MUST supply verified JWT subject, role and tenant context,
plus a transaction-scoped DB connection; these strings must never be accepted
from a public payload or AI tool. A review decision is durable evidence only:
it does NOT set journal_drafts.status='approved' and cannot trigger ERP posting.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.api.authz import has_role_permission
from app.api.db import _q, require_current_tenant_id
from app.api.services.period_transaction_gate import acquire_posting_gate
from app.api.services.period_lock_service import assert_period_open
from app.api.services.posting_helpers import _normalize_lines, _validate_lines
from app.api.services.reversal_service import lines_balanced


class CorrectionReviewUnavailable(ValueError):
    """Fail-closed missing identity, immutable source, or review evidence."""


def _deny(code: str):
    raise CorrectionReviewUnavailable(code)


def _checked_actor(subject: str, role: str, phase: str) -> str:
    """Role validation is necessary but not a substitute for JWT authentication."""
    if (not isinstance(subject, str) or not subject or subject != subject.strip()
            or len(subject) > 200 or any(ord(ch) < 33 or ord(ch) == 127 for ch in subject)
            or subject.casefold() in {"system", "anon", "anonymous", "human", "default"}):
        _deny("FIN11_REVIEW_VERIFIED_ACTOR_REQUIRED")
    if phase == "maker":
        allowed = {"accountant", "admin"}
        permission = "approval:write"
    elif phase == "checker":
        allowed = {"cfo", "admin"}
        permission = "approval:cfo"
    else:
        _deny("FIN11_REVIEW_INVALID_PHASE")
    if role not in allowed or not has_role_permission(role, permission):
        _deny("FIN11_REVIEW_ROLE_FORBIDDEN")
    return subject


def _require_independent_checker(maker_subject: str, checker_subject: str) -> None:
    if maker_subject.casefold() == checker_subject.casefold():
        _deny("FIN11_SELF_APPROVAL_DENIED")


def _scope(conn, tenant_id: str, draft_id: int) -> None:
    try:
        require_current_tenant_id(tenant_id)
    except ValueError:
        _deny("FIN11_REVIEW_TENANT_UNAUTHORIZED")
    if type(draft_id) is not int or not 1 <= draft_id <= 9223372036854775807:
        _deny("FIN11_REVIEW_INVALID_DRAFT_ID")
    if conn.is_in_transaction() is not True:
        _deny("FIN11_REVIEW_TRANSACTION_REQUIRED")


def correction_fingerprint(row) -> str:
    """Stable SHA-256 of financially material draft fields; not an approval."""
    d = dict(row)
    if not isinstance(d.get("date"), date) or isinstance(d["date"], datetime):
        _deny("FIN11_REVIEW_INVALID_DATE")
    try:
        amount = Decimal(str(d["amount"]))
        if not amount.is_finite():
            _deny("FIN11_REVIEW_INVALID_AMOUNT")
    except (KeyError, TypeError, InvalidOperation):
        _deny("FIN11_REVIEW_INVALID_AMOUNT")
    lines = d.get("lines_json")
    try:
        if isinstance(lines, str):
            lines = json.loads(lines)
        elif isinstance(lines, memoryview):
            lines = json.loads(lines.tobytes())
        if not isinstance(lines, list):
            _deny("FIN11_REVIEW_INVALID_LINES")
        canonical = json.dumps(
            {
                "draft_id": d["id"],
                "tenant_id": d["tenant_id"],
                "date": d["date"].isoformat(),
                "entry_type": d["entry_type"],
                "source_id": d["reversal_of_draft_id"],
                "reason": d["reversal_reason"],
                "amount": format(amount, "f"),
                "currency": d["currency"],
                "lines": lines,
            },
            sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
            default=lambda obj: str(obj) if isinstance(obj, Decimal) else None,
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        _deny("FIN11_REVIEW_FINGERPRINT_UNAVAILABLE")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _verified_correction(conn, tenant_id: str, draft_id: int) -> dict:
    draft_row = await conn.fetchrow(_q("""
        SELECT id,tenant_id,date,entry_type,reversal_of_draft_id,
               reversal_reason,status,currency,amount,lines_json
        FROM journal_drafts WHERE tenant_id=%s AND id=%s FOR UPDATE
    """), tenant_id, draft_id)
    if draft_row is None:
        _deny("FIN11_REVIEW_DRAFT_NOT_FOUND")
    draft = dict(draft_row)
    if (draft["entry_type"] not in ("reversal", "adjustment")
            or draft["status"] != "pending_approval"
            or type(draft["reversal_of_draft_id"]) is not int
            or draft["reversal_of_draft_id"] <= 0
            or not isinstance(draft["reversal_reason"], str)
            or not draft["reversal_reason"].strip()):
        _deny("FIN11_REVIEW_SOURCE_OR_STATUS_INVALID")

    source = await conn.fetchrow(_q("""
        SELECT id,status,entry_type,reversal_of_draft_id
        FROM journal_drafts WHERE tenant_id=%s AND id=%s
    """), tenant_id, draft["reversal_of_draft_id"])
    if (not source or source["status"] != "posted"
            or source["entry_type"] not in ("normal", "standard")
            or source["reversal_of_draft_id"] is not None):
        _deny("FIN11_REVIEW_SOURCE_NOT_POSTED")

    try:
        normalized = _normalize_lines(draft["lines_json"])
        if not normalized or _validate_lines(normalized) or not lines_balanced(normalized):
            _deny("FIN11_REVIEW_INVALID_LINES")
    except (TypeError, ValueError, KeyError, InvalidOperation):
        _deny("FIN11_REVIEW_INVALID_LINES")
    fingerprint = correction_fingerprint(draft)

    # Review must serialize with month/year close and check storage in this txn.
    await acquire_posting_gate(conn, tenant_id, draft["date"])
    await assert_period_open(conn, tenant_id, draft["date"], "correction_review")
    return {**draft, "fingerprint": fingerprint}


async def _audit(conn, *, tenant_id: str, draft_id: int, subject: str,
                 role: str, action: str, details: dict) -> None:
    """Mandatory audit_log write in the same transaction, no best-effort retry."""
    await conn.execute(_q("""
        INSERT INTO audit_log
            (actor,role,action,resource,resource_id,
             old_value,new_value,status,details,tenant_id)
        VALUES (%s,%s,%s,'journal_drafts',%s,
                NULL,%s::jsonb,'success',%s,%s)
    """), subject, role, action, str(draft_id),
        json.dumps(details, sort_keys=True, ensure_ascii=False), 
        "FIN11 correction review evidence only; no posting", tenant_id)


async def _require_original_maker(conn, tenant_id: str, draft: dict,
                                  maker_subject: str) -> None:
    """Bind the claimed maker to the single transactionally created source audit.

    This proves linkage to recorded creation actor, not that Production audit
    roles are append-only. Enabling any public path needs signed JWT actor
    mapping and read-only audit grants independently reviewed.
    """
    action = ("reversal_draft_created" if draft["entry_type"] == "reversal"
              else "adjustment_draft_created")
    events = await conn.fetch(_q("""
        SELECT actor,new_value FROM audit_log
         WHERE tenant_id=%s AND resource='journal_drafts' AND resource_id=%s
           AND action=%s AND status='success'
         ORDER BY id LIMIT 2
    """), tenant_id, str(draft["id"]), action)
    if len(events) != 1:
        _deny("FIN11_REVIEW_CREATOR_EVIDENCE_UNAVAILABLE")
    event = dict(events[0])
    try:
        evidence = event["new_value"]
        if isinstance(evidence, str):
            evidence = json.loads(evidence)
        source_id = evidence["source_id"]
        state = evidence["status"]
    except (TypeError, ValueError, KeyError):
        _deny("FIN11_REVIEW_CREATOR_EVIDENCE_UNAVAILABLE")
    if (event["actor"] != maker_subject
            or source_id != draft["reversal_of_draft_id"]
            or state != "pending_approval"):
        _deny("FIN11_REVIEW_MAKER_NOT_CREATOR")


async def submit_correction_review(conn, *, tenant_id: str, draft_id: int,
                                   maker_subject: str, maker_role: str) -> dict:
    """Submit reviewer evidence on an existing correction draft; no status change.

    The caller must COMMIT/ROLLBACK the surrounding transaction. Failure of
    either event/audit INSERT rolls back the review only if caller honors this.
    """
    _scope(conn, tenant_id, draft_id)
    maker = _checked_actor(maker_subject, maker_role, "maker")
    draft = await _verified_correction(conn, tenant_id, draft_id)
    await _require_original_maker(conn, tenant_id, draft, maker)
    row = await conn.fetchrow(_q("""
        INSERT INTO correction_review_intents
            (tenant_id,draft_id,source_id,entry_type,maker_subject,maker_role,
             source_fingerprint)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (tenant_id,draft_id) DO NOTHING
        RETURNING id
    """), tenant_id, draft_id, draft["reversal_of_draft_id"], draft["entry_type"],
        maker, maker_role, draft["fingerprint"])
    if row is None:
        _deny("FIN11_REVIEW_ALREADY_EXISTS")
    review_id = row["id"]
    await conn.execute(_q("""
        INSERT INTO correction_review_events
          (review_id,tenant_id,action,actor_subject,actor_role,source_fingerprint)
        VALUES (%s,%s,'submitted',%s,%s,%s)
    """), review_id, tenant_id, maker, maker_role, draft["fingerprint"])
    await _audit(conn, tenant_id=tenant_id, draft_id=draft_id,
                 subject=maker, role=maker_role, action="correction_review_submitted",
                 details={"review_id": review_id, "state": "awaiting_checker",
                          "fingerprint": draft["fingerprint"]})
    return {"review_id": review_id, "draft_id": draft_id,
            "state": "awaiting_checker", "posted": False}


async def decide_correction_review(conn, *, tenant_id: str, draft_id: int,
                                   checker_subject: str, checker_role: str,
                                   decision: str, reason: str = "") -> dict:
    """Independent checker decision; journal remains pending_approval and HOLD.

    No ERP posting, generic approval status change, or provider dispatch.
    """
    _scope(conn, tenant_id, draft_id)
    checker = _checked_actor(checker_subject, checker_role, "checker")
    if decision not in ("approved", "rejected"):
        _deny("FIN11_REVIEW_INVALID_DECISION")
    if not isinstance(reason, str) or len(reason) > 2048 or (decision == "rejected" and not reason.strip()):
        _deny("FIN11_REVIEW_REASON_REQUIRED")

    draft = await _verified_correction(conn, tenant_id, draft_id)
    row = await conn.fetchrow(_q("""
        SELECT id,maker_subject,maker_role,source_fingerprint,state,source_id,entry_type
          FROM correction_review_intents
         WHERE tenant_id=%s AND draft_id=%s FOR UPDATE
    """), tenant_id, draft_id)
    if row is None or row["state"] != "awaiting_checker":
        _deny("FIN11_REVIEW_NOT_AWAITING_CHECKER")
    _require_independent_checker(row["maker_subject"], checker)
    if (row["source_fingerprint"] != draft["fingerprint"]
            or row["entry_type"] != draft["entry_type"]
            or row["source_id"] != draft["reversal_of_draft_id"]):
        _deny("FIN11_REVIEW_SOURCE_CHANGED")

    await conn.execute(_q("""
        INSERT INTO correction_review_events
          (review_id,tenant_id,action,actor_subject,actor_role,
           source_fingerprint,reason)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
    """), row["id"], tenant_id, decision, checker, checker_role,
        draft["fingerprint"], reason.strip() or None)
    result = await conn.fetchrow(_q("""
        UPDATE correction_review_intents
           SET state=%s,checker_subject=%s,checker_role=%s,
               decision_reason=%s,decided_at=NOW()
         WHERE id=%s AND tenant_id=%s AND state='awaiting_checker'
        RETURNING id,state
    """), decision, checker, checker_role, reason.strip() or None,
        row["id"], tenant_id)
    if result is None:
        _deny("FIN11_REVIEW_CONCURRENT_DECISION")
    await _audit(conn, tenant_id=tenant_id, draft_id=draft_id,
                 subject=checker, role=checker_role, action="correction_review_"+decision,
                 details={"review_id": row["id"], "state": decision,
                          "fingerprint": draft["fingerprint"],
                          "maker_subject": row["maker_subject"]})
    return {"review_id": row["id"], "draft_id": draft_id, "state": decision,
            "posted": False, "journal_status": "pending_approval"}
