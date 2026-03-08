from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from app.api.email_service import send_email, notify_draft_approved, notify_review_required, notify_reconciliation
from app.api.response_utils import ok_response, error_response
from app.api.db import get_db
import psycopg2.extras

router = APIRouter(prefix="/notifications", tags=["notifications"])

class TestEmailRequest(BaseModel):
    to: Optional[str] = None
    email: Optional[str] = None
    subject: Optional[str] = "Bridge Hub Test"
    message: Optional[str] = "Test notification from Bridge Hub"

class NotifyApprovalRequest(BaseModel):
    to: Optional[str] = None
    email: Optional[str] = None
    draft_id: int

class NotifyReconcileRequest(BaseModel):
    to: Optional[str] = None
    email: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None

@router.post("/test")
def test_notification(req: TestEmailRequest):
    result = send_email(
        req.to, req.subject,
        f"<h2>{req.message}</h2><p>Bridge Hub v1.0.0</p>",
        req.message
    )
    if result.get("sent"):
        return ok_response("Email sent", result)
    return ok_response("Email queued (SMTP not configured)", result)

@router.post("/draft-approved")
def notify_approved(req: NotifyApprovalRequest):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM journal_drafts WHERE id=%s", (req.draft_id,))
        draft = cur.fetchone()
    finally:
        cur.close(); conn.close()
    if not draft:
        return error_response("Draft not found", "NOT_FOUND", "")
    result = notify_draft_approved(req.to, dict(draft))
    return ok_response("Notification sent", result)

@router.post("/review-required")
def notify_review(req: TestEmailRequest):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM journal_drafts WHERE status='pending_approval'")
        count = cur.fetchone()[0]
    finally:
        cur.close(); conn.close()
    result = notify_review_required(req.to, count)
    return ok_response("Notification sent", {"pending_count": count, **result})

@router.post("/reconciliation-report")
def notify_reconcile(req: NotifyReconcileRequest):
    from app.api.routes_reconciliation_v2 import run_reconciliation
    from pydantic import BaseModel as BM
    class R(BM):
        date_from: Optional[str] = None
        date_to: Optional[str] = None
        tenant_code: Optional[str] = None
    recon = run_reconciliation(R(date_from=req.date_from, date_to=req.date_to))
    result = notify_reconciliation(req.to, recon.get("data", {}))
    return ok_response("Reconciliation report sent", result)
