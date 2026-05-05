import asyncio
import logging
import psycopg2
import psycopg2.extras
import psycopg2.errors

from app.api.db import get_db, get_conn, _q
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
from app.api.services.approval_patterns import (
    _get_pattern_value_for_draft,
    _mark_success_for_draft,
    _mark_failure_for_draft,
)

AUTOPILOT_MIN_CONFIDENCE = 0.80
AUTOPILOT_MIN_USAGE_COUNT = 5
AUTOPILOT_MIN_SUCCESS_RATE = 0.80
AUTOPILOT_MAX_PATTERN_AGE_DAYS = 45

# Confidence thresholds by transaction risk tier (amount in GEL).
# Override via tenant_settings key "approval.confidence_threshold_high" etc. in future.
CONFIDENCE_THRESHOLD_HIGH_RISK  = 0.95   # amount > HIGH_RISK_AMOUNT_GEL
CONFIDENCE_THRESHOLD_LOW_RISK   = 0.75   # amount < LOW_RISK_AMOUNT_GEL
CONFIDENCE_THRESHOLD_DEFAULT    = 0.85   # everything else
HIGH_RISK_AMOUNT_GEL            = 1000.0
LOW_RISK_AMOUNT_GEL             = 50.0

# CFO dual-approval threshold default (GEL).
# Read per-tenant from tenant_settings key "approval.cfo_threshold_gel"; fallback to this value.
CFO_APPROVAL_THRESHOLD_DEFAULT  = 10000.0


def effective_threshold(amount: float) -> float:
    """Dynamic confidence threshold based on transaction risk (amount in GEL)."""
    if amount > HIGH_RISK_AMOUNT_GEL:
        return CONFIDENCE_THRESHOLD_HIGH_RISK
    if amount < LOW_RISK_AMOUNT_GEL:
        return CONFIDENCE_THRESHOLD_LOW_RISK
    return CONFIDENCE_THRESHOLD_DEFAULT

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


async def get_queue_service(status: str, limit: int, offset: int, tenant_id: str, q: str = ""):
    search_cond = ""
    search_params: list = []
    if q:
        search_cond = " AND (counterparty_name ILIKE %s OR description ILIKE %s OR counterparty_inn ILIKE %s)"
        like = f"%{q}%"
        search_params = [like, like, like]

    try:
        async with get_conn() as conn:
            if status:
                total = await conn.fetchval(
                    _q(f"SELECT COUNT(*) FROM journal_drafts WHERE status = %s AND tenant_id = %s{search_cond}"),
                    *([status, tenant_id] + search_params),
                )
                rows = await conn.fetch(
                    _q(f"""
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
                    """),
                    *([status, tenant_id] + search_params + [limit, offset]),
                )
            else:
                total = await conn.fetchval(
                    _q(f"""SELECT COUNT(*) FROM journal_drafts
                        WHERE status IN ('drafted', 'pending_approval', 'auto_approved', 'pending_human_review')
                          AND tenant_id = %s{search_cond}"""),
                    *([tenant_id] + search_params),
                )
                rows = await conn.fetch(
                    _q(f"""
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
                    """),
                    *([tenant_id] + search_params + [limit, offset]),
                )
            items = [dict(r) for r in rows]
    except Exception as e:
        return error_response("Queue failed", "QUEUE_ERROR", str(e))

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


