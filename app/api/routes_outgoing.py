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
    # transport
    transport_from: Optional[str] = None
    transport_to: Optional[str] = None
    vehicle_number: Optional[str] = None
    driver_name: Optional[str] = None
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
            """,
            (invoice_id, tenant_id),
        )
        row = cur.fetchone()
        if not row:
            return http_error(404, "Not found", "NOT_FOUND")
        result = dict(row)
        for dt_field in ("created_at", "updated_at", "finalized_at", "sent_at", "invoice_date", "delivery_date"):
            if result.get(dt_field):
                result[dt_field] = result[dt_field].isoformat() if hasattr(result[dt_field], 'isoformat') else str(result[dt_field])
        return ok_response("Invoice", result)
    finally:
        cur.close()
        conn.close()


def _build_nsd_pdf(inv: dict) -> bytes:
    """Generate NSD-style Georgian invoice PDF. Returns PDF bytes."""
    import io, json as _json
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4

    FONT = "Helvetica"
    FONT_BOLD = "Helvetica-Bold"
    try:
        import os
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        _paths = {
            "DejaVuSans": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "DejaVuSans-Bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        }
        _ok = 0
        for _name, _fp in _paths.items():
            if os.path.exists(_fp):
                try:
                    pdfmetrics.registerFont(TTFont(_name, _fp))
                    _ok += 1
                except Exception:
                    pass
        if _ok == 2:
            FONT = "DejaVuSans"
            FONT_BOLD = "DejaVuSans-Bold"
    except Exception:
        pass

    line_items = inv.get("line_items") or []
    if isinstance(line_items, str):
        line_items = _json.loads(line_items)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    ML = 40
    MR = 555  # right edge

    # ── Seller header ──────────────────────────────────────────────────────
    y = h - 50
    c.setFont(FONT_BOLD, 13)
    c.drawString(ML, y, inv.get("seller_name") or "")
    c.setFont(FONT, 9)
    for lbl, key in [
        ("მისამართი: ", "seller_address"),
        ("საიდ. კოდი: ", "seller_inn"),
        ("ტელ: ", "seller_phone"),
        ("ბანკი: ", "seller_bank"),
        ("SWIFT CODE: ", "seller_swift"),
        ("ა/ა: ", "seller_account"),
    ]:
        val = inv.get(key) or ""
        if val:
            y -= 14
            c.drawString(ML, y, lbl + val)

    # ── Info boxes top-right: date | invoice# | delivery ──────────────────
    box_h, box_w = 36, 90
    box_y = h - 50 - box_h
    box_start_x = MR - 3 * box_w
    labels_vals = [
        ("თარიღი", str(inv.get("invoice_date") or "")[:10]),
        ("ინვოისი №", inv.get("invoice_number") or "DRAFT"),
        ("მიწოდ. თარიღი", str(inv.get("delivery_date") or "")[:10]),
    ]
    for i, (lbl, val) in enumerate(labels_vals):
        bx = box_start_x + i * box_w
        c.rect(bx, box_y, box_w, box_h)
        c.setFont(FONT_BOLD, 7)
        c.drawCentredString(bx + box_w / 2, box_y + box_h / 2 + 4, lbl)
        c.setFont(FONT, 8)
        c.drawCentredString(bx + box_w / 2, box_y + 6, val)

    # ── Title bar ──────────────────────────────────────────────────────────
    title_y = min(y - 20, box_y - 20)
    c.line(ML, title_y + 16, MR, title_y + 16)
    inv_type = inv.get("invoice_type", "service")
    title_txt = "საქონლის ზედნადები / ინვოისი" if inv_type == "goods" else "მომსახურეობის ინვოისი"
    c.setFont(FONT_BOLD, 11)
    c.drawString(ML, title_y + 3, title_txt)
    c.line(ML, title_y - 6, MR, title_y - 6)

    # ── Buyer section ──────────────────────────────────────────────────────
    by = title_y - 22
    c.setFont(FONT_BOLD, 9)
    c.drawString(ML, by, "მყიდველი:")
    c.setFont(FONT, 9)
    c.drawString(ML + 65, by, inv.get("buyer_name") or "")
    for lbl, key in [
        ("  საიდ. კოდი: ", "buyer_inn"),
        ("  მისამართი: ", "buyer_address"),
        ("  ტელ: ", "buyer_phone"),
    ]:
        val = inv.get(key) or ""
        if val:
            by -= 14
            c.drawString(ML, by, lbl + val)

    # ── Items table ────────────────────────────────────────────────────────
    tbl_top = by - 18
    c.line(ML, tbl_top, MR, tbl_top)

    CW = MR - ML
    COL_NUM = 22
    COL_QTY = 50
    COL_PRICE = 75
    COL_AMT = 80
    COL_DESC = CW - COL_NUM - COL_QTY - COL_PRICE - COL_AMT

    cx = [ML, ML + COL_NUM, ML + COL_NUM + COL_DESC,
          ML + COL_NUM + COL_DESC + COL_QTY,
          ML + COL_NUM + COL_DESC + COL_QTY + COL_PRICE]

    th_y = tbl_top - 15
    c.setFont(FONT_BOLD, 8)
    c.drawCentredString(cx[0] + COL_NUM / 2, th_y, "№")
    c.drawString(cx[1] + 3, th_y, "დასახელება")
    c.drawRightString(cx[2] + COL_QTY - 3, th_y, "რაოდ.")
    c.drawRightString(cx[3] + COL_PRICE - 3, th_y, "ერთ. ფასი")
    c.drawRightString(cx[4] + COL_AMT - 3, th_y, "თანხა (₾)")
    c.line(ML, th_y - 5, MR, th_y - 5)

    row_y = th_y - 18
    c.setFont(FONT, 8)
    for idx, item in enumerate(line_items, 1):
        if row_y < 130:
            c.showPage()
            row_y = h - 60
            c.setFont(FONT, 8)
        desc = str(item.get("description") or "")
        qty = float(item.get("qty") or item.get("quantity") or 1)
        price = float(item.get("unit_price") or item.get("price") or item.get("amount") or 0)
        if inv_type == "service":
            qty = 1
            price = float(item.get("amount") or item.get("unit_price") or 0)
        amt = qty * price
        if len(desc) > 40:
            desc = desc[:39] + "…"
        c.drawCentredString(cx[0] + COL_NUM / 2, row_y, str(idx))
        c.drawString(cx[1] + 3, row_y, desc)
        c.drawRightString(cx[2] + COL_QTY - 3, row_y, f"{qty:g}")
        c.drawRightString(cx[3] + COL_PRICE - 3, row_y, f"{price:.2f}")
        c.drawRightString(cx[4] + COL_AMT - 3, row_y, f"{amt:.2f}")
        row_y -= 15
        c.line(ML, row_y + 2, MR, row_y + 2)
        row_y -= 4

    # ── Totals ─────────────────────────────────────────────────────────────
    subtotal = float(inv.get("subtotal") or 0)
    vat = float(inv.get("vat_amount") or 0)
    total = float(inv.get("total_amount") or 0)
    tot_x = cx[3]
    tot_y = row_y - 8

    def _row(lbl, val, bold=False):
        nonlocal tot_y
        c.setFont(FONT_BOLD if bold else FONT, 9)
        c.drawString(tot_x, tot_y, lbl)
        c.drawRightString(MR, tot_y, f"{val:.2f} ₾")
        tot_y -= 14

    _row("ფასი:", subtotal)
    _row("ფასდაკლება:", 0.0)
    _row("სხვაობა:", subtotal)
    _row("დღგ (18%):", vat)
    c.line(tot_x, tot_y + 10, MR, tot_y + 10)
    _row("ჯ ა მ ი:", total, bold=True)

    if inv.get("comment"):
        tot_y -= 8
        c.setFont(FONT, 8)
        c.drawString(ML, tot_y, f"შენიშვნა: {str(inv['comment'])[:120]}")

    sig_y = max(tot_y - 36, 55)
    c.setFont(FONT, 9)
    c.drawString(ML, sig_y, "დირექტორი: _______________________")
    c.drawString(w / 2, sig_y, "ბეჭედი")

    c.save()
    buf.seek(0)
    return buf.read()


@router.post("/{invoice_id}/send-email")
@limiter.limit("10/minute")
def send_invoice_email(invoice_id: int, request: Request):
    """Generate PDF and email it to buyer_email. Marks invoice as 'sent'."""
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
        pdf_bytes = _build_nsd_pdf(inv_data)
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
    """Generate NSD-style PDF for an outgoing invoice."""
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
        pdf_bytes = _build_nsd_pdf(inv_data)
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
