import psycopg2.extras

from app.api.db import get_db
from app.api.response_utils import ok_response, error_response
from app.api.audit_service import log_event
from app.api.services.feedback_service import save_feedback


PROMOTION_SUPPORT_THRESHOLD = 3
PROMOTION_SUCCESS_THRESHOLD = 3
DEMOTION_FAILURE_THRESHOLD = 2


def _decide_pattern_status(support_count: int, success_count: int, failure_count: int) -> str:
    if failure_count >= DEMOTION_FAILURE_THRESHOLD:
        return "inactive"

    if (
        support_count >= PROMOTION_SUPPORT_THRESHOLD
        and success_count >= PROMOTION_SUCCESS_THRESHOLD
        and failure_count == 0
    ):
        return "active"

    return "candidate"


def _normalize_pattern_value(value: str | None, lowercase: bool = False) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    return cleaned.lower() if lowercase else cleaned


def _update_pattern_feedback(cur, pattern_type: str, pattern_value: str | None, action: str):
    if not pattern_value:
        return

    cur.execute(
        """
        SELECT id, support_count, success_count, failure_count
        FROM learning_patterns
        WHERE pattern_type = %s
          AND pattern_value = %s
        LIMIT 1
        """,
        (pattern_type, pattern_value),
    )
    row = cur.fetchone()
    if not row:
        return

    pattern_id = row["id"]
    support_count = int(row.get("support_count") or 0)
    success_count = int(row.get("success_count") or 0)
    failure_count = int(row.get("failure_count") or 0)

    if action == "approve":
        success_count += 1
    elif action == "reject":
        failure_count += 1
    else:
        return

    new_status = _decide_pattern_status(support_count, success_count, failure_count)

    cur.execute(
        """
        UPDATE learning_patterns
        SET success_count = %s,
            failure_count = %s,
            status = %s,
            last_seen_at = NOW(),
            updated_at = NOW()
        WHERE id = %s
        """,
        (success_count, failure_count, new_status, pattern_id),
    )


def _update_patterns_for_draft_feedback(cur, draft: dict, action: str):
    matched_on = (draft.get("pattern_matched_on") or "").strip()

    description_value = _normalize_pattern_value(draft.get("description"), lowercase=True)
    partner_value = _normalize_pattern_value(draft.get("partner"), lowercase=False)

    if matched_on in ("description_exact", "description_fuzzy"):
        _update_pattern_feedback(cur, "description_exact", description_value, action)

    elif matched_on in ("partner_exact", "partner_fuzzy", "partner"):
        _update_pattern_feedback(cur, "partner", partner_value, action)

    else:
        # fallback: თუ pattern_matched_on არაა, მაგრამ classification_source pattern-based იყო,
        # მაინც ვცადოთ description / partner lookup
        if description_value:
            _update_pattern_feedback(cur, "description_exact", description_value, action)
        if partner_value:
            _update_pattern_feedback(cur, "partner", partner_value, action)


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
                SELECT * FROM journal_drafts
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
                SELECT * FROM journal_drafts
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


def approve_draft_service(draft_id: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("SELECT id, status FROM journal_drafts WHERE id = %s", (draft_id,))
        row = cur.fetchone()

        if not row:
            return error_response(
                "Not found",
                "NOT_FOUND",
                f"Draft {draft_id} not found",
            )

        current_status = row["status"]

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
            RETURNING id, status
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

        cur.execute("SELECT * FROM journal_drafts WHERE id = %s", (draft_id,))
        draft = cur.fetchone()

        save_feedback(
            draft_id=draft.get("id"),
            tx_fingerprint=draft.get("tx_fingerprint"),
            source_type=draft.get("source_type"),
            description_raw=draft.get("description"),
            description_normalized=draft.get("description"),
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

        if draft.get("classification_source") in (
            "pattern_learning",
            "pattern_learning_fuzzy",
            "human_correction",
        ):
            _update_patterns_for_draft_feedback(cur, draft, "approve")

        conn.commit()

    except Exception as e:
        conn.rollback()
        return error_response("Approve failed", "APPROVE_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    log_event(
        "draft_approved",
        {
            "draft_id": draft_id,
            "classification_source": draft.get("classification_source"),
            "pattern_matched_on": draft.get("pattern_matched_on"),
            "approved_by_mode": draft.get("approved_by_mode"),
        },
    )

    return ok_response("Draft approved", {"id": draft_id, "status": "approved"})


def reject_draft_service(draft_id: int, reason: str = ""):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("SELECT id, status FROM journal_drafts WHERE id = %s", (draft_id,))
        row = cur.fetchone()

        if not row:
            return error_response(
                "Not found",
                "NOT_FOUND",
                f"Draft {draft_id} not found",
            )

        current_status = row["status"]

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
            SET status = 'rejected',
                updated_at = NOW()
            WHERE id = %s
              AND status IN ('drafted', 'pending_approval', 'auto_approved')
            RETURNING id, status
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

        cur.execute("SELECT * FROM journal_drafts WHERE id = %s", (draft_id,))
        draft = cur.fetchone()

        save_feedback(
            draft_id=draft.get("id"),
            tx_fingerprint=draft.get("tx_fingerprint"),
            source_type=draft.get("source_type"),
            description_raw=draft.get("description"),
            description_normalized=draft.get("description"),
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

        if draft.get("classification_source") in (
            "pattern_learning",
            "pattern_learning_fuzzy",
            "human_correction",
        ):
            _update_patterns_for_draft_feedback(cur, draft, "reject")

        conn.commit()

    except Exception as e:
        conn.rollback()
        return error_response("Reject failed", "REJECT_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    log_event(
        "draft_rejected",
        {
            "draft_id": draft_id,
            "reason": reason,
            "classification_source": draft.get("classification_source"),
            "pattern_matched_on": draft.get("pattern_matched_on"),
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