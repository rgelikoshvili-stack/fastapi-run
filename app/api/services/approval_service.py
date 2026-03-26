import psycopg2.extras

from app.api.db import get_db
from app.api.response_utils import ok_response, error_response
from app.api.audit_service import log_event
from app.api.services.learning_service import (
    apply_approve_learning,
    apply_reject_learning,
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
                approved_by_mode = COALESCE(approved_by_mode, 'manual_review'),
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

        conn.commit()

    except Exception as e:
        conn.rollback()
        return error_response("Approve failed", "APPROVE_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    learning_result = apply_approve_learning(
        draft,
        approved_by_mode=updated.get("approved_by_mode") or "manual_review",
    ) or {}

    log_event(
        "draft_approved",
        {
            "draft_id": draft_id,
            "approved_by_mode": updated.get("approved_by_mode"),
            "classification_source": draft.get("classification_source"),
            "pattern_matched_on": draft.get("pattern_matched_on"),
            "pattern_value_used": draft.get("pattern_value_used"),
            "learning_result": learning_result,
        },
    )

    return ok_response(
        "Draft approved",
        {
            "id": draft_id,
            "status": "approved",
            "approved_by_mode": updated.get("approved_by_mode"),
            "learning_result": learning_result,
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

        conn.commit()

    except Exception as e:
        conn.rollback()
        return error_response("Reject failed", "REJECT_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    learning_result = apply_reject_learning(draft, reason=reason) or {}

    log_event(
        "draft_rejected",
        {
            "draft_id": draft_id,
            "reason": reason,
            "classification_source": draft.get("classification_source"),
            "pattern_matched_on": draft.get("pattern_matched_on"),
            "pattern_value_used": draft.get("pattern_value_used"),
            "learning_result": learning_result,
        },
    )

    return ok_response(
        "Draft rejected",
        {
            "id": draft_id,
            "status": "rejected",
            "reason": reason,
            "learning_result": learning_result,
        },
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