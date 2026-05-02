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
    """Generate NSD-style Georgian invoice PDF with colors and styled table."""
    import io, json as _json
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors

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
        for _n, _fp in _paths.items():
            if os.path.exists(_fp):
                try:
                    pdfmetrics.registerFont(TTFont(_n, _fp))
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

    NAVY        = colors.HexColor("#1e3a5f")
    NAVY_LIGHT  = colors.HexColor("#2d5f9e")
    STRIPE      = colors.HexColor("#eef4fb")
    BOX_BG      = colors.HexColor("#dce8f5")
    TOTAL_BG    = colors.HexColor("#d0e4f5")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    ML = 38
    MR = w - 38
    CW = MR - ML

    inv_type = inv.get("invoice_type", "service")

    # ── Large "INVOICE" label top-right ───────────────────────────────────
    c.setFillColor(NAVY)
    c.setFont(FONT_BOLD, 26)
    c.drawRightString(MR, h - 48, "INVOICE")

    # ── Seller info (top-left) ────────────────────────────────────────────
    y = h - 48
    c.setFillColor(colors.black)
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
            y -= 13
            c.drawString(ML, y, lbl + val)

    # ── Three bordered boxes: date | inv# | delivery ──────────────────────
    BH, BW = 34, 93
    box_y0 = h - 60 - BH
    bx0 = MR - 3 * BW
    def _fmt_date(d):
        s = str(d or "")[:10]
        return f"{s[8:10]}.{s[5:7]}.{s[:4]}" if len(s) == 10 and s[4] == "-" else s

    lv_pairs = [
        ("თარიღი",       _fmt_date(inv.get("invoice_date"))),
        ("ინვოისი #",    inv.get("invoice_number") or "DRAFT"),
        ("მიწ. თარიღი",  _fmt_date(inv.get("delivery_date"))),
    ]
    for i, (lbl, val) in enumerate(lv_pairs):
        bx = bx0 + i * BW
        c.setFillColor(BOX_BG)
        c.setStrokeColor(NAVY)
        c.setLineWidth(0.8)
        c.rect(bx, box_y0, BW, BH, fill=1, stroke=1)
        c.setFillColor(NAVY)
        c.setFont(FONT_BOLD, 7.5)
        c.drawCentredString(bx + BW / 2, box_y0 + BH / 2 + 4, lbl)
        c.setFillColor(colors.black)
        c.setFont(FONT_BOLD if i == 1 else FONT, 9)
        c.drawCentredString(bx + BW / 2, box_y0 + 6, val)

    # ── Horizontal rule + title ───────────────────────────────────────────
    sep_y = min(y - 10, box_y0 - 10)
    c.setStrokeColor(NAVY)
    c.setLineWidth(1.4)
    c.line(ML, sep_y, MR, sep_y)

    title_txt = "საქონლის ზედნადები / ინვოისი" if inv_type == "goods" else "მომსახურეობის ინვოისი"
    c.setFillColor(NAVY)
    c.setFont(FONT_BOLD, 11)
    c.drawString(ML, sep_y - 14, title_txt)
    c.setLineWidth(0.5)
    c.line(ML, sep_y - 22, MR, sep_y - 22)

    # ── Buyer bar + details ───────────────────────────────────────────────
    bar_y = sep_y - 40
    c.setFillColor(NAVY)
    c.setStrokeColor(NAVY)
    c.rect(ML, bar_y, CW, 16, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(FONT_BOLD, 9)
    c.drawString(ML + 6, bar_y + 4, "მყიდველი")

    by = bar_y - 13
    c.setFillColor(colors.black)
    c.setFont(FONT_BOLD, 9)
    c.drawString(ML + 4, by, "კომპანია: " + (inv.get("buyer_name") or ""))
    c.setFont(FONT, 9)
    for lbl, key in [
        ("საიდ. კოდი: ", "buyer_inn"),
        ("მისამართი: ",  "buyer_address"),
        ("ტელეფონი: ",   "buyer_phone"),
    ]:
        val = inv.get(key) or ""
        if val:
            by -= 13
            c.drawString(ML + 4, by, lbl + val)

    # ── Items table ───────────────────────────────────────────────────────
    tbl_top = by - 16
    ROW_H = 14
    COL_NUM   = 22
    COL_QTY   = 55
    COL_PRICE = 82
    COL_AMT   = 86
    COL_DESC  = CW - COL_NUM - COL_QTY - COL_PRICE - COL_AMT
    cx = [
        ML,
        ML + COL_NUM,
        ML + COL_NUM + COL_DESC,
        ML + COL_NUM + COL_DESC + COL_QTY,
        ML + COL_NUM + COL_DESC + COL_QTY + COL_PRICE,
    ]
    MIN_ROWS = max(len(line_items), 8)
    tbl_h_total = ROW_H + MIN_ROWS * ROW_H

    # Outer border
    c.setStrokeColor(NAVY)
    c.setLineWidth(0.8)
    c.rect(ML, tbl_top - tbl_h_total, CW, tbl_h_total, fill=0, stroke=1)

    # Header row
    th_y = tbl_top - ROW_H
    c.setFillColor(NAVY)
    c.rect(ML, th_y, CW, ROW_H, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(FONT_BOLD, 8)
    c.drawCentredString(cx[0] + COL_NUM / 2, th_y + 4, "№")
    c.drawCentredString(cx[1] + COL_DESC / 2, th_y + 4, "დასახელება")
    c.drawRightString(cx[2] + COL_QTY - 4, th_y + 4, "რაოდ.")
    c.drawRightString(cx[3] + COL_PRICE - 4, th_y + 4, "ერთ. ფასი")
    c.drawRightString(cx[4] + COL_AMT - 4, th_y + 4, "თანხა (₾)")
    c.setStrokeColor(colors.HexColor("#4a7ab5"))
    c.setLineWidth(0.4)
    for xi in cx[1:]:
        c.line(xi, th_y, xi, th_y + ROW_H)

    # Data rows
    row_y = th_y - ROW_H
    c.setLineWidth(0.25)
    for idx, item in enumerate(line_items):
        if row_y < 130:
            c.showPage(); row_y = h - 60
        if idx % 2 == 1:
            c.setFillColor(STRIPE)
            c.rect(ML + 1, row_y, CW - 2, ROW_H, fill=1, stroke=0)
        desc = str(item.get("description") or "")
        qty   = float(item.get("qty") or item.get("quantity") or 1)
        price = float(item.get("unit_price") or item.get("price") or item.get("amount") or 0)
        amt   = qty * price
        if len(desc) > 44: desc = desc[:43] + "…"
        c.setFillColor(colors.black)
        c.setFont(FONT, 8)
        c.drawCentredString(cx[0] + COL_NUM / 2, row_y + 4, str(idx + 1))
        c.drawString(cx[1] + 3, row_y + 4, desc)
        c.drawRightString(cx[2] + COL_QTY - 4, row_y + 4, f"{qty:g}")
        c.drawRightString(cx[3] + COL_PRICE - 4, row_y + 4, f"{price:.2f}")
        c.drawRightString(cx[4] + COL_AMT - 4, row_y + 4, f"{amt:.2f}")
        c.setStrokeColor(colors.HexColor("#c0d4e8"))
        c.line(ML, row_y, MR, row_y)
        for xi in cx[1:]:
            c.line(xi, row_y, xi, row_y + ROW_H)
        row_y -= ROW_H

    # Empty filler rows
    while row_y > tbl_top - tbl_h_total + ROW_H:
        c.setStrokeColor(colors.HexColor("#ccdde8"))
        c.setLineWidth(0.2)
        c.line(ML, row_y, MR, row_y)
        c.setFillColor(colors.HexColor("#aaaaaa"))
        c.setFont(FONT, 7)
        c.drawRightString(cx[4] + COL_AMT - 4, row_y + 4, "-")
        for xi in cx[1:]:
            c.line(xi, row_y, xi, row_y + ROW_H)
        row_y -= ROW_H

    # ── Totals block ──────────────────────────────────────────────────────
    subtotal = float(inv.get("subtotal") or 0)
    vat      = float(inv.get("vat_amount") or 0)
    total    = float(inv.get("total_amount") or 0)
    tot_y = row_y - 10
    tx = cx[3]

    def _trow(lbl, txt, bold=False):
        nonlocal tot_y
        c.setFillColor(NAVY if bold else colors.black)
        c.setFont(FONT_BOLD if bold else FONT, 9 if not bold else 10)
        c.drawString(tx, tot_y, lbl)
        c.drawRightString(MR, tot_y, txt)
        tot_y -= 14

    _trow("ფასი:", f"{subtotal:.2f} ₾")
    _trow("ფასდაკლება:", "0.00 ₾")
    _trow("სხვაობა:", f"{subtotal:.2f} ₾")
    _trow("დღგ (18%):", f"{vat:.2f} ₾")
    c.setStrokeColor(NAVY)
    c.setLineWidth(0.8)
    c.line(tx, tot_y + 11, MR, tot_y + 11)
    # Total row with background
    c.setFillColor(TOTAL_BG)
    c.rect(tx, tot_y - 3, MR - tx, 16, fill=1, stroke=0)
    _trow("ჯ ა მ ი:", f"{total:.2f} ₾", bold=True)

    # Signature
    sig_y = max(tot_y - 28, 80)
    c.setFillColor(colors.black)
    c.setFont(FONT, 9)
    c.drawString(ML, sig_y, "დირექტორი: _______________________")
    c.drawString(w / 2, sig_y, "ბეჭედი")

    # Comment below signature
    if inv.get("comment"):
        c.setFont(FONT, 8)
        c.drawString(ML, sig_y - 18, f"კომენტარი: {str(inv['comment'])[:120]}")

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
