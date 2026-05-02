"""Outgoing invoice routes — create, auto-save, finalize, list, PDF download."""
import logging
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel, Field
from typing import Optional, List

from app.api.tenant_context import resolve_tenant_id
from app.api.response_utils import ok_response, error_response, http_error
from app.api.db import get_db
from app.api.security import limiter
from app.api.services.invoice_creator import (
    create_draft, update_draft, finalize, list_invoices
)

router = APIRouter(prefix="/outgoing", tags=["outgoing"])
log = logging.getLogger(__name__)


class LineItem(BaseModel):
    description: str = ""
    qty: float = 1
    unit_price: float = 0
    amount: Optional[float] = None


class InvoiceCreateRequest(BaseModel):
    invoice_type: str = Field(..., pattern="^(goods|service)$")
    buyer_inn: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_email: Optional[str] = None
    transport_from: Optional[str] = None
    transport_to: Optional[str] = None
    vehicle_number: Optional[str] = None
    driver_name: Optional[str] = None
    line_items: List[LineItem] = []
    comment: Optional[str] = Field(None, max_length=500)


class InvoiceUpdateRequest(BaseModel):
    buyer_inn: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_email: Optional[str] = None
    transport_from: Optional[str] = None
    transport_to: Optional[str] = None
    vehicle_number: Optional[str] = None
    driver_name: Optional[str] = None
    line_items: Optional[List[LineItem]] = None
    comment: Optional[str] = Field(None, max_length=500)


