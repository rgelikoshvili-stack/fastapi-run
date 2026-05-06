"""Outgoing invoice routes — create, auto-save, finalize, list, PDF download."""
import logging
from fastapi import APIRouter, Request, Query
from app.api.authz import require_permission
from pydantic import BaseModel, Field
from typing import Optional, List

from app.api.tenant_context import resolve_tenant_id
from app.api.response_utils import ok_response, error_response, http_error
from app.api.db import get_conn, get_db, _q
from app.api.security import limiter
from app.api.services.invoice_creator import (
    create_draft, update_draft, finalize, list_invoices
)
from app.api.services.outgoing_invoice_pdf_service import (
    _load_tenant_signature,
    _load_tenant_stamp,
    _build_nsd_pdf,
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
    # seller (our company)
    seller_name: Optional[str] = None
    seller_inn: Optional[str] = None
    seller_address: Optional[str] = None
    seller_phone: Optional[str] = None
    seller_bank: Optional[str] = None
    seller_swift: Optional[str] = None
    seller_account: Optional[str] = None
    # buyer (client)
    buyer_inn: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_email: Optional[str] = None
    buyer_address: Optional[str] = None
    buyer_phone: Optional[str] = None
    # invoice meta
    invoice_date: Optional[str] = None
    delivery_date: Optional[str] = None
    due_date: Optional[str] = None  # payment due date for reminder system
    # transport
    transport_from: Optional[str] = None
    transport_to: Optional[str] = None
    vehicle_number: Optional[str] = None
    driver_name: Optional[str] = None
    currency: str = Field("GEL", pattern="^(GEL|USD|EUR|GBP|TRY|RUB|CHF)$")
    exchange_rate: Optional[float] = Field(None, gt=0)  # GEL per 1 unit; auto-filled if None
    line_items: List[LineItem] = []
    comment: Optional[str] = Field(None, max_length=500)


class InvoiceUpdateRequest(BaseModel):
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
    invoice_date: Optional[str] = None
    delivery_date: Optional[str] = None
    due_date: Optional[str] = None
    transport_from: Optional[str] = None
    transport_to: Optional[str] = None
    vehicle_number: Optional[str] = None
    driver_name: Optional[str] = None
    currency: Optional[str] = Field(None, pattern="^(GEL|USD|EUR|GBP|TRY|RUB|CHF)$")
    exchange_rate: Optional[float] = Field(None, gt=0)
    line_items: Optional[List[LineItem]] = None
    comment: Optional[str] = Field(None, max_length=500)


@router.post("/drafts")
@limiter.limit("30/minute")
def create_invoice_draft(data: InvoiceCreateRequest, request: Request):
    require_permission(request, "approval:write")
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
    require_permission(request, "approval:write")
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
    require_permission(request, "approval:write")
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
    require_permission(request, "approval:write")
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
async def get_invoice(invoice_id: int, request: Request):
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        row = await conn.fetchrow(_q("""
            SELECT id, invoice_number, invoice_type, status,
                   seller_name, seller_inn, seller_address, seller_phone,
                   seller_bank, seller_swift, seller_account,
                   buyer_inn, buyer_name, buyer_email, buyer_address, buyer_phone,
                   invoice_date, delivery_date,
                   transport_from, transport_to, vehicle_number, driver_name,
                   line_items, subtotal, vat_amount, total_amount, comment,
                   generated_waybill_id, generated_tax_invoice_id,
                   created_at, updated_at, finalized_at, sent_at
            FROM outgoing_invoices
            WHERE id = %s AND tenant_id = %s
        """), invoice_id, tenant_id)
    if not row:
        return http_error(404, "Not found", "NOT_FOUND")
    result = dict(row)
    for dt_field in ("created_at", "updated_at", "finalized_at", "sent_at", "invoice_date", "delivery_date"):
        if result.get(dt_field):
            result[dt_field] = result[dt_field].isoformat() if hasattr(result[dt_field], 'isoformat') else str(result[dt_field])
    return ok_response("Invoice", result)


@router.post("/{invoice_id}/send-email")
@limiter.limit("10/minute")
def send_invoice_email(invoice_id: int, request: Request):
    """Generate PDF and email it to buyer_email. Marks invoice as 'sent'."""
    require_permission(request, "approval:write")
    import os, smtplib
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
            """SELECT invoice_number, invoice_type,
                      seller_name, seller_inn, seller_address, seller_phone,
                      seller_bank, seller_swift, seller_account,
                      buyer_name, buyer_inn, buyer_email, buyer_address, buyer_phone,
                      invoice_date, delivery_date,
                      subtotal, vat_amount, total_amount, comment, line_items, status
               FROM outgoing_invoices WHERE id = %s AND tenant_id = %s""",
            (invoice_id, tenant_id),
        )
        row = cur.fetchone()
        col_names = [d[0] for d in cur.description]
    finally:
        cur.close()
        conn.close()

    if not row:
        return http_error(404, "Not found", "NOT_FOUND")

    inv_data = dict(zip(col_names, row))
    buyer_email = inv_data.get("buyer_email") or ""
    if not buyer_email:
        return error_response("No buyer email", "VALIDATION_ERROR", "ინვოისზე შემკვეთის ელ-ფოსტა არ არის მითითებული")

    # ── Build PDF ─────────────────────────────────────────────────────────────
    try:
        sig_bytes   = _load_tenant_signature(tenant_id)
        stamp_bytes = _load_tenant_stamp(tenant_id)
        pdf_bytes   = _build_nsd_pdf(inv_data, signature_bytes=sig_bytes, stamp_bytes=stamp_bytes)
    except ImportError:
        return error_response("reportlab not installed", "PDF_ERROR")
    except Exception as _pdf_e:
        return error_response("PDF generation failed", "PDF_ERROR", str(_pdf_e))

    inv_num = inv_data.get("invoice_number") or ""
    buyer_name = inv_data.get("buyer_name") or ""
    total = float(inv_data.get("total_amount") or 0)

    # ── Send email ───────────────────────────────────────────────────────────
    try:
        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = buyer_email
        msg["Subject"] = f"ინვოისი {inv_num or ''} — {buyer_name or ''}"
        body = (
            f"გამარჯობა,\n\n"
            f"გთხოვთ იხილოთ თანდართული ინვოისი {inv_num}.\n"
            f"ჯამი: {total:.2f} GEL\n\n"
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
    cur2 = conn2.cursor()
    try:
        cur2.execute(
            "UPDATE outgoing_invoices SET status='sent', sent_at=NOW() WHERE id=%s AND tenant_id=%s",
            (invoice_id, tenant_id),
        )
        conn2.commit()
    except Exception as _upd_e:
        log.warning("sent-status update failed (non-critical, email was delivered): %s", _upd_e)
        conn2.rollback()
    finally:
        cur2.close()
        conn2.close()

    log.info("action=invoice_emailed tenant=%s id=%s to=%s", tenant_id, invoice_id, buyer_email)
    return ok_response("ინვოისი გაიგზავნა", {"sent_to": buyer_email, "invoice_number": inv_num})


@router.get("/{invoice_id}/pdf")
@limiter.limit("10/minute")
def download_invoice_pdf(invoice_id: int, request: Request):
    """Generate NSD-style PDF for an outgoing invoice."""
    require_permission(request, "approval:write")
    import io, psycopg2.extras
    from fastapi.responses import StreamingResponse

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db(tenant_id)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """
            SELECT invoice_number, invoice_type,
                   seller_name, seller_inn, seller_address, seller_phone,
                   seller_bank, seller_swift, seller_account,
                   buyer_name, buyer_inn, buyer_address, buyer_phone,
                   invoice_date, delivery_date,
                   subtotal, vat_amount, total_amount, comment, line_items
            FROM outgoing_invoices WHERE id = %s AND tenant_id = %s
            """,
            (invoice_id, tenant_id),
        )
        row = cur.fetchone()
        if not row:
            return http_error(404, "Not found", "NOT_FOUND")
        inv_data = dict(row)
    finally:
        cur.close()
        conn.close()

    try:
        sig_bytes   = _load_tenant_signature(tenant_id)
        stamp_bytes = _load_tenant_stamp(tenant_id)
        pdf_bytes   = _build_nsd_pdf(inv_data, signature_bytes=sig_bytes, stamp_bytes=stamp_bytes)
        filename = f"invoice_{inv_data.get('invoice_number') or invoice_id}.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except ImportError:
        return error_response("reportlab not installed", "PDF_ERROR")
    except Exception as e:
        return error_response("PDF generation failed", "PDF_ERROR", str(e))
