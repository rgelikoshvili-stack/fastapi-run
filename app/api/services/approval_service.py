import asyncio
import logging
import psycopg2
import psycopg2.extras
import psycopg2.errors

from app.api.db import get_db
from app.api.response_utils import ok_response, error_response
from app.api.audit_service import log_event
from app.api.services.entity_audit_service import log_entity_change
from app.api.metrics import APPROVAL_ACTIONS, APPROVAL_DURATION

log = logging.getLogger(__name__)


def _ws_notify(tenant_id: str, event: str, draft_id: int, status: str):
    """Fire-and-forget WebSocket notification — never raises."""
    try:
        from app.api.routes_notifications_ws import manager
        from datetime import datetime
        msg = {
            "type": event,
            "draft_id": draft_id,
            "status": status,
            "tenant_id": tenant_id,
            "timestamp": datetime.utcnow().isoformat(),
        }
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(manager.send_to_tenant(tenant_id, msg))
        except RuntimeError:
            pass  # no event loop running (sync context) — notification skipped
    except Exception as e:
        log.debug("_ws_notify: %s", e)
from app.api.services.feedback_service import save_feedback
from app.api.services.transaction_memory_service import save_transaction_memory
from app.api.services.qa_engine import evaluate_decision
from app.api.engines.pattern_engine import (
    generate_patterns_from_feedback,
    mark_pattern_success,
    mark_pattern_failure,
)

AUTOPILOT_MIN_CONFIDENCE = 0.80
AUTOPILOT_MIN_USAGE_COUNT = 5
AUTOPILOT_MIN_SUCCESS_RATE = 0.80
AUTOPILOT_MAX_PATTERN_AGE_DAYS = 45


def effective_threshold(amount: float) -> float:
    """
    Dynamic confidence threshold based on transaction risk (amount).
    > 1000 GEL → stricter (0.95)
    < 50  GEL → lenient  (0.75)
    default    → 0.85
    """
    if amount > 1000:
        return 0.95
    if amount < 50:
        return 0.75
    return 0.85

PATTERN_SOURCES = {
    "pattern_active",
    "pattern_active_fuzzy",
    "pattern_candidate",
    "pattern_candidate_fuzzy",
}

SIGNAL_WEIGHTS = {
    "approve": 1.0,
    "reject": 1.5,
}


def get_queue_service(status: str, limit: int, offset: int, tenant_id: str, q: str = ""):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    search_cond = ""
    search_params: list = []
    if q:
        search_cond = " AND (counterparty_name ILIKE %s OR description ILIKE %s OR counterparty_inn ILIKE %s)"
        like = f"%{q}%"
        search_params = [like, like, like]

    try:
        if status:
            cur.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM journal_drafts
                WHERE status = %s AND tenant_id = %s{search_cond}
                """,
                [status, tenant_id] + search_params,
            )
            total = cur.fetchone()["total"]
            cur.execute(
                f"""
                SELECT id, date, partner, amount, currency, status, our_role,
                       confidence, created_at, source_document_id,
                       description, account_code, debit_account, credit_account,
                       operation_category, is_foreign_doc, counterparty_name,
                       doc_set_summary, doc_set_score, doc_matrix,
                       provider_type, completeness_alerts
                FROM journal_drafts
                WHERE status = %s AND tenant_id = %s{search_cond}
                ORDER BY created_at DESC, id DESC
                LIMIT %s OFFSET %s
                """,
                [status, tenant_id] + search_params + [limit, offset],
            )
        else:
            cur.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM journal_drafts
                WHERE status IN ('drafted', 'pending_approval', 'auto_approved', 'pending_human_review')
                  AND tenant_id = %s{search_cond}
                """,
                [tenant_id] + search_params,
            )
            total = cur.fetchone()["total"]
            cur.execute(
                f"""
                SELECT id, date, partner, amount, currency, status, our_role,
                       confidence, created_at, source_document_id,
                       description, account_code, debit_account, credit_account,
                       operation_category, is_foreign_doc, counterparty_name,
                       doc_set_summary, doc_set_score, doc_matrix,
                       provider_type, completeness_alerts
                FROM journal_drafts
                WHERE status IN ('drafted', 'pending_approval', 'auto_approved', 'pending_human_review')
                  AND tenant_id = %s{search_cond}
                ORDER BY created_at DESC, id DESC
                LIMIT %s OFFSET %s
                """,
                [tenant_id] + search_params + [limit, offset],
            )

        items = [dict(r) for r in cur.fetchall()]

    except Exception as e:
        return error_response("Queue failed", "QUEUE_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    return ok_response(
        "Approval queue",
        {
            "count": total,
            "filter": status or "drafted+pending_approval+auto_approved",
            "limit": limit,
            "offset": offset,
            "queue": items,
            "tenant_id": tenant_id,
        },
    )