async def approve_draft_service(draft_id: int, tenant_id: str):
    import asyncpg

    draft = None
    updated = None
    memory_result = {"ok": False, "message": "not_run"}
    qa_result = {"ok": False, "score": 0, "issues": [], "recommendation": "unknown"}

    try:
        async with get_conn() as conn:
            tr = conn.transaction()
            await tr.start()

            try:
                draft_row = await conn.fetchrow(
                    _q("SELECT * FROM journal_drafts WHERE id = %s AND tenant_id = %s FOR UPDATE NOWAIT"),
                    draft_id, tenant_id,
                )
            except asyncpg.exceptions.LockNotAvailableError:
                await tr.rollback()
                return error_response(
                    "Draft locked", "DRAFT_LOCKED",
                    "Draft is being processed by another request. Try again in a moment.",
                )

            if not draft_row:
                await tr.rollback()
                return error_response("Not found", "NOT_FOUND",
                                      f"Draft {draft_id} not found for tenant {tenant_id}")

            draft = dict(draft_row)
            draft["confidence"] = round(float(draft.get("confidence") or 0.0), 6)
            draft["amount"] = round(float(draft.get("amount") or 0.0), 2)

            # Period lock check (is_period_locked is already async + asyncpg-compatible)
            try:
                from app.api.routes_period_lock import is_period_locked
                from datetime import date as _date
                entry_date_raw = draft.get("date")
                if entry_date_raw:
                    if isinstance(entry_date_raw, str):
                        entry_date_raw = _date.fromisoformat(str(entry_date_raw)[:10])
                    if await is_period_locked(conn, tenant_id, entry_date_raw):
                        await tr.rollback()
                        return error_response(
                            "Period is locked", "PERIOD_LOCKED",
                            f"The accounting period {entry_date_raw.strftime('%B %Y')} is locked. Unlock it first.",
                        )
            except Exception as _pl_exc:
                # Period-lock check failed unexpectedly. Log so it is visible in
                # Cloud Run logs; do NOT silently pass — at minimum the operator
                # must see this. We continue because a broken lock-check function
                # must not block all approvals, but the operator should fix it.
                log.warning(
                    "period_lock check raised an unexpected exception for draft %s "
                    "(approval proceeding — investigate period_lock service): %s",
                    draft_id, _pl_exc,
                )

            if draft["status"] == "approved":
                await tr.rollback()
                return error_response("Already approved", "ALREADY_APPROVED",
                                      f"Draft {draft_id} is already approved")

            if draft["status"] == "rejected":
                await tr.rollback()
                return error_response("Already rejected", "ALREADY_REJECTED",
                                      f"Draft {draft_id} is already rejected and cannot be approved")

            qa_result = evaluate_decision(draft)

            from app.api.services.tenant_config_service import get_tenant_setting
            DUAL_APPROVAL_THRESHOLD = float(await get_tenant_setting(
                tenant_id, "approval.cfo_threshold_gel", CFO_APPROVAL_THRESHOLD_DEFAULT
            ))
            needs_dual = draft["amount"] >= DUAL_APPROVAL_THRESHOLD

            if draft.get("status") == "awaiting_cfo":
                await tr.rollback()
                return error_response(
                    "Awaiting CFO", "AWAITING_CFO",
                    f"Draft {draft_id} requires CFO second approval (amount ≥ ₾{DUAL_APPROVAL_THRESHOLD:,.0f}). Use /approval/cfo-approve/{draft_id}.",
                )

            if needs_dual:
                updated_row = await conn.fetchrow(_q("""
                    UPDATE journal_drafts
                    SET status = 'awaiting_cfo', approved_by_mode = 'human', updated_at = NOW()
                    WHERE id = %s AND tenant_id = %s
                      AND status IN ('drafted', 'pending_approval', 'auto_approved', 'pending_human_review')
                    RETURNING *
                """), draft_id, tenant_id)
                if updated_row:
                    await tr.commit()
                    _ws_notify(tenant_id, "draft_awaiting_cfo", draft_id, "awaiting_cfo")
                    return ok_response("First approval done — awaiting CFO", {
                        "id": draft_id,
                        "status": "awaiting_cfo",
                        "message": f"Amount ₾{draft['amount']:,.2f} requires CFO approval. Use /approval/cfo-approve/{draft_id}.",
                        "dual_approval_required": True,
                    })
                else:
                    await tr.rollback()
                    return error_response("Approve blocked", "APPROVE_BLOCKED",
                                          f"Draft {draft_id} could not be approved for tenant {tenant_id}")

            updated_row = await conn.fetchrow(_q("""
                UPDATE journal_drafts
                SET status = 'approved',
                    approved_by_mode = COALESCE(approved_by_mode, 'human'),
                    updated_at = NOW()
                WHERE id = %s AND tenant_id = %s
                  AND status IN ('drafted', 'pending_approval', 'auto_approved', 'pending_human_review')
                RETURNING *
            """), draft_id, tenant_id)

            if not updated_row:
                await tr.rollback()
                return error_response("Approve blocked", "APPROVE_BLOCKED",
                                      f"Draft {draft_id} could not be approved for tenant {tenant_id}")

            updated = dict(updated_row)
            await tr.commit()

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

            # Audit log — separate psycopg2 conn so INSERT is actually committed (fixes pre-existing bug)
            try:
                _audit_conn = get_db()
                try:
                    log_entity_change(_audit_conn, "journal_drafts", draft_id,
                                      old_data=draft, new_data=updated,
                                      actor=tenant_id, tenant_id=tenant_id, action="APPROVE")
                    _audit_conn.commit()
                finally:
                    _audit_conn.close()
            except Exception as _ae:
                log.warning("audit log failed (non-fatal): %s", _ae)

    except Exception as e:
        return error_response("Approve failed", "APPROVE_ERROR", str(e))

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


