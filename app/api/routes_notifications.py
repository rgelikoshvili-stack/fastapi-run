from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
import psycopg2.extras

from app.api.email_service import (
    send_email,
    notify_draft_approved,
    notify_review_required,
    notify_reconciliation,
)
from app.api.response_utils import ok_response, error_response
from app.api.db import get_db

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


@router.get("/list")
def list_notifications(request: Request, limit: int = 20):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        items = []

        try:
            cur.execute("""
                SELECT
                    id,
                    status,
                    created_at,
                    'draft_pending' AS notification_type,
                    COALESCE(description, 'Draft pending approval') AS message
                FROM journal_drafts
                WHERE status = 'pending_approval' AND tenant_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (tenant_id, limit))
            for row in cur.fetchall():
                items.append(dict(row))
        except Exception:
            pass

        try:
            cur.execute("""
                SELECT
                    id,
                    COALESCE(event_time, created_at) AS created_at,
                    'audit_error' AS notification_type,
                    COALESCE(details, action, 'Audit event') AS message,
                    status
                FROM audit_log
                WHERE status = 'error' AND tenant_id = %s
                ORDER BY COALESCE(event_time, created_at) DESC
                LIMIT %s
            """, (tenant_id, limit))
            for row in cur.fetchall():
                items.append(dict(row))
        except Exception:
            pass

        items.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
        items = items[:limit]

        return ok_response("Notifications list", {
            "count": len(items),
            "items": items,
        })

    finally:
        cur.close()
        conn.close()


@router.post("/test")
def test_notification(req: TestEmailRequest):
    to_email = req.to or req.email
    result = send_email(
        to_email,
        req.subject,
        f"<h2>{req.message}</h2><p>Bridge Hub v1.0.0</p>",
        req.message,
    )

    if result.get("sent"):
        return ok_response("Email sent", result)

    return ok_response("Email queued (SMTP not configured)", result)


@router.post("/draft-approved")
def notify_approved(req: NotifyApprovalRequest, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    to_email = req.to or req.email

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            "SELECT * FROM journal_drafts WHERE id = %s AND tenant_id = %s",
            (req.draft_id, tenant_id),
        )
        draft = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not draft:
        return error_response("Draft not found", "NOT_FOUND", "")

    result = notify_draft_approved(to_email, dict(draft))
    return ok_response("Notification sent", result)


@router.post("/review-required")
def notify_review(req: TestEmailRequest, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    to_email = req.to or req.email

    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute(
            "SELECT COUNT(*) FROM journal_drafts WHERE status = 'pending_approval' AND tenant_id = %s",
            (tenant_id,),
        )
        count = cur.fetchone()[0]
    finally:
        cur.close()
        conn.close()

    result = notify_review_required(to_email, count)
    return ok_response("Notification sent", {"pending_count": count, **result})


@router.post("/reconciliation-report")
def notify_reconcile(req: NotifyReconcileRequest):
    to_email = req.to or req.email

    from app.api.routes_reconciliation_v2 import run_reconciliation
    from pydantic import BaseModel as BM

    class R(BM):
        date_from: Optional[str] = None
        date_to: Optional[str] = None
        tenant_code: Optional[str] = None

    recon = run_reconciliation(R(date_from=req.date_from, date_to=req.date_to))
    result = notify_reconciliation(to_email, recon.get("data", {}))
    return ok_response("Reconciliation report sent", result)