def _get_pattern_value_for_draft(draft: dict):
    matched_on = draft.get("pattern_matched_on")
    if matched_on in ("description_exact", "description_fuzzy"):
        return draft.get("pattern_value_used") or draft.get("description")
    if matched_on in ("partner_exact", "partner_fuzzy"):
        return draft.get("pattern_value_used") or draft.get("partner")
    return None


def _mark_success_for_draft(draft: dict, tenant_id: str, weight: float = 1.0):
    matched_on = draft.get("pattern_matched_on")
    account_code = draft.get("account_code")
    pattern_value = _get_pattern_value_for_draft(draft)

    if not pattern_value or not account_code:
        return {"updated": 0}

    if matched_on == "description_exact":
        return mark_pattern_success(
            "description_exact", pattern_value, account_code, tenant_id=tenant_id, weight=weight
        )
    if matched_on == "partner_exact":
        return mark_pattern_success(
            "partner", pattern_value, account_code, tenant_id=tenant_id, weight=weight
        )
    if matched_on == "description_fuzzy":
        return mark_pattern_success(
            "description_exact", pattern_value, account_code, tenant_id=tenant_id, weight=weight
        )
    if matched_on == "partner_fuzzy":
        return mark_pattern_success(
            "partner", pattern_value, account_code, tenant_id=tenant_id, weight=weight
        )

    return {"updated": 0}


def _mark_failure_for_draft(draft: dict, tenant_id: str, weight: float = 1.5):
    matched_on = draft.get("pattern_matched_on")
    account_code = draft.get("account_code")
    pattern_value = _get_pattern_value_for_draft(draft)

    if not pattern_value or not account_code:
        return {"updated": 0}

    if matched_on == "description_exact":
        return mark_pattern_failure(
            "description_exact", pattern_value, account_code, tenant_id=tenant_id, weight=weight
        )
    if matched_on == "partner_exact":
        return mark_pattern_failure(
            "partner", pattern_value, account_code, tenant_id=tenant_id, weight=weight
        )
    if matched_on == "description_fuzzy":
        return mark_pattern_failure(
            "description_exact", pattern_value, account_code, tenant_id=tenant_id, weight=weight
        )
    if matched_on == "partner_fuzzy":
        return mark_pattern_failure(
            "partner", pattern_value, account_code, tenant_id=tenant_id, weight=weight
        )

    return {"updated": 0}


