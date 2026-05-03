"""app/api/routes_recurring.py — Recurring invoice templates + scheduler trigger.

Table: recurring_invoice_templates
  - id, tenant_id, name, frequency (monthly|weekly|quarterly|yearly)
  - next_run_date, last_run_date, active
  - template payload: same fields as InvoiceCreateRequest
  - created_at, updated_at

Trigger: POST /recurring/run — generates due invoices (called by scheduler or manually).
"""
import logging
import os
import smtplib
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, List

import psycopg2.extras
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel, Field

from app.api.authz import require_permission
from app.api.db import get_db
from app.api.response_utils import ok_response, error_response, http_error
from app.api.security import limiter
from app.api.tenant_context import resolve_tenant_id

router = APIRouter(prefix="/recurring", tags=["recurring"])
log = logging.getLogger(__name__)

_FREQ_DAYS = {
    "weekly":    7,
    "monthly":   30,
    "quarterly": 90,
    "yearly":    365,
}


# ── Email helper ─────────────────────────────────────────────────────────────

def _send_invoice_email(to_email: str, buyer_name: str, seller_name: str,
                        invoice_id: int, due_date: str, total: float) -> None:
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    if not smtp_user or not smtp_pass:
        raise RuntimeError("SMTP not configured")

    subject = f"ინვოისი — {seller_name or 'Bridge Hub'}"
    html = f"""
    <div style="font-family:Georgia,serif;max-width:520px;margin:40px auto;
                background:#f3ecdc;padding:32px;border-radius:8px">
      <h2 style="color:#8c3c2d;margin:0 0 8px">Bridge Hub</h2>
      <p style="color:#4a3728;margin:0 0 20px">გამარჯობა, <strong>{buyer_name or 'კლიენტო'}</strong>,</p>
      <p style="color:#4a3728;margin:0 0 16px">
        გამოგიგზავნეთ ახალი ინვოისი <strong>{seller_name}</strong>-ისგან.
      </p>
      <table style="width:100%;border-collapse:collapse;margin:0 0 20px">
        <tr><td style="padding:8px;color:#4a3728">ინვოისი №</td>
            <td style="padding:8px;font-weight:bold;color:#8c3c2d">#{invoice_id}</td></tr>
        <tr style="background:#fff8f0"><td style="padding:8px;color:#4a3728">გადახდის ვადა</td>
            <td style="padding:8px;color:#8c3c2d"><strong>{due_date or '—'}</strong></td></tr>
        <tr><td style="padding:8px;color:#4a3728">სულ გადასახდელი</td>
            <td style="padding:8px;font-weight:bold;font-size:16px;color:#8c3c2d">₾{total:,.2f}</td></tr>
      </table>
      <p style="color:#888;font-size:13px;margin:0">
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


# ── DB bootstrap ──────────────────────────────────────────────────────────────

def _ensure_table(conn):
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS recurring_invoice_templates (
                id              SERIAL PRIMARY KEY,
                tenant_id       TEXT NOT NULL,
                name            TEXT NOT NULL,
                frequency       TEXT NOT NULL DEFAULT 'monthly',
                next_run_date   DATE NOT NULL,
                last_run_date   DATE,
                active          BOOLEAN DEFAULT TRUE,
                auto_send       BOOLEAN DEFAULT FALSE,
                invoice_type    TEXT DEFAULT 'service',
                seller_name     TEXT,
                seller_inn      TEXT,
                seller_address  TEXT,
                seller_phone    TEXT,
                seller_bank     TEXT,
                seller_swift    TEXT,
                seller_account  TEXT,
                buyer_inn       TEXT,
                buyer_name      TEXT,
                buyer_email     TEXT,
                buyer_address   TEXT,
                buyer_phone     TEXT,
                due_days        INT DEFAULT 30,
                line_items      JSONB DEFAULT '[]',
                comment         TEXT,
                created_at      TIMESTAMP DEFAULT NOW(),
                updated_at      TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()
    finally:
        cur.close()


# ── Models ────────────────────────────────────────────────────────────────────

class LineItem(BaseModel):
    description: str = ""
    qty: float = 1
    unit_price: float = 0
    amount: Optional[float] = None


class RecurringTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    frequency: str = Field("monthly", pattern="^(weekly|monthly|quarterly|yearly)$")
    start_date: Optional[str] = None       # YYYY-MM-DD, default today
    auto_send: bool = False                # auto-email buyer on generation
    invoice_type: str = Field("service", pattern="^(goods|service)$")
    seller_name: Optional[str] = None
    seller_inn: Optional[str] = None
    seller_address: Optional[str] = None
    seller_phone: Optional[str] = None
    seller_bank: Optional[str] = None
    seller_swift: Optional[str] = None
    seller_account: Optional[str] = None
    buyer_inn: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_email: Optional[str] = None
    buyer_address: Optional[str] = None
    buyer_phone: Optional[str] = None
    due_days: int = Field(30, ge=1, le=365)  # payment due N days after invoice_date
    line_items: List[LineItem] = []
    comment: Optional[str] = Field(None, max_length=500)


class RecurringTemplateUpdate(BaseModel):
    name: Optional[str] = None
    frequency: Optional[str] = Field(None, pattern="^(weekly|monthly|quarterly|yearly)$")
    active: Optional[bool] = None
    auto_send: Optional[bool] = None
    buyer_email: Optional[str] = None
    buyer_name: Optional[str] = None
    due_days: Optional[int] = Field(None, ge=1, le=365)
    line_items: Optional[List[LineItem]] = None
    comment: Optional[str] = Field(None, max_length=500)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _next_date(from_date: date, frequency: str) -> date:
    days = _FREQ_DAYS.get(frequency, 30)
    if frequency == "monthly":
        month = from_date.month + 1
        year = from_date.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        try:
            return from_date.replace(year=year, month=month)
        except ValueError:
            return from_date + timedelta(days=30)
    return from_date + timedelta(days=days)


def _generate_invoice_from_template(conn, tenant_id: str, tmpl: dict) -> int:
    """Insert a new outgoing_invoices draft from template. Returns new invoice id."""
    from app.api.services.invoice_creator import create_draft
    today = date.today()
    due = today + timedelta(days=int(tmpl.get("due_days") or 30))
    payload = {
        "invoice_type": tmpl.get("invoice_type") or "service",
        "seller_name": tmpl.get("seller_name"),
        "seller_inn": tmpl.get("seller_inn"),
        "seller_address": tmpl.get("seller_address"),
        "seller_phone": tmpl.get("seller_phone"),
        "seller_bank": tmpl.get("seller_bank"),
        "seller_swift": tmpl.get("seller_swift"),
        "seller_account": tmpl.get("seller_account"),
        "buyer_inn": tmpl.get("buyer_inn"),
        "buyer_name": tmpl.get("buyer_name"),
        "buyer_email": tmpl.get("buyer_email"),
        "buyer_address": tmpl.get("buyer_address"),
        "buyer_phone": tmpl.get("buyer_phone"),
        "invoice_date": str(today),
        "due_date": str(due),
        "line_items": tmpl.get("line_items") or [],
        "comment": tmpl.get("comment"),
    }
    result = create_draft(conn, tenant_id, payload)
    return result["id"]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/templates")
@limiter.limit("20/minute")
def create_template(data: RecurringTemplateCreate, request: Request):
    """Create a recurring invoice template."""
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    _ensure_table(conn)
    cur = conn.cursor()
    try:
        start = date.fromisoformat(data.start_date) if data.start_date else date.today()
        cur.execute("""
            INSERT INTO recurring_invoice_templates (
                tenant_id, name, frequency, next_run_date, active, auto_send,
                invoice_type, seller_name, seller_inn, seller_address, seller_phone,
                seller_bank, seller_swift, seller_account,
                buyer_inn, buyer_name, buyer_email, buyer_address, buyer_phone,
                due_days, line_items, comment
            ) VALUES (
                %s,%s,%s,%s,TRUE,%s,
                %s,%s,%s,%s,%s,
                %s,%s,%s,
                %s,%s,%s,%s,%s,
                %s,%s,%s
            ) RETURNING id
        """, (
            tenant_id, data.name, data.frequency, start, data.auto_send,
            data.invoice_type, data.seller_name, data.seller_inn,
            data.seller_address, data.seller_phone,
            data.seller_bank, data.seller_swift, data.seller_account,
            data.buyer_inn, data.buyer_name, data.buyer_email,
            data.buyer_address, data.buyer_phone,
            data.due_days,
            psycopg2.extras.Json([i.dict() for i in data.line_items]),
            data.comment,
        ))
        new_id = cur.fetchone()[0]
        conn.commit()
        log.info("recurring_template_created id=%s tenant=%s freq=%s", new_id, tenant_id, data.frequency)
        return ok_response("Template created", {"id": new_id, "next_run_date": str(start)})
    except Exception as e:
        conn.rollback()
        return error_response("DB error", "DB_ERROR", str(e))
    finally:
        cur.close(); conn.close()


@router.get("/templates")
@limiter.limit("30/minute")
def list_templates(request: Request, active_only: bool = Query(True)):
    """List recurring invoice templates for this tenant."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    _ensure_table(conn)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cond = "tenant_id = %s" + (" AND active = TRUE" if active_only else "")
        cur.execute(f"""
            SELECT id, name, frequency, next_run_date, last_run_date,
                   active, auto_send, invoice_type, buyer_name, buyer_email,
                   due_days, comment, created_at
            FROM recurring_invoice_templates
            WHERE {cond}
            ORDER BY next_run_date ASC
        """, (tenant_id,))
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            for f in ("next_run_date", "last_run_date", "created_at"):
                if r.get(f):
                    r[f] = str(r[f])[:10]
        return ok_response("Templates", {"templates": rows, "count": len(rows)})
    finally:
        cur.close(); conn.close()


