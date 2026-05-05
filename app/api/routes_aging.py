"""app/api/routes_aging.py — AR/AP Aging Reports (receivables + payables) + overdue reminders."""
import logging
import os
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from fastapi import APIRouter, Request, Query

from app.api.authz import require_permission
from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, error_response
from app.api.security import limiter
from app.api.tenant_context import resolve_tenant_id

log = logging.getLogger(__name__)
router = APIRouter(prefix="/reports/aging", tags=["reports"])

_BUCKETS = [
    ("current",  0,   30,  "მიმდინარე (0–30)"),
    ("31_60",    31,  60,  "31–60 დღე"),
    ("61_90",    61,  90,  "61–90 დღე"),
    ("91_120",   91,  120, "91–120 დღე"),
    ("over_120", 121, None,"120+ დღე"),
]


def _bucket(days_overdue: int) -> str:
    for key, lo, hi, _ in _BUCKETS:
        if days_overdue <= (hi or 999999) and days_overdue >= lo:
            return key
    return "over_120"


def _build_summary(rows: list, as_of: date) -> dict:
    totals = {key: {"label": label, "count": 0, "amount": 0.0}
              for key, _, _, label in _BUCKETS}
    for r in rows:
        due = r.get("due_date")
        if not due:
            k = "current"
        else:
            if isinstance(due, str):
                due = date.fromisoformat(due[:10])
            days = (as_of - due).days
            k = _bucket(max(days, 0))
        totals[k]["count"] += 1
        totals[k]["amount"] = round(totals[k]["amount"] + float(r.get("outstanding", 0) or 0), 2)
    return totals