def approve_draft_service(draft_id: int, tenant_id: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    draft = None
    updated = None
    memory_result = {"ok": False, "message": "not_run"}
    qa_result = {"ok": False, "score": 0, "issues": [], "recommendation": "unknown"}

    try:
        try:
            cur.execute(
                """
                SELECT * FROM journal_drafts
                WHERE id = %s AND tenant_id = %s
                FOR UPDATE NOWAIT
                """,
                (draft_id, tenant_id),
            )
        except psycopg2.errors.LockNotAvailable:
            conn.rollback()
            return error_response(
                "Draft locked",
                "DRAFT_LOCKED",
                "Draft is being processed by another request. Try again in a moment.",
            )

        draft = cur.fetchone()

        if not draft:
            return error_response(
                "Not found",
                "NOT_FOUND",
                f"Draft {draft_id} not found for tenant {tenant_id}",
            )

        draft = dict(draft)
        draft["confidence"] = float(draft.get("confidence") or 0.0)
        draft["amount"] = float(draft.get("amount") or 0.0)

        # Period lock check
        try:
            from app.api.routes_period_lock import is_period_locked
            from datetime import date as _date
            entry_date_raw = draft.get("date")
            if entry_date_raw:
                if isinstance(entry_date_raw, str):
                    entry_date_raw = _date.fromisoformat(str(entry_date_raw)[:10])
                if is_period_locked(conn, tenant_id, entry_date_raw):
                    return error_response(
                        "Period is locked",
                        "PERIOD_LOCKED",
                        f"The accounting period {entry_date_raw.strftime('%B %Y')} is locked. Unlock it first.",
                    )
        except Exception:
            pass  # period_locks table may not exist yet

        if draft["status"] == "approved":
            return error_response(
                "Already approved",
                "ALREADY_APPROVED",
                f"Draft {draft_id} is already approved",
            )

        if draft["status"] == "rejected":
            return error_response(
                "Already rejected",
                "ALREADY_REJECTED",
                f"Draft {draft_id} is already rejected and cannot be approved",
            )

        qa_result = evaluate_decision(draft)

        # Dual approval: amounts above threshold require CFO second approval
        DUAL_APPROVAL_THRESHOLD = 10000.0
        needs_dual = draft["amount"] >= DUAL_APPROVAL_THRESHOLD
        # Check if already at level 1 (awaiting_cfo)
        if draft.get("status") == "awaiting_cfo":
            return error_response(
                "Awaiting CFO",
                "AWAITING_CFO",
                f"Draft {draft_id} requires CFO second approval (amount ≥ ₾{DUAL_APPROVAL_THRESHOLD:,.0f}). Use /approval/cfo-approve/{draft_id}.",
            )

        if needs_dual:
            # First approval: set to awaiting_cfo
            cur.execute("""
                UPDATE journal_drafts
                SET status = 'awaiting_cfo',
                    approved_by_mode = 'human',
                    updated_at = NOW()
                WHERE id = %s AND tenant_id = %s
                  AND status IN ('drafted', 'pending_approval', 'auto_approved', 'pending_human_review')
                RETURNING *
            """, (draft_id, tenant_id))
            updated = cur.fetchone()
            if updated:
                conn.commit()
                _ws_notify(tenant_id, "draft_awaiting_cfo", draft_id, "awaiting_cfo")
                return ok_response("First approval done — awaiting CFO", {
                    "id": draft_id,
                    "status": "awaiting_cfo",
                    "message": f"Amount ₾{draft['amount']:,.2f} requires CFO approval. Use /approval/cfo-approve/{draft_id}.",
                    "dual_approval_required": True,
                })

        cur.execute(
            """
            UPDATE journal_drafts
            SET status = 'approved',
                approved_by_mode = COALESCE(approved_by_mode, 'human'),
                updated_at = NOW()
            WHERE id = %s AND tenant_id = %s
              AND status IN ('drafted', 'pending_approval', 'auto_approved', 'pending_human_review')
            RETURNING *
            """,
            (draft_id, tenant_id),
        )
        updated = cur.fetchone()

        if not updated:
            conn.rollback()
            return error_response(
                "Approve blocked",
                "APPROVE_BLOCKED",
                f"Draft {draft_id} could not be approved for tenant {tenant_id}",
            )

        conn.commit()  # commit status change first — audit/feedback are non-fatal

        try:
            save_feedback(
                draft_id=draft.get("id"),
                tx_fingerprint=draft.get("tx_fingerprint"),
                source_type=draft.get("source_type"),
                description_raw=draft.get("description"),
                description_normalized=draft.get("normalized_description") or draft.get("description"),
                partner_raw=draft.get("partner"),
                partner_normalized=draft.get("partner"),
                amount=draft.get("amount"),
                original_account_code=draft.get("account_code"),
                original_reason=draft.get("reason"),
                original_confidence=float(draft.get("confidence") or 0.0),
                final_account_code=draft.get("account_code"),
                final_reason=draft.get("reason"),
                feedback_type="approve",
                corrected_by=None,
                notes=None,
                tenant_id=tenant_id,
            )
        except Exception as _fe:
            log.warning("save_feedback failed (non-fatal): %s", _fe)

        try:
            save_transaction_memory(
                draft.get("description"),
                draft.get("partner"),
                draft.get("amount"),
                draft.get("account_code"),
                tenant_id=tenant_id,
            )
            generate_patterns_from_feedback(tenant_id=tenant_id)
        except Exception as _me:
            log.warning("memory/patterns update failed (non-fatal): %s", _me)

        try:
            log_entity_change(conn, "journal_drafts", draft_id,
                              old_data=draft, new_data=dict(updated),
                              actor=tenant_id, tenant_id=tenant_id, action="APPROVE")
        except Exception as _ae:
            log.warning("audit log failed (non-fatal): %s", _ae)

    except Exception as e:
        conn.rollback()
        return error_response("Approve failed", "APPROVE_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    pattern_update_result = {"updated": 0}
    try:
        if draft and draft.get("classification_source") in PATTERN_SOURCES:
            pattern_update_result = _mark_success_for_draft(
                draft, tenant_id, weight=SIGNAL_WEIGHTS["approve"]
            )
    except Exception as _pe:
        log.warning("pattern success update failed (non-fatal): %s", _pe)

    log_event(
        "draft_approved",
        {
            "draft_id": draft_id,
            "tenant_id": tenant_id,
            "classification_source": draft.get("classification_source") if draft else None,
            "pattern_matched_on": draft.get("pattern_matched_on") if draft else None,
            "pattern_value_used": draft.get("pattern_value_used") if draft else None,
            "approved_by_mode": updated.get("approved_by_mode") if updated else None,
            "pattern_update_result": pattern_update_result,
            "memory_saved": bool(memory_result.get("ok")),
            "memory_result": memory_result,
            "qa_score": qa_result.get("score"),
            "qa_issues": qa_result.get("issues"),
            "qa_recommendation": qa_result.get("recommendation"),
        },
    )

    _ws_notify(tenant_id, "draft_approved", draft_id, "approved")
    APPROVAL_ACTIONS.labels(action="approve", tenant=tenant_id).inc()

    return ok_response(
        "Draft approved",
        {
            "id": draft_id,
            "status": "approved",
            "approved_by_mode": updated.get("approved_by_mode") if updated else "human",
            "tenant_id": tenant_id,
        },
    )


def reject_draft_service(draft_id: int, reason: str = "", tenant_id: str = "default"):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    draft = None
    updated = None

    try:
        try:
            cur.execute(
                """
                SELECT * FROM journal_drafts
                WHERE id = %s AND tenant_id = %s
                FOR UPDATE NOWAIT
                """,
                (draft_id, tenant_id),
            )
        except psycopg2.errors.LockNotAvailable:
            conn.rollback()
            return error_response(
                "Draft locked",
                "DRAFT_LOCKED",
                "Draft is being processed by another request. Try again in a moment.",
            )

        draft = cur.fetchone()

        if not draft:
            return error_response(
                "Not found",
                "NOT_FOUND",
                f"Draft {draft_id} not found for tenant {tenant_id}",
            )

        draft = dict(draft)
        draft["confidence"] = float(draft.get("confidence") or 0.0)
        draft["amount"] = float(draft.get("amount") or 0.0)

        if draft["status"] == "rejected":
            return error_response(
                "Already rejected",
                "ALREADY_REJECTED",
                f"Draft {draft_id} is already rejected",
            )

        if draft["status"] == "approved":
            return error_response(
                "Already approved",
                "ALREADY_APPROVED",
                f"Draft {draft_id} is already approved and cannot be rejected",
            )

        cur.execute(
            """
            UPDATE journal_drafts
            SET status = 'rejected', updated_at = NOW()
            WHERE id = %s AND tenant_id = %s
              AND status IN ('drafted', 'pending_approval', 'auto_approved', 'pending_human_review')
            RETURNING *
            """,
            (draft_id, tenant_id),
        )
        updated = cur.fetchone()

        if not updated:
            conn.rollback()
            return error_response(
                "Reject blocked",
                "REJECT_BLOCKED",
                f"Draft {draft_id} could not be rejected for tenant {tenant_id}",
            )

        conn.commit()  # commit status change first — audit/feedback are non-fatal

        try:
            save_feedback(
                draft_id=draft.get("id"),
                tx_fingerprint=draft.get("tx_fingerprint"),
                source_type=draft.get("source_type"),
                description_raw=draft.get("description"),
                description_normalized=draft.get("normalized_description") or draft.get("description"),
                partner_raw=draft.get("partner"),
                partner_normalized=draft.get("partner"),
                amount=draft.get("amount"),
                original_account_code=draft.get("account_code"),
                original_reason=draft.get("reason"),
                original_confidence=float(draft.get("confidence") or 0.0),
                final_account_code=None,
                final_reason=None,
                feedback_type="reject",
                corrected_by=None,
                notes=reason,
                tenant_id=tenant_id,
            )
        except Exception as _fe:
            log.warning("save_feedback failed (non-fatal): %s", _fe)

        try:
            log_entity_change(conn, "journal_drafts", draft_id,
                              old_data=draft, new_data=dict(updated),
                              actor=tenant_id, tenant_id=tenant_id, action="REJECT",
                              details=reason or None)
        except Exception as _ae:
            log.warning("audit log failed (non-fatal): %s", _ae)

    except Exception as e:
        conn.rollback()
        return error_response("Reject failed", "REJECT_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    pattern_update_result = {"updated": 0}
    try:
        if draft and draft.get("classification_source") in PATTERN_SOURCES:
            pattern_update_result = _mark_failure_for_draft(
                draft, tenant_id, weight=SIGNAL_WEIGHTS["reject"]
            )
    except Exception as _pe:
        log.warning("pattern failure update failed (non-fatal): %s", _pe)

    log_event(
        "draft_rejected",
        {
            "draft_id": draft_id,
            "tenant_id": tenant_id,
            "reason": reason,
            "classification_source": draft.get("classification_source") if draft else None,
            "pattern_matched_on": draft.get("pattern_matched_on") if draft else None,
            "pattern_value_used": draft.get("pattern_value_used") if draft else None,
            "pattern_update_result": pattern_update_result,
        },
    )

    _ws_notify(tenant_id, "draft_rejected", draft_id, "rejected")
    APPROVAL_ACTIONS.labels(action="reject", tenant=tenant_id).inc()

    return ok_response(
        "Draft rejected",
        {"id": draft_id, "status": "rejected", "reason": reason, "tenant_id": tenant_id},
    )


def get_audit_service(limit: int, offset: int, tenant_id: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            """
            SELECT * FROM audit_events
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (tenant_id, limit, offset),
        )
        events = [dict(r) for r in cur.fetchall()]

    except Exception as e:
        return error_response("Audit failed", "AUDIT_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    return ok_response(
        "Audit log",
        {"count": len(events), "events": events, "tenant_id": tenant_id},
    )


def autopilot_approve_service(
    tenant_id: str, confidence_threshold: float = AUTOPILOT_MIN_CONFIDENCE
):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            """
            SELECT
                jd.id,
                jd.confidence,
                jd.description,
                jd.amount,
                jd.account_code,
                jd.tenant_id,
                jd.classification_source,
                jd.pattern_matched_on,
                jd.pattern_value_used,
                lp.success_count,
                lp.failure_count,
                lp.usage_count,
                lp.last_used_at
            FROM journal_drafts jd
            LEFT JOIN learning_patterns lp
                ON lp.tenant_id = jd.tenant_id
                AND lp.account_code = jd.account_code
                AND lp.status = 'active'
            WHERE jd.status IN ('drafted', 'pending_approval')
              AND jd.tenant_id = %s
              AND jd.confidence >= %s
              AND (jd.review_required = false OR jd.confidence >= 0.85)
            ORDER BY jd.confidence DESC
            """,
            (tenant_id, confidence_threshold),
        )
        raw_candidates = [dict(r) for r in cur.fetchall()]

    except Exception as e:
        return error_response("Autopilot query failed", "AUTOPILOT_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    candidates = []
    skipped = []

    for draft in raw_candidates:
        confidence = float(draft.get("confidence") or 0.0)
        amount = float(draft.get("amount") or 0.0)
        success_count = int(draft.get("success_count") or 0)
        failure_count = int(draft.get("failure_count") or 0)
        usage_count = int(draft.get("usage_count") or 0)
        total = success_count + failure_count
        success_rate = (success_count / total) if total > 0 else 0.0

        # Use dynamic threshold per-draft (additive — honours caller's override too)
        draft_threshold = max(confidence_threshold, effective_threshold(amount))

        skip_reason = None

        if draft.get("classification_source") == "rules":
            skip_reason = "rules_path_not_eligible"
        elif usage_count < AUTOPILOT_MIN_USAGE_COUNT and draft.get("classification_source") not in (
            "expense_article",
            "partner_memory",
            "erp_history",
        ):
            skip_reason = f"usage_count_too_low:{usage_count}"
        elif total > 0 and success_rate < AUTOPILOT_MIN_SUCCESS_RATE:
            skip_reason = f"success_rate_too_low:{round(success_rate, 2)}"
        elif failure_count > 0 and draft.get("classification_source") in (
            "pattern_active",
            "pattern_candidate",
            "pattern_active_fuzzy",
            "pattern_candidate_fuzzy",
        ):
            skip_reason = f"has_failures:{failure_count}"
        elif confidence < draft_threshold:
            skip_reason = f"below_threshold:{confidence:.3f}<{draft_threshold:.2f}"

        if skip_reason:
            skipped.append({"id": draft["id"], "reason": skip_reason})
        else:
            candidates.append(draft)

    if not candidates:
        return ok_response(
            "Autopilot: nothing to approve",
            {
                "approved": 0,
                "items": [],
                "skipped": skipped,
                "tenant_id": tenant_id,
            },
        )

    approved_ids = []
    failed_ids = []

    for draft in candidates:
        draft_id = draft["id"]
        conn2 = get_db()
        cur2 = conn2.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            cur2.execute(
                """
                UPDATE journal_drafts
                SET status = 'auto_approved',
                    approved_by_mode = 'autopilot',
                    updated_at = NOW()
                WHERE id = %s AND tenant_id = %s
                  AND status IN ('drafted', 'pending_approval')
                RETURNING id
                """,
                (draft_id, tenant_id),
            )
            updated = cur2.fetchone()
            conn2.commit()

            if updated:
                approved_ids.append(draft_id)
                log_event(
                    "draft_auto_approved",
                    {
                        "draft_id": draft_id,
                        "tenant_id": tenant_id,
                        "confidence": float(draft.get("confidence") or 0.0),
                        "threshold": confidence_threshold,
                        "account_code": draft.get("account_code"),
                        "usage_count": draft.get("usage_count"),
                        "success_count": draft.get("success_count"),
                        "failure_count": draft.get("failure_count"),
                        "classification_source": draft.get("classification_source"),
                    },
                )
            else:
                failed_ids.append(draft_id)

        except Exception:
            conn2.rollback()
            failed_ids.append(draft_id)
        finally:
            cur2.close()
            conn2.close()

    return ok_response(
        "Autopilot complete",
        {
            "approved": len(approved_ids),
            "failed": len(failed_ids),
            "skipped": len(skipped),
            "skipped_details": skipped,
            "threshold": confidence_threshold,
            "approved_ids": approved_ids,
            "failed_ids": failed_ids,
            "tenant_id": tenant_id,
        },
    )


def autopilot_suggest_service(tenant_id: str):
    """
    Suggest-only autopilot: identifies approval candidates WITHOUT changing any DB status.
    Returns drafts flagged autopilot_suggested=True / autopilot_flag='ready_for_approval'.
    UI shows these as 'Ready' — human still clicks Approve.
    Never sets status = approved / auto_approved.
    """
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """
            SELECT jd.id, jd.confidence, jd.description, jd.account_code,
                   jd.amount, jd.status, jd.classification_source,
                   jd.pattern_matched_on, jd.pattern_value_used,
                   lp.success_count, lp.failure_count, lp.usage_count
            FROM journal_drafts jd
            LEFT JOIN learning_patterns lp
                ON lp.tenant_id = jd.tenant_id
               AND lp.account_code = jd.account_code
               AND lp.status = 'active'
            WHERE jd.status IN ('drafted', 'pending_approval')
              AND jd.tenant_id = %s
            ORDER BY jd.confidence DESC
            LIMIT 50
            """,
            (tenant_id,),
        )
        drafts = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        return error_response("Autopilot suggest failed", "SUGGEST_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    suggestions = []
    for draft in drafts:
        amount = float(draft.get("amount") or 0)
        confidence = float(draft.get("confidence") or 0)
        threshold = effective_threshold(amount)
        usage_count = int(draft.get("usage_count") or 0)
        success_count = int(draft.get("success_count") or 0)
        failure_count = int(draft.get("failure_count") or 0)
        total = success_count + failure_count
        success_rate = (success_count / total) if total > 0 else 0.0

        eligible = (
            confidence >= threshold
            and draft.get("classification_source") != "rules"
            and failure_count == 0
            and (
                usage_count >= AUTOPILOT_MIN_USAGE_COUNT
                or draft.get("classification_source") in ("expense_article", "partner_memory", "erp_history")
            )
            and (total == 0 or success_rate >= AUTOPILOT_MIN_SUCCESS_RATE)
        )

        if eligible:
            suggestions.append({
                "id": draft["id"],
                "description": draft.get("description"),
                "account_code": draft.get("account_code"),
                "amount": amount,
                "confidence": confidence,
                "status": draft.get("status"),
                "classification_source": draft.get("classification_source"),
                "autopilot_suggested": True,
                "autopilot_flag": "ready_for_approval",
                "effective_threshold": threshold,
            })

    return ok_response(
        "Autopilot suggestions (suggest-only)",
        {
            "count": len(suggestions),
            "suggestions": suggestions,
            "tenant_id": tenant_id,
            "note": "No status changes made. Human approval required.",
        },
    )