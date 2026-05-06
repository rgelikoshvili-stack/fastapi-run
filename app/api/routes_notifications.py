import logging
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel
from typing import Optional
from app.api.authz import require_permission

from app.api.email_service import (
    send_email,
    notify_draft_approved,
    notify_review_required,
    notify_reconciliation,
)
from app.api.response_utils import ok_response, error_response
from app.api.db import get_conn, _q
from app.api.tenant_context import resolve_tenant_id
log = logging.getLogger(__name__)


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
async def list_notifications(request: Request, limit: int = 20):
    require_permission(request, "notifications:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    items = []

    async with get_conn() as conn:
        try:
            rows = await conn.fetch(_q("""
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
            """), tenant_id, limit)
            items.extend([dict(r) for r in rows])
        except Exception as e:
            log.warning("unexpected error: %s", e)

        try:
            rows = await conn.fetch(_q("""
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
            """), tenant_id, limit)
            items.extend([dict(r) for r in rows])
        except Exception as e:
            log.warning("unexpected error: %s", e)

    items.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
    items = items[:limit]

    return ok_response("Notifications list", {
        "count": len(items),
        "items": items,
    })


@router.get("/feed")
async def notifications_feed(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    high_amount_threshold: float = Query(5000.0),
):
    """
    Enriched, actionable notification feed. Read-only. No emails sent.
    Types: pending_approval, high_amount, failed_posting, repeated_anomaly.
    """
    require_permission(request, "notifications:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    items = []

    try:
        async with get_conn() as conn:
            rows = await conn.fetch(_q("""
                SELECT id, description, partner, amount, account_code, created_at
                FROM journal_drafts
                WHERE tenant_id = %s AND status = 'pending_approval'
                ORDER BY created_at DESC
                LIMIT %s
            """), tenant_id, limit)
            for row in rows:
                amt = float(row["amount"] or 0)
                items.append({
                    "type": "pending_approval",
                    "severity": "warning",
                    "title": "დასამტკიცებელი draft",
                    "message": (
                        f"Draft #{row['id']} — {row['description'] or 'N/A'} "
                        f"({amt:,.2f} GEL) ელოდება დამტკიცებას"
                    ),
                    "draft_id": row["id"],
                    "amount": amt,
                    "account_code": row["account_code"],
                    "partner": row["partner"],
                    "created_at": str(row["created_at"]),
                    "action": f"/approval/approve/{row['id']}",
                })

            rows = await conn.fetch(_q("""
                SELECT id, description, partner, amount, account_code, status, created_at
                FROM journal_drafts
                WHERE tenant_id = %s
                  AND amount >= %s
                  AND status IN ('drafted', 'pending_approval')
                ORDER BY amount DESC
                LIMIT 20
            """), tenant_id, high_amount_threshold)
            for row in rows:
                amt = float(row["amount"] or 0)
                items.append({
                    "type": "high_amount",
                    "severity": "critical",
                    "title": "მაღალი თანხა — საჭიროა შემოწმება",
                    "message": (
                        f"Draft #{row['id']}: {row['description'] or 'N/A'} — "
                        f"{amt:,.2f} GEL (status: {row['status']})"
                    ),
                    "draft_id": row["id"],
                    "amount": amt,
                    "account_code": row["account_code"],
                    "partner": row["partner"],
                    "created_at": str(row["created_at"]),
                    "action": f"/posting/preview/{row['id']}",
                })

            try:
                rows = await conn.fetch(_q("""
                    SELECT pl.id, pl.draft_id, pl.target_system,
                           pl.error_message, pl.created_at,
                           jd.description, jd.amount
                    FROM posting_logs pl
                    LEFT JOIN journal_drafts jd
                      ON jd.id = pl.draft_id AND jd.tenant_id = %s
                    WHERE pl.tenant_id = %s
                      AND pl.status = 'error'
                      AND pl.created_at >= NOW() - INTERVAL '7 days'
                    ORDER BY pl.created_at DESC
                    LIMIT 20
                """), tenant_id, tenant_id)
                for row in rows:
                    amt = float(row["amount"] or 0) if row["amount"] else None
                    items.append({
                        "type": "failed_posting",
                        "severity": "critical",
                        "title": "Posting-ი ვერ მოხდა",
                        "message": (
                            f"Draft #{row['draft_id']} → {row['target_system']}: "
                            f"{(row['error_message'] or 'unknown error')[:120]}"
                        ),
                        "draft_id": row["draft_id"],
                        "amount": amt,
                        "account_code": None,
                        "partner": None,
                        "created_at": str(row["created_at"]),
                        "action": f"/posting/apply/{row['draft_id']}",
                    })
            except Exception as e:
                log.warning("unexpected error: %s", e)

            rows = await conn.fetch(_q("""
                SELECT description, COUNT(*) AS cnt, SUM(amount) AS total
                FROM journal_drafts
                WHERE tenant_id = %s
                  AND status IN ('drafted', 'pending_approval')
                  AND description IS NOT NULL
                GROUP BY description
                HAVING COUNT(*) >= 3
                ORDER BY cnt DESC
                LIMIT 10
            """), tenant_id)
            for row in rows:
                items.append({
                    "type": "repeated_anomaly",
                    "severity": "warning",
                    "title": "განმეორებადი ტრანზაქცია",
                    "message": (
                        f"'{row['description']}' — {row['cnt']}-ჯერ pending, "
                        f"ჯამი: {float(row['total'] or 0):,.2f} GEL"
                    ),
                    "draft_id": None,
                    "amount": float(row["total"] or 0),
                    "account_code": None,
                    "partner": None,
                    "created_at": None,
                    "action": "/approval/queue",
                })

    except Exception as e:
        return error_response("Notifications feed failed", "FEED_ERROR", str(e))

    items.sort(
        key=lambda x: (
            {"critical": 0, "warning": 1, "info": 2}.get(x["severity"], 3),
            x["created_at"] or "",
        ),
        reverse=False,
    )
    items = items[:limit]

    summary = {
        "total": len(items),
        "critical": sum(1 for i in items if i["severity"] == "critical"),
        "warning": sum(1 for i in items if i["severity"] == "warning"),
        "info": sum(1 for i in items if i["severity"] == "info"),
    }

    return ok_response("Notifications feed", {
        "tenant_id": tenant_id,
        "summary": summary,
        "items": items,
    })


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
async def notify_approved(req: NotifyApprovalRequest, request: Request):
    require_permission(request, "notifications:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    to_email = req.to or req.email

    async with get_conn() as conn:
        draft = await conn.fetchrow(_q(
            "SELECT * FROM journal_drafts WHERE id = %s AND tenant_id = %s"
        ), req.draft_id, tenant_id)

    if not draft:
        return error_response("Draft not found", "NOT_FOUND", "")

    result = notify_draft_approved(to_email, dict(draft))
    return ok_response("Notification sent", result)


@router.post("/review-required")
async def notify_review(req: TestEmailRequest, request: Request):
    require_permission(request, "notifications:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    to_email = req.to or req.email

    async with get_conn() as conn:
        count = await conn.fetchval(_q(
            "SELECT COUNT(*) FROM journal_drafts WHERE status = 'pending_approval' AND tenant_id = %s"
        ), tenant_id)

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