@router.patch("/templates/{tmpl_id}")
def update_template(tmpl_id: int, data: RecurringTemplateUpdate, request: Request):
    """Update a recurring template (deactivate, change frequency, etc.)."""
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor()
    try:
        fields, vals = [], []
        if data.name is not None:       fields.append("name=%s");        vals.append(data.name)
        if data.frequency is not None:  fields.append("frequency=%s");   vals.append(data.frequency)
        if data.active is not None:     fields.append("active=%s");      vals.append(data.active)
        if data.auto_send is not None:  fields.append("auto_send=%s");   vals.append(data.auto_send)
        if data.buyer_email is not None:fields.append("buyer_email=%s"); vals.append(data.buyer_email)
        if data.buyer_name is not None: fields.append("buyer_name=%s");  vals.append(data.buyer_name)
        if data.due_days is not None:   fields.append("due_days=%s");    vals.append(data.due_days)
        if data.comment is not None:    fields.append("comment=%s");     vals.append(data.comment)
        if data.line_items is not None:
            fields.append("line_items=%s")
            vals.append(psycopg2.extras.Json([i.dict() for i in data.line_items]))
        if not fields:
            return ok_response("No changes", {})
        fields.append("updated_at=NOW()")
        vals += [tmpl_id, tenant_id]
        cur.execute(
            f"UPDATE recurring_invoice_templates SET {','.join(fields)} WHERE id=%s AND tenant_id=%s",
            vals,
        )
        if cur.rowcount == 0:
            return http_error(404, "Template not found", "NOT_FOUND")
        conn.commit()
        return ok_response("Template updated", {"id": tmpl_id})
    except Exception as e:
        conn.rollback()
        return error_response("DB error", "DB_ERROR", str(e))
    finally:
        cur.close(); conn.close()