@router.post("/drafts")
@limiter.limit("30/minute")
def create_invoice_draft(data: InvoiceCreateRequest, request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db(tenant_id)
    try:
        result = create_draft(
            conn, tenant_id,
            {**data.dict(), "line_items": [i.dict() for i in data.line_items]}
        )
        return ok_response("Draft created", result)
    except ValueError as e:
        return error_response(str(e), "VALIDATION_ERROR")
    except Exception as e:
        log.error("create_draft failed: %s", e)
        return error_response("DB error", "DB_ERROR", str(e))
    finally:
        conn.close()


@router.patch("/drafts/{invoice_id}")
@limiter.limit("60/minute")
def autosave_invoice(invoice_id: int, data: InvoiceUpdateRequest, request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db(tenant_id)
    try:
        payload = {k: v for k, v in data.dict().items() if v is not None}
        if "line_items" in payload:
            payload["line_items"] = [i if isinstance(i, dict) else i.dict() for i in payload["line_items"]]
        result = update_draft(conn, tenant_id, invoice_id, payload)
        return ok_response("Draft updated", result)
    except LookupError as e:
        return http_error(404, str(e), "NOT_FOUND")
    except Exception as e:
        log.error("update_draft failed: %s", e)
        return error_response("DB error", "DB_ERROR", str(e))
    finally:
        conn.close()


@router.post("/drafts/{invoice_id}/finalize")
@limiter.limit("20/minute")
def finalize_invoice(invoice_id: int, request: Request):
    """Generate waybill + tax invoice, assign invoice number, propagate comment."""
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db(tenant_id)
    try:
        result = finalize(conn, tenant_id, invoice_id)
        return ok_response("Invoice finalized", result)
    except LookupError as e:
        return http_error(404, str(e), "NOT_FOUND")
    except ValueError as e:
        return http_error(409, str(e), "CONFLICT")
    except Exception as e:
        log.error("finalize failed tenant=%s id=%s: %s", tenant_id, invoice_id, e)
        return error_response("Finalize failed", "FINALIZE_ERROR", str(e))
    finally:
        conn.close()


@router.get("/list")
@limiter.limit("30/minute")
def list_outgoing_invoices(
    request: Request,
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db(tenant_id)
    try:
        result = list_invoices(conn, tenant_id, status=status, limit=limit, offset=offset)
        return ok_response("Outgoing invoices", result)
    except Exception as e:
        return error_response("DB error", "DB_ERROR", str(e))
    finally:
        conn.close()


@router.get("/{invoice_id}")
def get_invoice(invoice_id: int, request: Request):
    import psycopg2.extras
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db(tenant_id)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """
            SELECT id, invoice_number, invoice_type, status,
                   buyer_inn, buyer_name, buyer_email,
                   transport_from, transport_to, vehicle_number, driver_name,
                   line_items, subtotal, vat_amount, total_amount, comment,
                   generated_waybill_id, generated_tax_invoice_id,
                   created_at, updated_at, finalized_at
            FROM outgoing_invoices
            WHERE id = %s AND tenant_id = %s
            """,
            (invoice_id, tenant_id),
        )
        row = cur.fetchone()
        if not row:
            return http_error(404, "Not found", "NOT_FOUND")
        result = dict(row)
        for dt_field in ("created_at", "updated_at", "finalized_at"):
            if result.get(dt_field):
                result[dt_field] = result[dt_field].isoformat()
        return ok_response("Invoice", result)
    finally:
        cur.close()
        conn.close()


@router.post("/{invoice_id}/send-email")
@limiter.limit("10/minute")
def send_invoice_email(invoice_id: int, request: Request):
    """Generate PDF and email it to buyer_email. Marks invoice as 'sent'."""
    import io, os, json as _json, smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email.mime.text import MIMEText
    from email import encoders

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    if not smtp_user or not smtp_pass:
        return error_response("Email not configured", "SMTP_ERROR", "SMTP_USER / SMTP_PASS env vars missing")

    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT invoice_number, invoice_type, buyer_name, buyer_inn, buyer_email,
                      subtotal, vat_amount, total_amount, comment, line_items, created_at, status
               FROM outgoing_invoices WHERE id = %s AND tenant_id = %s""",
            (invoice_id, tenant_id),
        )
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not row:
        return http_error(404, "Not found", "NOT_FOUND")

    inv_num, inv_type, buyer_name, buyer_inn, buyer_email, subtotal, vat, total, comment, line_items_raw, created_at, status = row
    if not buyer_email:
        return error_response("No buyer email", "VALIDATION_ERROR", "ინვოისზე მყიდველის ელ-ფოსტა არ არის მითითებული")

    # ── Build PDF ────────────────────────────────────────────────────────────
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
    except ImportError:
        return error_response("reportlab not installed", "PDF_ERROR")

    line_items = _json.loads(line_items_raw) if isinstance(line_items_raw, str) else (line_items_raw or [])
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, h - 60, f"Invoice {inv_num or 'DRAFT'}")
    c.setFont("Helvetica", 11)
    c.drawString(50, h - 85, f"Type: {inv_type} | Date: {str(created_at)[:10]}")
    c.drawString(50, h - 105, f"Buyer: {buyer_name or '?'} (INN: {buyer_inn or '?'})")
    y = h - 140
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Description"); c.drawString(320, y, "Qty"); c.drawString(370, y, "Price"); c.drawString(440, y, "Total")
    y -= 15
    c.setFont("Helvetica", 10)
    for item in line_items:
        desc = str(item.get("description", ""))[:45]
        qty = item.get("qty", item.get("quantity", 1))
        price = item.get("unit_price", item.get("price", item.get("amount", 0)))
        amt = float(qty) * float(price)
        c.drawString(50, y, desc); c.drawString(320, y, str(qty)); c.drawString(370, y, f"{float(price):.2f}"); c.drawString(440, y, f"{amt:.2f}")
        y -= 14
        if y < 100:
            c.showPage(); y = h - 60
    y -= 10
    c.setFont("Helvetica-Bold", 10)
    c.drawString(350, y, f"Subtotal: {float(subtotal or 0):.2f} GEL")
    y -= 14; c.drawString(350, y, f"VAT (18%): {float(vat or 0):.2f} GEL")
    y -= 14; c.drawString(350, y, f"TOTAL: {float(total or 0):.2f} GEL")
    if comment:
        y -= 20; c.setFont("Helvetica", 9); c.drawString(50, y, f"Note: {comment[:100]}")
    c.save()
    buf.seek(0)
    pdf_bytes = buf.read()

    # ── Send email ───────────────────────────────────────────────────────────
    try:
        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = buyer_email
        msg["Subject"] = f"ინვოისი {inv_num or ''} — {buyer_name or ''}"
        body = (
            f"გამარჯობა,\n\n"
            f"გთხოვთ იხილოთ თანდართული ინვოისი {inv_num or ''}.\n"
            f"ჯამი: {float(total or 0):.2f} GEL\n\n"
            f"პატივისცემით,\nBridge Hub"
        )
        msg.attach(MIMEText(body, "plain", "utf-8"))
        part = MIMEBase("application", "pdf")
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        filename = f"invoice_{inv_num or invoice_id}.pdf"
        part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
        msg.attach(part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, buyer_email, msg.as_string())
    except Exception as e:
        log.error("send_invoice_email failed: %s", e)
        return error_response("Email send failed", "SMTP_ERROR", str(e))

    # ── Mark as sent ─────────────────────────────────────────────────────────
    conn2 = get_db(tenant_id)
    try:
        cur2 = conn2.cursor()
        cur2.execute(
            "UPDATE outgoing_invoices SET status='sent', sent_at=NOW() WHERE id=%s AND tenant_id=%s",
            (invoice_id, tenant_id),
        )
        conn2.commit()
    finally:
        cur2.close()
        conn2.close()

    log.info("action=invoice_emailed tenant=%s id=%s to=%s", tenant_id, invoice_id, buyer_email)
    return ok_response("ინვოისი გაიგზავნა", {"sent_to": buyer_email, "invoice_number": inv_num})


@router.get("/{invoice_id}/pdf")
@limiter.limit("10/minute")
def download_invoice_pdf(invoice_id: int, request: Request):
    """Generate a simple PDF for an outgoing invoice."""
    from fastapi.responses import StreamingResponse
    import io

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT invoice_number, invoice_type, buyer_name, buyer_inn,
                   subtotal, vat_amount, total_amount, comment,
                   line_items, created_at
            FROM outgoing_invoices WHERE id = %s AND tenant_id = %s
            """,
            (invoice_id, tenant_id),
        )
        row = cur.fetchone()
        if not row:
            return http_error(404, "Not found", "NOT_FOUND")
    finally:
        cur.close()
        conn.close()

    inv_num, inv_type, buyer_name, buyer_inn, subtotal, vat, total, comment, line_items_raw, created_at = row

    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4

        import json as _json
        line_items = _json.loads(line_items_raw) if isinstance(line_items_raw, str) else (line_items_raw or [])

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        w, h = A4

        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, h - 60, f"Invoice {inv_num or 'DRAFT'}")
        c.setFont("Helvetica", 11)
        c.drawString(50, h - 85, f"Type: {inv_type} | Date: {str(created_at)[:10]}")
        c.drawString(50, h - 105, f"Buyer: {buyer_name or '?'} (INN: {buyer_inn or '?'})")

        y = h - 140
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, "Description"); c.drawString(320, y, "Qty"); c.drawString(370, y, "Price"); c.drawString(440, y, "Total")
        y -= 15
        c.setFont("Helvetica", 10)
        for item in line_items:
            desc = str(item.get("description",""))[:45]
            qty = item.get("qty", item.get("quantity", 1))
            price = item.get("unit_price", item.get("price", item.get("amount", 0)))
            amt = float(qty) * float(price)
            c.drawString(50, y, desc); c.drawString(320, y, str(qty)); c.drawString(370, y, f"{float(price):.2f}"); c.drawString(440, y, f"{amt:.2f}")
            y -= 14
            if y < 100: c.showPage(); y = h - 60

        y -= 10
        c.setFont("Helvetica-Bold", 10)
        c.drawString(350, y, f"Subtotal: {float(subtotal or 0):.2f} GEL")
        y -= 14; c.drawString(350, y, f"VAT (18%): {float(vat or 0):.2f} GEL")
        y -= 14; c.drawString(350, y, f"TOTAL: {float(total or 0):.2f} GEL")
        if comment:
            y -= 20; c.setFont("Helvetica", 9); c.drawString(50, y, f"Note: {comment[:100]}")

        c.save()
        buf.seek(0)

        filename = f"invoice_{inv_num or invoice_id}.pdf"
        return StreamingResponse(
            buf,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except ImportError:
        return error_response("reportlab not installed", "PDF_ERROR")
    except Exception as e:
        return error_response("PDF generation failed", "PDF_ERROR", str(e))