@router.get("/receivables")
async def ar_aging(
    request: Request,
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD, default today"),
    partner: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    """AR aging — outstanding customer invoices by age bucket."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    as_of_date = date.fromisoformat(as_of) if as_of else date.today()

    conditions = ["tenant_id = %s", "status IN ('sent','overdue','partial')"]
    params: list = [tenant_id]
    if partner:
        conditions.append("partner ILIKE %s"); params.append(f"%{partner}%")
    where = " AND ".join(conditions)

    try:
        async with get_conn() as conn:
            rows = [dict(r) for r in await conn.fetch(_q(f"""
                SELECT
                    id, invoice_number, partner, issue_date, due_date,
                    total, COALESCE(paid_amount, 0) AS paid_amount,
                    total - COALESCE(paid_amount, 0) AS outstanding,
                    currency, status, notes
                FROM invoices
                WHERE {where}
                  AND total > COALESCE(paid_amount, 0)
                ORDER BY due_date ASC NULLS LAST
                LIMIT %s
            """), *params, limit)]
    except Exception as e:
        log.warning("ar_aging query failed: %s", e)
        rows = []

    for r in rows:
        for f in ("issue_date", "due_date"):
            if r.get(f):
                r[f] = str(r[f])[:10]
        if r.get("due_date"):
            due = date.fromisoformat(r["due_date"])
            days = (as_of_date - due).days
            r["days_overdue"] = max(days, 0)
            r["bucket"] = _bucket(max(days, 0))
        else:
            r["days_overdue"] = 0
            r["bucket"] = "current"

    summary = _build_summary(rows, as_of_date)
    total_outstanding = round(sum(b["amount"] for b in summary.values()), 2)

    return ok_response("AR Aging", {
        "as_of": str(as_of_date),
        "total_outstanding": total_outstanding,
        "buckets": summary,
        "invoices": rows,
    })


@router.get("/payables")
async def ap_aging(
    request: Request,
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD, default today"),
    partner: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    """AP aging — outstanding supplier obligations by age bucket."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    as_of_date = date.fromisoformat(as_of) if as_of else date.today()

    conditions = [
        "tenant_id = %s",
        "status IN ('approved','auto_approved','posted')",
        "(credit_account >= '3100' AND credit_account <= '3399')",
        "(reconciled = FALSE OR reconciled IS NULL)",
    ]
    params: list = [tenant_id]
    if partner:
        conditions.append("partner ILIKE %s"); params.append(f"%{partner}%")
    where = " AND ".join(conditions)

    try:
        async with get_conn() as conn:
            rows = [dict(r) for r in await conn.fetch(_q(f"""
                SELECT
                    id, date AS issue_date, description, partner,
                    ABS(amount) AS outstanding,
                    credit_account AS account, status, created_at
                FROM journal_drafts
                WHERE {where}
                  AND amount < 0
                ORDER BY date ASC NULLS LAST
                LIMIT %s
            """), *params, limit)]
    except Exception as e:
        log.warning("ap_aging query failed: %s", e)
        rows = []

    for r in rows:
        if r.get("issue_date"):
            r["issue_date"] = str(r["issue_date"])[:10]
        created = r.get("issue_date") or str(r.get("created_at", ""))[:10]
        if created:
            try:
                created_dt = date.fromisoformat(created[:10])
                days = (as_of_date - created_dt).days
                r["days_overdue"] = max(days, 0)
                r["bucket"] = _bucket(max(days, 0))
            except ValueError:
                r["days_overdue"] = 0
                r["bucket"] = "current"
        else:
            r["days_overdue"] = 0
            r["bucket"] = "current"
        r["due_date"] = None

    summary = _build_summary(rows, as_of_date)
    total_outstanding = round(sum(b["amount"] for b in summary.values()), 2)

    return ok_response("AP Aging", {
        "as_of": str(as_of_date),
        "total_outstanding": total_outstanding,
        "buckets": summary,
        "payables": rows,
    })


@router.get("/summary")
async def aging_summary(
    request: Request,
    as_of: Optional[str] = Query(None),
):
    """Quick combined AR + AP snapshot for dashboard widget."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    as_of_date = date.fromisoformat(as_of) if as_of else date.today()

    try:
        async with get_conn() as conn:
            ar = await conn.fetchrow(_q("""
                SELECT
                    COUNT(*) FILTER (WHERE due_date < %s) AS overdue_count,
                    COALESCE(SUM(total - COALESCE(paid_amount,0))
                        FILTER (WHERE due_date < %s), 0) AS overdue_amount,
                    COALESCE(SUM(total - COALESCE(paid_amount,0)), 0) AS total_ar
                FROM invoices
                WHERE tenant_id = %s AND status IN ('sent','overdue','partial')
                  AND total > COALESCE(paid_amount, 0)
            """), as_of_date, as_of_date, tenant_id)
            ap = await conn.fetchrow(_q("""
                SELECT
                    COUNT(*) AS total_ap_count,
                    COALESCE(SUM(ABS(amount)), 0) AS total_ap
                FROM journal_drafts
                WHERE tenant_id = %s
                  AND status IN ('approved','auto_approved','posted')
                  AND (credit_account >= '3100' AND credit_account <= '3399')
                  AND amount < 0
                  AND (reconciled = FALSE OR reconciled IS NULL)
            """), tenant_id)
    except Exception:
        ar = None
        ap = None

    return ok_response("Aging summary", {
        "as_of": str(as_of_date),
        "ar": {
            "overdue_count": int((ar or {}).get("overdue_count") or 0),
            "overdue_amount": round(float((ar or {}).get("overdue_amount") or 0), 2),
            "total_outstanding": round(float((ar or {}).get("total_ar") or 0), 2),
        },
        "ap": {
            "total_count": int((ap or {}).get("total_ap_count") or 0),
            "total_outstanding": round(float((ap or {}).get("total_ap") or 0), 2),
        },
    })


def _send_reminder_email(to_email: str, buyer_name: str, invoice_number: str,
                         total: float, due_date: str, days_overdue: int,
                         seller_name: str) -> None:
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    if not smtp_user or not smtp_pass:
        raise RuntimeError("SMTP not configured")

    subject = f"გადახდის შეხსენება — ინვოისი {invoice_number}"
    html = f"""
    <div style="font-family:Georgia,serif;max-width:520px;margin:40px auto;
                background:#f3ecdc;padding:32px;border-radius:8px">
      <h2 style="color:#8c3c2d;margin:0 0 8px">Bridge Hub</h2>
      <p style="color:#4a3728;margin:0 0 20px">გამარჯობა, <strong>{buyer_name or 'კლიენტო'}</strong>,</p>
      <p style="color:#4a3728;margin:0 0 16px">
        გეხსენებათ, რომ <strong>{seller_name}</strong>-ის ინვოისი
        <strong>#{invoice_number}</strong> ჯერ გადაუხდელია.
      </p>
      <table style="width:100%;border-collapse:collapse;margin:0 0 20px">
        <tr><td style="padding:8px;color:#4a3728">ინვოისი №</td>
            <td style="padding:8px;font-weight:bold;color:#8c3c2d">{invoice_number}</td></tr>
        <tr style="background:#fff8f0"><td style="padding:8px;color:#4a3728">გადახდის ვადა</td>
            <td style="padding:8px;color:#8c3c2d"><strong>{due_date}</strong></td></tr>
        <tr><td style="padding:8px;color:#4a3728">ვადაგადაცილება</td>
            <td style="padding:8px;color:#c0392b"><strong>{days_overdue} დღე</strong></td></tr>
        <tr style="background:#fff8f0"><td style="padding:8px;color:#4a3728">დასაფარი თანხა</td>
            <td style="padding:8px;font-weight:bold;font-size:16px;color:#8c3c2d">₾{total:,.2f}</td></tr>
      </table>
      <p style="color:#888;font-size:13px;margin:0">
        გთხოვთ, განახორციელოთ გადახდა რაც შეიძლება მალე.<br>
        კითხვების შემთხვევაში დაგვიკავშირდით.
      </p>
    </div>
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(smtp_user, smtp_pass)
        s.sendmail(smtp_user, to_email, msg.as_string())


@router.post("/send-reminders")
@limiter.limit("5/minute")
async def send_overdue_reminders(
    request: Request,
    min_days_overdue: int = Query(1, ge=1, description="Minimum days overdue to trigger reminder"),
    resend_after_days: int = Query(7, ge=1, description="Re-send if last reminder was N+ days ago"),
    dry_run: bool = Query(False, description="If true, return list without sending emails"),
):
    """Send reminder emails for all overdue outgoing invoices."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    today = date.today()

    try:
        async with get_conn() as conn:
            # Ensure columns exist
            try:
                await conn.execute("""
                    ALTER TABLE outgoing_invoices
                      ADD COLUMN IF NOT EXISTS due_date DATE,
                      ADD COLUMN IF NOT EXISTS reminder_sent_at TIMESTAMP
                """)
            except Exception as e:
                log.warning("unexpected error: %s", e)

            invoices = [dict(r) for r in await conn.fetch(_q("""
                SELECT id, invoice_number, buyer_name, buyer_email,
                       total_amount, due_date, reminder_sent_at, seller_name
                FROM outgoing_invoices
                WHERE tenant_id = %s
                  AND status IN ('sent', 'overdue')
                  AND due_date IS NOT NULL
                  AND due_date < %s
                  AND buyer_email IS NOT NULL AND buyer_email != ''
                  AND (%s - due_date) >= %s
                  AND (
                      reminder_sent_at IS NULL
                      OR reminder_sent_at < NOW() - (%s || ' days')::INTERVAL
                  )
                ORDER BY due_date ASC
                LIMIT 100
            """), tenant_id, today, today, min_days_overdue, str(resend_after_days))]
    except Exception as e:
        log.error("send_reminders query failed: %s", e)
        return error_response("Query failed", "DB_ERROR", str(e))

    sent, errors = [], []

    for inv in invoices:
        inv_id = inv["id"]
        inv_num = inv["invoice_number"] or str(inv_id)
        buyer_email = inv["buyer_email"]
        days_overdue = (today - inv["due_date"]).days if inv.get("due_date") else 0

        if dry_run:
            sent.append({"id": inv_id, "invoice": inv_num,
                         "email": buyer_email, "days_overdue": days_overdue})
            continue

        try:
            _send_reminder_email(
                to_email=buyer_email,
                buyer_name=inv.get("buyer_name") or "",
                invoice_number=inv_num,
                total=float(inv.get("total_amount") or 0),
                due_date=str(inv.get("due_date", "")),
                days_overdue=days_overdue,
                seller_name=inv.get("seller_name") or tenant_id,
            )
            async with get_conn() as conn2:
                await conn2.execute(_q("""
                    UPDATE outgoing_invoices
                    SET status = 'overdue', reminder_sent_at = NOW()
                    WHERE id = %s AND tenant_id = %s
                """), inv_id, tenant_id)
            sent.append({"id": inv_id, "invoice": inv_num,
                         "email": buyer_email, "days_overdue": days_overdue})
            log.info("reminder_sent invoice=%s tenant=%s email=%s days_overdue=%s",
                     inv_num, tenant_id, buyer_email, days_overdue)
        except Exception as e:
            log.error("reminder_failed invoice=%s: %s", inv_num, e)
            errors.append({"id": inv_id, "invoice": inv_num, "error": str(e)})

    return ok_response("Reminders processed", {
        "dry_run": dry_run,
        "sent_count": len(sent),
        "error_count": len(errors),
        "sent": sent,
        "errors": errors,
    })