@router.delete("/templates/{tmpl_id}")
def delete_template(tmpl_id: int, request: Request):
    """Deactivate (soft-delete) a recurring template."""
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE recurring_invoice_templates SET active=FALSE, updated_at=NOW() WHERE id=%s AND tenant_id=%s",
            (tmpl_id, tenant_id),
        )
        if cur.rowcount == 0:
            return http_error(404, "Template not found", "NOT_FOUND")
        conn.commit()
        return ok_response("Template deactivated", {"id": tmpl_id})
    finally:
        cur.close(); conn.close()


@router.post("/run")
@limiter.limit("10/minute")
def run_recurring(
    request: Request,
    dry_run: bool = Query(False, description="If true, show what would be generated without creating"),
):
    """
    Generate invoices for all due recurring templates (next_run_date <= today).
    Call this endpoint daily (e.g. from a Cloud Scheduler job or cron).
    If auto_send=True on template, emails the buyer automatically.
    """
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    today = date.today()

    conn = get_db()
    _ensure_table(conn)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT * FROM recurring_invoice_templates
            WHERE tenant_id = %s AND active = TRUE AND next_run_date <= %s
            ORDER BY next_run_date ASC
            LIMIT 50
        """, (tenant_id, today))
        due = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()

    generated, errors = [], []

    for tmpl in due:
        if dry_run:
            generated.append({
                "template_id": tmpl["id"],
                "name": tmpl["name"],
                "buyer": tmpl.get("buyer_name"),
                "would_run": str(tmpl["next_run_date"]),
            })
            continue
        try:
            inv_id = _generate_invoice_from_template(conn, tenant_id, tmpl)
            next_run = _next_date(tmpl["next_run_date"], tmpl["frequency"])
            cur2 = conn.cursor()
            cur2.execute("""
                UPDATE recurring_invoice_templates
                SET last_run_date=%s, next_run_date=%s, updated_at=NOW()
                WHERE id=%s
            """, (today, next_run, tmpl["id"]))
            conn.commit()
            cur2.close()

            # auto-send email if configured
            if tmpl.get("auto_send") and tmpl.get("buyer_email"):
                try:
                    from app.api.services.invoice_creator import _calc_totals
                    items = tmpl.get("line_items") or []
                    if isinstance(items, str):
                        import json as _json
                        items = _json.loads(items)
                    totals = _calc_totals(items)
                    due_str = str(today + timedelta(days=int(tmpl.get("due_days") or 30)))
                    _send_invoice_email(
                        to_email=tmpl["buyer_email"],
                        buyer_name=tmpl.get("buyer_name") or "",
                        seller_name=tmpl.get("seller_name") or "",
                        invoice_id=inv_id,
                        due_date=due_str,
                        total=totals["total_amount"],
                    )
                    log.info("recurring_auto_sent invoice=%s email=%s", inv_id, tmpl["buyer_email"])
                except Exception as email_err:
                    log.warning("recurring auto_send failed invoice=%s: %s", inv_id, email_err)

            generated.append({
                "template_id": tmpl["id"],
                "name": tmpl["name"],
                "invoice_id": inv_id,
                "next_run_date": str(next_run),
            })
            log.info("recurring_generated tmpl=%s invoice=%s tenant=%s", tmpl["id"], inv_id, tenant_id)
        except Exception as e:
            log.error("recurring_run failed tmpl=%s: %s", tmpl["id"], e)
            errors.append({"template_id": tmpl["id"], "name": tmpl["name"], "error": str(e)})

    conn.close()
    return ok_response("Recurring run complete", {
        "dry_run": dry_run,
        "generated_count": len(generated),
        "error_count": len(errors),
        "generated": generated,
        "errors": errors,
    })
