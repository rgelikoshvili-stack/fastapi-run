from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import psycopg2.extras

from app.api.db import get_db
from app.api.response_utils import ok_response, error_response
from app.api.audit_service import log_event

router = APIRouter(prefix="/approval", tags=["approval"])


def _validate_pagination(limit: int, offset: int):
    if limit < 0:
        raise HTTPException(
            status_code=422,
            detail={"error": "INVALID_PAGINATION", "message": "limit უნდა იყოს 0 ან მეტი"}
        )
    if offset < 0:
        raise HTTPException(
            status_code=422,
            detail={"error": "INVALID_PAGINATION", "message": "offset უნდა იყოს 0 ან მეტი"}
        )


def _fix_text(value):
    if not isinstance(value, str):
        return value

    s = value
    candidates = [s]

    try:
        candidates.append(s.encode("latin1").decode("utf-8"))
    except Exception:
        pass

    try:
        candidates.append(s.encode("cp1252").decode("utf-8"))
    except Exception:
        pass

    try:
        candidates.append(
            s.encode("latin1").decode("utf-8").encode("latin1").decode("utf-8")
        )
    except Exception:
        pass

    def score(text):
        if not isinstance(text, str):
            return -1
        good = 0
        for ch in text:
            o = ord(ch)
            if 0x10A0 <= o <= 0x10FF:
                good += 3
            elif ch.isalpha():
                good += 1
            elif ch.isdigit() or ch in " .,:-_/()[]":
                good += 0.2
        for m in ("á", "Ã", "¢", "£", "â", "Ð", "Ñ"):
            good -= text.count(m) * 2
        return good

    return max(candidates, key=score)


def _fix_item(item: dict):
    return {k: _fix_text(v) for k, v in item.items()}


class RejectRequest(BaseModel):
    reason: Optional[str] = ""


# ─── QUEUE ────────────────────────────────────────────────────────────────────

@router.get("/queue")
def get_queue(status: str = "", limit: int = 100, offset: int = 0):
    _validate_pagination(limit, offset)
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
                SELECT COUNT(*) AS total FROM journal_drafts
                WHERE status IN ('drafted', 'pending_approval')
                """
            )
            total = cur.fetchone()["total"]

            cur.execute(
                """
                SELECT * FROM journal_drafts
                WHERE status IN ('drafted', 'pending_approval')
                ORDER BY created_at DESC, id DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )

        items = [_fix_item(dict(r)) for r in cur.fetchall()]

    except Exception as e:
        return error_response("Queue failed", "QUEUE_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    return ok_response("Approval queue", {
        "count": total,
        "filter": status or "drafted+pending_approval",
        "limit": limit,
        "offset": offset,
        "queue": items,
    })


# ─── APPROVE ──────────────────────────────────────────────────────────────────

@router.post("/approve/{draft_id}")
def approve_draft(draft_id: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("SELECT id, status FROM journal_drafts WHERE id = %s", (draft_id,))
        row = cur.fetchone()

        if not row:
            return error_response("Not found", "NOT_FOUND", f"Draft {draft_id} not found")

        current_status = row["status"]

        if current_status == "approved":
            return error_response("Already approved", "ALREADY_APPROVED", f"Draft {draft_id} is already approved")

        if current_status == "rejected":
            return error_response("Already rejected", "ALREADY_REJECTED", f"Draft {draft_id} is already rejected and cannot be approved")

        cur.execute(
            """
            UPDATE journal_drafts
            SET status = 'approved'
            WHERE id = %s AND status IN ('drafted', 'pending_approval')
            RETURNING id, status
            """,
            (draft_id,),
        )
        updated = cur.fetchone()
        conn.commit()

        if not updated:
            return error_response("Approve blocked", "APPROVE_BLOCKED", f"Draft {draft_id} could not be approved")

    except Exception as e:
        conn.rollback()
        return error_response("Approve failed", "APPROVE_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    log_event("draft_approved", {"draft_id": draft_id})
    return ok_response("Draft approved", {"id": draft_id, "status": "approved"})


# ─── REJECT ───────────────────────────────────────────────────────────────────

@router.post("/reject/{draft_id}")
def reject_draft(draft_id: int, req: RejectRequest = RejectRequest()):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("SELECT id, status FROM journal_drafts WHERE id = %s", (draft_id,))
        row = cur.fetchone()

        if not row:
            return error_response("Not found", "NOT_FOUND", f"Draft {draft_id} not found")

        current_status = row["status"]

        if current_status == "rejected":
            return error_response("Already rejected", "ALREADY_REJECTED", f"Draft {draft_id} is already rejected")

        if current_status == "approved":
            return error_response("Already approved", "ALREADY_APPROVED", f"Draft {draft_id} is already approved and cannot be rejected")

        cur.execute(
            """
            UPDATE journal_drafts
            SET status = 'rejected'
            WHERE id = %s AND status IN ('drafted', 'pending_approval')
            RETURNING id, status
            """,
            (draft_id,),
        )
        updated = cur.fetchone()
        conn.commit()

        if not updated:
            return error_response("Reject blocked", "REJECT_BLOCKED", f"Draft {draft_id} could not be rejected")

    except Exception as e:
        conn.rollback()
        return error_response("Reject failed", "REJECT_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    log_event("draft_rejected", {"draft_id": draft_id, "reason": req.reason})
    return ok_response("Draft rejected", {"id": draft_id, "status": "rejected", "reason": req.reason})


# ─── AUDIT ────────────────────────────────────────────────────────────────────

@router.get("/audit")
def get_audit_log(limit: int = 50, offset: int = 0):
    _validate_pagination(limit, offset)
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            """
            SELECT * FROM audit_events
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        events = [_fix_item(dict(r)) for r in cur.fetchall()]

    except Exception as e:
        return error_response("Audit failed", "AUDIT_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    return ok_response("Audit log", {"count": len(events), "events": events})