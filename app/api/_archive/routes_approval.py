from fastapi import APIRouter
from typing import Optional
import psycopg2.extras

from app.api.db import get_db
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/approval", tags=["approval"])


def _log_audit(event_type: str, entity_id: int, details: dict):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO audit_events (id, event_type, actor, details, created_at)
            VALUES (gen_random_uuid(), %s, %s, %s::jsonb, NOW())
            """,
            (event_type, "system", psycopg2.extras.Json(details)),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass


@router.get("/queue")
def get_queue(status: str = "", limit: int = 100, offset: int = 0):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        where_sql = ""
        params = []

        if status:
            where_sql = "WHERE status = %s"
            params.append(status)
        else:
            where_sql = "WHERE status IN ('drafted', 'pending_approval')"

        query = f"""
            SELECT
                id,
                date,
                description,
                partner,
                amount,
                debit_account,
                credit_account,
                account_code,
                reason,
                confidence,
                review_required,
                status,
                source_type,
                created_at
            FROM journal_drafts
            {where_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])

        cur.execute(query, params)
        rows = [dict(r) for r in cur.fetchall()]

        count_query = f"""
            SELECT COUNT(*) AS total
            FROM journal_drafts
            {where_sql}
        """
        cur.execute(count_query, params[:-2])
        total = cur.fetchone()["total"]

        cur.close()
        conn.close()

        return ok_response(
            "Approval queue",
            {
                "count": total,
                "filter": status or "drafted+pending_approval",
                "limit": limit,
                "offset": offset,
                "queue": rows,
            },
        )

    except Exception as e:
        cur.close()
        conn.close()
        return error_response("Queue fetch failed", "QUEUE_ERROR", str(e))


@router.post("/approve/{draft_id}")
def approve_draft(draft_id: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("SELECT * FROM journal_drafts WHERE id = %s", (draft_id,))
        row = cur.fetchone()

        if not row:
            cur.close()
            conn.close()
            return error_response("Draft not found", "NOT_FOUND", "")

        cur.execute(
            """
            UPDATE journal_drafts
            SET status = 'approved'
            WHERE id = %s
            """,
            (draft_id,),
        )
        conn.commit()

        _log_audit(
            "draft_approved",
            draft_id,
            {
                "id": draft_id,
                "old_status": row["status"],
                "new_status": "approved",
                "description": row.get("description"),
            },
        )

        cur.close()
        conn.close()
        return ok_response("Draft approved", {"id": draft_id, "status": "approved"})

    except Exception as e:
        cur.close()
        conn.close()
        return error_response("Approve failed", "APPROVE_ERROR", str(e))


@router.post("/reject/{draft_id}")
def reject_draft(draft_id: int, reason: Optional[str] = ""):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("SELECT * FROM journal_drafts WHERE id = %s", (draft_id,))
        row = cur.fetchone()

        if not row:
            cur.close()
            conn.close()
            return error_response("Draft not found", "NOT_FOUND", "")

        cur.execute(
            """
            UPDATE journal_drafts
            SET status = 'rejected'
            WHERE id = %s
            """,
            (draft_id,),
        )
        conn.commit()

        _log_audit(
            "draft_rejected",
            draft_id,
            {
                "id": draft_id,
                "old_status": row["status"],
                "new_status": "rejected",
                "description": row.get("description"),
                "reason": reason or "",
            },
        )

        cur.close()
        conn.close()
        return ok_response(
            "Draft rejected",
            {"id": draft_id, "status": "rejected", "reason": reason or ""},
        )

    except Exception as e:
        cur.close()
        conn.close()
        return error_response("Reject failed", "REJECT_ERROR", str(e))


@router.get("/audit")
def approval_audit(limit: int = 50):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            """
            SELECT id, event_type, actor, details, created_at
            FROM audit_events
            WHERE event_type IN ('draft_approved', 'draft_rejected')
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()

        return ok_response("Audit log", {"count": len(rows), "events": rows})

    except Exception as e:
        cur.close()
        conn.close()
        return error_response("Audit fetch failed", "AUDIT_ERROR", str(e))