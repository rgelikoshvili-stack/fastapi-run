import psycopg2.extras

from app.api.db import get_db
from app.api.response_utils import ok_response, error_response
from app.api.audit_service import log_event
from app.api.services.feedback_service import save_feedback
from app.api.services.transaction_memory_service import save_transaction_memory
from app.api.engines.pattern_engine import (
    generate_patterns_from_feedback,
    mark_pattern_success,
    mark_pattern_failure,
)


def get_queue_service(status: str, limit: int, offset: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        if status:
            cur.execute(
                "SELECT COUNT(*) AS total FROM journal_drafts WHERE status = %s",
                (status,),
            )
            total = cur.fetchone()["total"]

            cur.execute(
                """
                SELECT *
                FROM journal_drafts
                WHERE status = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s OFFSET %s
                """,
                (status, limit, offset),
            )
        else:
            cur.execute(
                """
                SELECT COUNT(*) AS total
                FROM journal_drafts
                WHERE status IN ('drafted', 'pending_approval', 'auto_approved')
                """
            )
            total = cur.fetchone()["total"]

            cur.execute(
                """
                SELECT *
                FROM journal_drafts
                WHERE status IN ('drafted', 'pending_approval', 'auto_approved')
                ORDER BY created_at DESC, id DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
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
        },
    )


def _get_pattern_value_for_draft(draft: dict):
    matched_on = draft.get("pattern_matched_on")

    if matched_on in ("description_exact", "description_fuzzy"):
        return draft.get("pattern_value_used") or draft.get("description")

    if matched_on in ("partner_exact", "partner_fuzzy"):
        return draft.get("pattern_value_used") or draft.get("partner")

    return None


def _mark_success_for_draft(draft: dict):
    matched_on = draft.get("pattern_matched_on")
    account_code = draft.get("account_code")
    pattern_value = _get_pattern_value_for_draft(draft)

    if not pattern_value:
        return {"updated": 0}

    if matched_on == "description_exact":
        return mark_pattern_success("description_exact", pattern_value, account_code)
    if matched_on == "partner_exact":
        return mark_pattern_success("partner", pattern_value, account_code)
    if matched_on == "description_fuzzy":
        return mark_pattern_success("description_exact", pattern_value, account_code)
    if matched_on == "partner_fuzzy":
        return mark_pattern_success("partner", pattern_value, account_code)

    return {"updated": 0}


def _mark_failure_for_draft(draft: dict):
    matched_on = draft.get("pattern_matched_on")
    account_code = draft.get("account_code")
    pattern_value = _get_pattern_value_for_draft(draft)

    if not pattern_value:
        return {"updated": 0}

    if matched_on == "description_exact":
        return mark_pattern_failure("description_exact", pattern_value, account_code)
    if matched_on == "partner_exact":
        return mark_pattern_failure("partner", pattern_value, account_code)
    if matched_on == "description_fuzzy":
        return mark_pattern_failure("description_exact", pattern_value, account_code)
    if matched_on == "partner_fuzzy":
        return mark_pattern_failure("partner", pattern_value, account_code)

    return {"updated": 0}


def approve_draft_service(draft_id: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("SELECT * FROM journal_drafts WHERE id = %s", (draft_id,))
        draft = cur.fetchone()

        if not draft:
            return error_response(
                "Not found",
                "NOT_FOUND",
                f"Draft {draft_id} not found",
            )

        current_status = draft["status"]

        if current_status == "approved":
            return error_response(
                "Already approved",
                "ALREADY_APPROVED",
                f"Draft {draft_id} is already approved",
            )

        if current_status == "rejected":
            return error_response(
                "Already rejected",
                "ALREADY_REJECTED",
                f"Draft {draft_id} is already rejected and cannot be approved",
            )

        cur.execute(
            """
            UPDATE journal_drafts
            SET
                status = 'approved',
                approved_by_mode = COALESCE(approved_by_mode, 'human'),
                updated_at = NOW()
            WHERE id = %s
              AND status IN ('drafted', 'pending_approval', 'auto_approved')
            RETURNING *
            """,
            (draft_id,),
        )
        updated = cur.fetchone()

        if not updated:
            conn.rollback()
            return error_response(
                "Approve blocked",
                "APPROVE_BLOCKED",
                f"Draft {draft_id} could not be approved",
            )

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
            original_confidence=draft.get("confidence"),
            final_account_code=draft.get("account_code"),
            final_reason=draft.get("reason"),
            feedback_type="approve",
            corrected_by=None,
            notes=None,
        )

        memory_result = save_transaction_memory(
            draft.get("description"),
            draft.get("partner"),
            draft.get("amount"),
            draft.get("account_code"),
        )

        generate_patterns_from_feedback()
        conn.commit()

    except Exception as e:
        conn.rollback()
        return error_response("Approve failed", "APPROVE_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    pattern_update_result = {"updated": 0}
    if draft.get("classification_source") in (
        "pattern_active",
        "pattern_active_fuzzy",
        "pattern_candidate",
        "pattern_candidate_fuzzy",
    ):
        pattern_update_result = _mark_success_for_draft(draft)

    log_event(
        "draft_approved",
        {
            "draft_id": draft_id,
            "classification_source": draft.get("classification_source"),
            "pattern_matched_on": draft.get("pattern_matched_on"),
            "pattern_value_used": draft.get("pattern_value_used"),
            "approved_by_mode": updated.get("approved_by_mode"),
            "pattern_update_result": pattern_update_result,
            "memory_saved": bool(memory_result.get("ok")),
            "memory_result": memory_result,
            "bridge_from_erp_history": draft.get("classification_source") == "erp_history",
        },
    )

    return ok_response(
        "Draft approved",
        {
            "id": draft_id,
            "status": "approved",
            "approved_by_mode": updated.get("approved_by_mode"),
        },
    )


def reject_draft_service(draft_id: int, reason: str = ""):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("SELECT * FROM journal_drafts WHERE id = %s", (draft_id,))
        draft = cur.fetchone()

        if not draft:
            return error_response(
                "Not found",
                "NOT_FOUND",
                f"Draft {draft_id} not found",
            )

        current_status = draft["status"]

        if current_status == "rejected":
            return error_response(
                "Already rejected",
                "ALREADY_REJECTED",
                f"Draft {draft_id} is already rejected",
            )

        if current_status == "approved":
            return error_response(
                "Already approved",
                "ALREADY_APPROVED",
                f"Draft {draft_id} is already approved and cannot be rejected",
            )

        cur.execute(
            """
            UPDATE journal_drafts
            SET
                status = 'rejected',
                updated_at = NOW()
            WHERE id = %s
              AND status IN ('drafted', 'pending_approval', 'auto_approved')
            RETURNING *
            """,
            (draft_id,),
        )
        updated = cur.fetchone()

        if not updated:
            conn.rollback()
            return error_response(
                "Reject blocked",
                "REJECT_BLOCKED",
                f"Draft {draft_id} could not be rejected",
            )

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
            original_confidence=draft.get("confidence"),
            final_account_code=None,
            final_reason=None,
            feedback_type="reject",
            corrected_by=None,
            notes=reason,
        )

        conn.commit()

    except Exception as e:
        conn.rollback()
        return error_response("Reject failed", "REJECT_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    pattern_update_result = {"updated": 0}
    if draft.get("classification_source") in (
        "pattern_active",
        "pattern_active_fuzzy",
        "pattern_candidate",
        "pattern_candidate_fuzzy",
    ):
        pattern_update_result = _mark_failure_for_draft(draft)

    log_event(
        "draft_rejected",
        {
            "draft_id": draft_id,
            "reason": reason,
            "classification_source": draft.get("classification_source"),
            "pattern_matched_on": draft.get("pattern_matched_on"),
            "pattern_value_used": draft.get("pattern_value_used"),
            "pattern_update_result": pattern_update_result,
        },
    )

    return ok_response(
        "Draft rejected",
        {"id": draft_id, "status": "rejected", "reason": reason},
    )


def get_audit_service(limit: int, offset: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            """
            SELECT *
            FROM audit_events
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        events = [dict(r) for r in cur.fetchall()]

    except Exception as e:
        return error_response("Audit failed", "AUDIT_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    return ok_response(
        "Audit log",
        {
            "count": len(events),
            "events": events,
        },
    )
def autopilot_approve_service(confidence_threshold: float = 0.80):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            """
            SELECT id, confidence, description, account_code
            FROM journal_drafts
            WHERE status IN ('drafted', 'pending_approval')
  AND confidence >= %s
  AND (review_required = false OR confidence >= 0.85)
            ORDER BY confidence DESC
            """,
            (confidence_threshold,),
        )
        candidates = [dict(r) for r in cur.fetchall()]

    except Exception as e:
        return error_response("Autopilot query failed", "AUTOPILOT_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    if not candidates:
        return ok_response("Autopilot: nothing to approve", {"approved": 0, "items": []})

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
                WHERE id = %s
                  AND status IN ('drafted', 'pending_approval')
                RETURNING id
                """,
                (draft_id,),
            )
            updated = cur2.fetchone()
            conn2.commit()

            if updated:
                approved_ids.append(draft_id)

                log_event("draft_auto_approved", {
                    "draft_id": draft_id,
                    "confidence": draft.get("confidence"),
                    "threshold": confidence_threshold,
                    "account_code": draft.get("account_code"),
                })
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
            "threshold": confidence_threshold,
            "approved_ids": approved_ids,
            "failed_ids": failed_ids,
        },
    )