async def reject_draft_service(draft_id: int, reason: str = "", tenant_id: str = "default"):
    import asyncpg

    draft = None
    updated = None

    try:
        async with get_conn() as conn:
            tr = conn.transaction()
            await tr.start()

            try:
                draft_row = await conn.fetchrow(
                    _q("SELECT * FROM journal_drafts WHERE id = %s AND tenant_id = %s FOR UPDATE NOWAIT"),
                    draft_id, tenant_id,
                )
            except asyncpg.exceptions.LockNotAvailableError:
                await tr.rollback()
                return error_response(
                    "Draft locked", "DRAFT_LOCKED",
                    "Draft is being processed by another request. Try again in a moment.",
                )

            if not draft_row:
                await tr.rollback()
                return error_response("Not found", "NOT_FOUND",
                                      f"Draft {draft_id} not found for tenant {tenant_id}")

            draft = dict(draft_row)
            draft["confidence"] = round(float(draft.get("confidence") or 0.0), 6)
            draft["amount"] = round(float(draft.get("amount") or 0.0), 2)

            if draft["status"] == "rejected":
                await tr.rollback()
                return error_response("Already rejected", "ALREADY_REJECTED",
                                      f"Draft {draft_id} is already rejected")

            if draft["status"] == "approved":
                await tr.rollback()
                return error_response("Already approved", "ALREADY_APPROVED",
                                      f"Draft {draft_id} is already approved and cannot be rejected")

            updated_row = await conn.fetchrow(_q("""
                UPDATE journal_drafts
                SET status = 'rejected', updated_at = NOW()
                WHERE id = %s AND tenant_id = %s
                  AND status IN ('drafted', 'pending_approval', 'auto_approved', 'pending_human_review')
                RETURNING *
            """), draft_id, tenant_id)

            if not updated_row:
                await tr.rollback()
                return error_response("Reject blocked", "REJECT_BLOCKED",
                                      f"Draft {draft_id} could not be rejected for tenant {tenant_id}")

            updated = dict(updated_row)
            await tr.commit()

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
                _audit_conn = get_db()
                try:
                    log_entity_change(_audit_conn, "journal_drafts", draft_id,
                                      old_data=draft, new_data=updated,
                                      actor=tenant_id, tenant_id=tenant_id, action="REJECT",
                                      details=reason or None)
                    _audit_conn.commit()
                finally:
                    _audit_conn.close()
            except Exception as _ae:
                log.warning("audit log failed (non-fatal): %s", _ae)

    except Exception as e:
        return error_response("Reject failed", "REJECT_ERROR", str(e))

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


async def get_audit_service(limit: int, offset: int, tenant_id: str):
    try:
        async with get_conn() as conn:
            events = [dict(r) for r in await conn.fetch(_q("""
                SELECT * FROM audit_events
                WHERE tenant_id = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """), tenant_id, limit, offset)]
    except Exception as e:
        return error_response("Audit failed", "AUDIT_ERROR", str(e))

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