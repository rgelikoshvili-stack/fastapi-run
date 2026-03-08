from app.api.audit_service import log_event
from fastapi import APIRouter
import psycopg2, psycopg2.extras
from app.api.db import get_db
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/approval", tags=["approval"])

@router.get("/queue")
def get_queue():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM journal_drafts WHERE status IN ('drafted','pending_approval') ORDER BY created_at DESC LIMIT 100")
        items = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        return error_response("Queue failed", "QUEUE_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Approval queue", {"count": len(items), "items": items})

@router.post("/approve/{draft_id}")
def approve_draft(draft_id: int):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE journal_drafts SET status='approved' WHERE id=%s RETURNING id", (draft_id,))
        row = cur.fetchone()
        conn.commit()
        if not row:
            return error_response("Not found", "NOT_FOUND", f"Draft {draft_id} not found")
    except Exception as e:
        conn.rollback()
        return error_response("Approve failed", "APPROVE_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    log_event("draft_approved", {"draft_id": draft_id})
    return ok_response("Draft approved", {"id": draft_id, "status": "approved"})

@router.post("/reject/{draft_id}")
def reject_draft(draft_id: int, data: dict = {}):
    conn = get_db()
    cur = conn.cursor()
    try:
        reason = data.get("reason", "")
        cur.execute("UPDATE journal_drafts SET status='rejected' WHERE id=%s RETURNING id", (draft_id,))
        row = cur.fetchone()
        conn.commit()
        if not row:
            return error_response("Not found", "NOT_FOUND", f"Draft {draft_id} not found")
    except Exception as e:
        conn.rollback()
        return error_response("Reject failed", "REJECT_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    log_event("draft_rejected", {"draft_id": draft_id, "reason": reason})
    return ok_response("Draft rejected", {"id": draft_id, "status": "rejected", "reason": reason})

@router.get("/audit")
def get_audit_log():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM audit_events ORDER BY created_at DESC LIMIT 50")
        events = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        return error_response("Audit failed", "AUDIT_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Audit log", {"count": len(events), "events": events})
