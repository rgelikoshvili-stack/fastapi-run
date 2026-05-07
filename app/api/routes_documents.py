"""app/api/routes_documents.py
Document upload + intelligence pipeline:
  parse → extract → resolve party → classify operation → build journal

Triangle document endpoints:
  POST /documents/upload-waybill
  POST /documents/upload-tax-invoice
  POST /documents/upload-commercial-invoice
"""
import asyncio
import hashlib
import logging
from fastapi import APIRouter, UploadFile, File, Request, Query

from app.api.tenant_context import resolve_tenant_id
from app.api.response_utils import ok_response, error_response, http_error
from app.api.db import get_conn, _q
from app.api.security import limiter
from app.api.services.storage_service import upload_file as gcs_upload, safe_download
from app.api.metrics import FILE_PREVIEW_DURATION
from app.api.authz import require_permission
from app.api.services.document_processing_service import (
    _dec_or_none,
    _parse_date,
    _extract_from_file,
    _try_match_triangle,
    _also_queue_for_pipeline,
    _refresh_related_drafts,
    _process_document_background,
)

router = APIRouter(prefix="/documents", tags=["documents"])
log = logging.getLogger(__name__)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/upload")
@limiter.limit("10/minute")
async def upload_document(file: UploadFile = File(...), request: Request = None):
    require_permission(request, "ocr:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None) if request else None)

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        return http_error(413, "File too large (max 10MB)", "FILE_TOO_LARGE")

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    mime_type = file.content_type or "application/pdf"

    # ── 1. Dedup by file hash ──────────────────────────────────────────────
    async with get_conn() as conn:
        existing_file = await conn.fetchrow(_q(
            "SELECT id, (file_content IS NOT NULL OR gcs_path IS NOT NULL) AS has_content "
            "FROM processed_documents WHERE tenant_id = %s AND file_hash = %s"
        ), tenant_id, file_hash)

    if existing_file and existing_file["has_content"]:
        doc_id_existing = existing_file["id"]
        async with get_conn() as conn:
            existing_draft = await conn.fetchrow(_q(
                "SELECT id, status FROM journal_drafts "
                "WHERE source_document_id = %s AND tenant_id = %s ORDER BY id DESC LIMIT 1"
            ), doc_id_existing, tenant_id)

        _terminal = {'rejected', 'posted', 'auto_approved'}
        draft_is_terminal = (existing_draft is None) or (existing_draft["status"] in _terminal)

        if not draft_is_terminal:
            return ok_response("Duplicate file", {
                "status": "duplicate_file",
                "message": "ეს ფაილი უკვე ატვირთულია",
                "existing_draft_id": existing_draft["id"] if existing_draft else None,
            })
        asyncio.create_task(
            _process_document_background(doc_id_existing, tenant_id, file_bytes, mime_type, file.filename or "document")
        )
        return ok_response("Re-processing file", {
            "status": "reprocessing",
            "message": "ფაილი ხელახლა მუშავდება",
            "doc_id": doc_id_existing,
        })

    if existing_file and not existing_file["has_content"]:
        doc_id = existing_file["id"]
        gcs_path = gcs_upload(file_bytes, file.filename or "document", mime_type, tenant_id)
        async with get_conn() as conn:
            if gcs_path:
                await conn.execute(_q(
                    "UPDATE processed_documents SET gcs_path = %s WHERE id = %s AND tenant_id = %s"
                ), gcs_path, doc_id, tenant_id)
            else:
                await conn.execute(_q(
                    "UPDATE processed_documents SET file_content = %s WHERE id = %s AND tenant_id = %s"
                ), file_bytes, doc_id, tenant_id)
        log.info("action=doc_content_patched doc_id=%s tenant=%s", doc_id, tenant_id)
        async with get_conn() as conn:
            existing_draft = await conn.fetchrow(_q(
                "SELECT id, status FROM journal_drafts "
                "WHERE source_document_id = %s AND tenant_id = %s LIMIT 1"
            ), doc_id, tenant_id)
        return ok_response("File content restored", {
            "status": "content_restored",
            "message": "ფაილის შინაარსი განახლდა — 👁 ღილაკი ახლა მუშაობს",
            "doc_id": doc_id,
            "existing_draft_id": existing_draft["id"] if existing_draft else None,
        })

    # ── 2. Upload to GCS (or fall back to DB storage if GCS not configured) ──
    gcs_path = gcs_upload(file_bytes, file.filename or "document", mime_type, tenant_id)

    try:
        async with get_conn() as conn:
            if gcs_path:
                doc_id = await conn.fetchval(_q("""
                    INSERT INTO processed_documents
                        (tenant_id, file_hash, file_name, file_size_bytes, mime_type, gcs_path, status)
                    VALUES (%s, %s, %s, %s, %s, %s, 'processing')
                    RETURNING id
                """), tenant_id, file_hash, file.filename, len(file_bytes), mime_type, gcs_path)
            else:
                doc_id = await conn.fetchval(_q("""
                    INSERT INTO processed_documents
                        (tenant_id, file_hash, file_name, file_size_bytes, mime_type, file_content, status)
                    VALUES (%s, %s, %s, %s, %s, %s, 'processing')
                    RETURNING id
                """), tenant_id, file_hash, file.filename, len(file_bytes), mime_type, file_bytes)
    except Exception as e:
        log.error("processed_documents insert failed: %s", e)
        return error_response("DB error", "DB_ERROR", str(e))

    # ── 3. Fire background processing — return immediately ─────────────────
    asyncio.create_task(
        _process_document_background(doc_id, tenant_id, file_bytes, mime_type, file.filename or "document")
    )

    log.info("action=document_queued tenant=%s doc_id=%s", tenant_id, doc_id)

    return ok_response("Document queued for processing", {
        "status": "processing",
        "doc_id": doc_id,
        "message": "დოკუმენტი მუშავდება ფონზე — approval queue-ში გამოჩნდება რამდენიმე წამში",
    })


# ── Upload Waybill ────────────────────────────────────────────────────────────

@router.post("/upload-waybill")
@limiter.limit("20/minute")
async def upload_waybill(file: UploadFile = File(...), request: Request = None):
    """Upload a waybill (ზედნადები). Extracts fields + attempts triangle match."""
    require_permission(request, "ocr:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None) if request else None)

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        return http_error(413, "File too large (max 10MB)", "FILE_TOO_LARGE")

    mime_type = file.content_type or "application/pdf"
    parsed, extracted = await _extract_from_file(file_bytes, mime_type)

    doc = {
        "waybill_number": extracted.document_number or "",
        "waybill_date": _parse_date(extracted.issue_date),
        "seller_inn": extracted.seller.inn,
        "seller_name": extracted.seller.name,
        "buyer_inn": extracted.buyer.inn,
        "buyer_name": extracted.buyer.name,
        "subtotal": _dec_or_none(extracted.net_amount),
        "vat_amount": _dec_or_none(extracted.total_vat),
        "total_amount": _dec_or_none(extracted.total_with_vat),
        "raw_text": (parsed.get("text") or "")[:5000],
    }

    try:
        async with get_conn() as conn:
            waybill_id = await conn.fetchval(_q("""
                INSERT INTO waybills
                    (tenant_id, waybill_number, waybill_date, seller_inn, seller_name,
                     buyer_inn, buyer_name, subtotal, vat_amount, total_amount,
                     status, raw_text, version)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'imported',%s,1)
                RETURNING id
            """),
                tenant_id, doc["waybill_number"], doc["waybill_date"],
                doc["seller_inn"], doc["seller_name"],
                doc["buyer_inn"], doc["buyer_name"],
                doc["subtotal"], doc["vat_amount"], doc["total_amount"],
                doc["raw_text"],
            )
    except Exception as e:
        return error_response("DB error saving waybill", "DB_ERROR", str(e))

    match_info = await _try_match_triangle(tenant_id, "waybill", waybill_id, doc)
    await _refresh_related_drafts(tenant_id, doc.get("seller_inn"), doc.get("buyer_inn"))
    await _also_queue_for_pipeline(tenant_id, file_bytes, mime_type, file.filename or "waybill.pdf")

    log.info("action=waybill_uploaded tenant=%s id=%s num=%s",
             tenant_id, waybill_id, doc["waybill_number"])

    return ok_response("Waybill uploaded", {
        "waybill_id": waybill_id,
        "waybill_number": doc["waybill_number"],
        "extracted": extracted.dict(),
        "triangle_match": match_info,
        "extraction_method": parsed.get("method"),
    })


# ── Upload Tax Invoice ────────────────────────────────────────────────────────

@router.post("/upload-tax-invoice")
@limiter.limit("20/minute")
async def upload_tax_invoice(file: UploadFile = File(...), request: Request = None):
    """Upload a tax invoice (საგადასახადო ანგარიშ-ფაქტურა)."""
    require_permission(request, "ocr:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None) if request else None)

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        return http_error(413, "File too large (max 10MB)", "FILE_TOO_LARGE")

    mime_type = file.content_type or "application/pdf"
    parsed, extracted = await _extract_from_file(file_bytes, mime_type)

    doc = {
        "invoice_number": extracted.document_number or "",
        "invoice_series": extracted.document_series or "",
        "invoice_date": _parse_date(extracted.issue_date),
        "seller_inn": extracted.seller.inn,
        "seller_name": extracted.seller.name,
        "buyer_inn": extracted.buyer.inn,
        "buyer_name": extracted.buyer.name,
        "subtotal": _dec_or_none(extracted.net_amount),
        "vat_amount": _dec_or_none(extracted.total_vat),
        "total_amount": _dec_or_none(extracted.total_with_vat),
        "raw_text": (parsed.get("text") or "")[:5000],
    }

    try:
        async with get_conn() as conn:
            ti_id = await conn.fetchval(_q("""
                INSERT INTO tax_invoices
                    (tenant_id, invoice_number, invoice_series, invoice_date,
                     seller_inn, seller_name, buyer_inn, buyer_name,
                     subtotal, vat_amount, total_amount, status, raw_text)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'imported',%s)
                RETURNING id
            """),
                tenant_id, doc["invoice_number"], doc["invoice_series"], doc["invoice_date"],
                doc["seller_inn"], doc["seller_name"],
                doc["buyer_inn"], doc["buyer_name"],
                doc["subtotal"], doc["vat_amount"], doc["total_amount"],
                doc["raw_text"],
            )
    except Exception as e:
        return error_response("DB error saving tax invoice", "DB_ERROR", str(e))

    match_info = await _try_match_triangle(tenant_id, "tax_invoice", ti_id, doc)
    await _refresh_related_drafts(tenant_id, doc.get("seller_inn"), doc.get("buyer_inn"))
    await _also_queue_for_pipeline(tenant_id, file_bytes, mime_type, file.filename or "tax_invoice.pdf")

    log.info("action=tax_invoice_uploaded tenant=%s id=%s num=%s",
             tenant_id, ti_id, doc["invoice_number"])

    return ok_response("Tax invoice uploaded", {
        "tax_invoice_id": ti_id,
        "invoice_number": doc["invoice_number"],
        "extracted": extracted.dict(),
        "triangle_match": match_info,
        "extraction_method": parsed.get("method"),
    })


# ── Upload Commercial Invoice ─────────────────────────────────────────────────

@router.post("/upload-commercial-invoice")
@limiter.limit("20/minute")
async def upload_commercial_invoice(file: UploadFile = File(...), request: Request = None):
    """Upload a commercial invoice (ანგარიში)."""
    require_permission(request, "ocr:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None) if request else None)

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        return http_error(413, "File too large (max 10MB)", "FILE_TOO_LARGE")

    mime_type = file.content_type or "application/pdf"
    parsed, extracted = await _extract_from_file(file_bytes, mime_type)

    doc = {
        "invoice_number": extracted.document_number or "",
        "invoice_date": _parse_date(extracted.issue_date),
        "seller_inn": extracted.seller.inn,
        "seller_name": extracted.seller.name,
        "buyer_inn": extracted.buyer.inn,
        "buyer_name": extracted.buyer.name,
        "subtotal": _dec_or_none(extracted.net_amount),
        "vat_amount": _dec_or_none(extracted.total_vat),
        "total_amount": _dec_or_none(extracted.total_with_vat),
        "raw_text": (parsed.get("text") or "")[:5000],
    }

    try:
        async with get_conn() as conn:
            ci_id = await conn.fetchval(_q("""
                INSERT INTO commercial_invoices
                    (tenant_id, invoice_number, invoice_date,
                     seller_inn, seller_name, buyer_inn, buyer_name,
                     subtotal, vat_amount, total_amount, status, raw_text)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'imported',%s)
                RETURNING id
            """),
                tenant_id, doc["invoice_number"], doc["invoice_date"],
                doc["seller_inn"], doc["seller_name"],
                doc["buyer_inn"], doc["buyer_name"],
                doc["subtotal"], doc["vat_amount"], doc["total_amount"],
                doc["raw_text"],
            )
    except Exception as e:
        return error_response("DB error saving commercial invoice", "DB_ERROR", str(e))

    match_info = await _try_match_triangle(tenant_id, "commercial_invoice", ci_id, doc)
    await _refresh_related_drafts(tenant_id, doc.get("seller_inn"), doc.get("buyer_inn"))
    await _also_queue_for_pipeline(tenant_id, file_bytes, mime_type, file.filename or "commercial_invoice.pdf")

    log.info("action=commercial_invoice_uploaded tenant=%s id=%s num=%s",
             tenant_id, ci_id, doc["invoice_number"])

    return ok_response("Commercial invoice uploaded", {
        "commercial_invoice_id": ci_id,
        "invoice_number": doc["invoice_number"],
        "extracted": extracted.dict(),
        "triangle_match": match_info,
        "extraction_method": parsed.get("method"),
    })


# ── Triangle match status ─────────────────────────────────────────────────────

@router.get("/triangle-matches")
async def list_triangle_matches(
    request: Request,
    status: str = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List triangle matches for tenant, optionally filtered by match_status."""
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    where = "WHERE tenant_id = %s"
    params: list = [tenant_id]
    if status:
        where += " AND match_status = %s"
        params.append(status)
    async with get_conn() as conn:
        rows = [dict(r) for r in await conn.fetch(_q(f"""
            SELECT id, waybill_id, tax_invoice_id, commercial_invoice_id,
                   match_score, match_status, mismatch_fields,
                   waybill_total, tax_invoice_total, commercial_invoice_total,
                   amount_diff, matched_at
            FROM triangle_matches {where}
            ORDER BY matched_at DESC LIMIT %s OFFSET %s
        """), *params, limit, offset)]
        total = await conn.fetchval(_q(f"SELECT COUNT(*) FROM triangle_matches {where}"), *params) or 0

    return ok_response("Triangle matches", {
        "total": total, "limit": limit, "offset": offset, "items": rows
    })


# ── Waybills list ─────────────────────────────────────────────────────────────

@router.get("/waybills")
async def list_waybills(
    request: Request,
    q: str = Query(None),
    status: str = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List waybills with triangle-match status joined."""
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conditions = ["w.tenant_id = %s"]
    params: list = [tenant_id]
    if status:
        conditions.append("w.status = %s")
        params.append(status)
    if q:
        conditions.append(
            "(w.waybill_number ILIKE %s OR w.seller_inn ILIKE %s"
            " OR w.buyer_inn ILIKE %s OR w.seller_name ILIKE %s OR w.buyer_name ILIKE %s)"
        )
        like = f"%{q}%"
        params += [like, like, like, like, like]
    where = "WHERE " + " AND ".join(conditions)
    async with get_conn() as conn:
        rows = [dict(r) for r in await conn.fetch(_q(f"""
            SELECT w.id, w.waybill_number, w.seller_inn, w.seller_name,
                   w.buyer_inn, w.buyer_name, w.waybill_date,
                   w.subtotal, w.vat_amount, w.total_amount,
                   w.transport_from, w.transport_to,
                   w.status, w.version, w.original_waybill_id, w.notes,
                   w.created_at,
                   tm.match_status, tm.match_score,
                   tm.tax_invoice_id, tm.commercial_invoice_id, tm.id AS match_id
            FROM waybills w
            LEFT JOIN triangle_matches tm
              ON tm.waybill_id = w.id AND tm.tenant_id = w.tenant_id
            {where}
            ORDER BY w.created_at DESC
            LIMIT %s OFFSET %s
        """), *params, limit, offset)]
        total = await conn.fetchval(_q(f"SELECT COUNT(*) FROM waybills w {where}"), *params) or 0

    return ok_response("Waybills", {"total": total, "limit": limit, "offset": offset, "items": rows})


# ── Tax invoices list ─────────────────────────────────────────────────────────

@router.get("/tax-invoices")
async def list_tax_invoices(
    request: Request,
    q: str = Query(None),
    status: str = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List tax invoices with optional waybill link status."""
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conditions = ["ti.tenant_id = %s"]
    params: list = [tenant_id]
    if status:
        conditions.append("ti.status = %s")
        params.append(status)
    if q:
        conditions.append(
            "(ti.invoice_number ILIKE %s OR ti.seller_inn ILIKE %s"
            " OR ti.buyer_inn ILIKE %s OR ti.seller_name ILIKE %s OR ti.buyer_name ILIKE %s)"
        )
        like = f"%{q}%"
        params += [like, like, like, like, like]
    where = "WHERE " + " AND ".join(conditions)
    async with get_conn() as conn:
        rows = [dict(r) for r in await conn.fetch(_q(f"""
            SELECT ti.id, ti.invoice_number, ti.seller_inn, ti.seller_name,
                   ti.buyer_inn, ti.buyer_name, ti.invoice_date,
                   ti.subtotal, ti.vat_amount, ti.total_amount,
                   ti.related_waybill_number, ti.related_waybill_id,
                   ti.status, ti.notes, ti.created_at,
                   tm.match_status, tm.match_score, tm.id AS match_id
            FROM tax_invoices ti
            LEFT JOIN triangle_matches tm
              ON tm.tax_invoice_id = ti.id AND tm.tenant_id = ti.tenant_id
            {where}
            ORDER BY ti.created_at DESC
            LIMIT %s OFFSET %s
        """), *params, limit, offset)]
        total = await conn.fetchval(_q(f"SELECT COUNT(*) FROM tax_invoices ti {where}"), *params) or 0

    return ok_response("Tax invoices", {"total": total, "limit": limit, "offset": offset, "items": rows})


# ─────────────────────────────────────────────────────────────
# Tax invoice email sending
# ─────────────────────────────────────────────────────────────

from pydantic import BaseModel as _BaseModel

class _TIEmailReq(_BaseModel):
    email: str

@router.post("/tax-invoice/{invoice_id}/send-email")
@limiter.limit("10/minute")
async def send_tax_invoice_email(invoice_id: int, data: _TIEmailReq, request: Request):
    """Generate a PDF for a tax invoice and email it."""
    require_permission(request, "ocr:write")
    import io, os, smtplib, json as _json
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email.mime.text import MIMEText
    from email import encoders

    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    if not smtp_user or not smtp_pass:
        return error_response("Email not configured", "SMTP_ERROR", "SMTP_USER / SMTP_PASS env vars missing")

    recipient = (data.email or "").strip()
    if not recipient or "@" not in recipient:
        return error_response("Invalid email", "VALIDATION_ERROR", "სწორი ელ-ფოსტა შეიყვანეთ")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        inv = await conn.fetchrow(_q(
            "SELECT * FROM tax_invoices WHERE id = %s AND tenant_id = %s"
        ), invoice_id, tenant_id)

    if not inv:
        return http_error(404, "Not found", "NOT_FOUND")
    inv = dict(inv)

    # ── Build PDF ─────────────────────────────────────────────
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
    except ImportError:
        return error_response("reportlab not installed", "PDF_ERROR")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, h - 55, f"Tax Invoice {inv.get('invoice_number') or '#' + str(invoice_id)}")
    c.setFont("Helvetica", 11)
    c.drawString(50, h - 80, f"Date: {str(inv.get('invoice_date') or inv.get('created_at') or '')[:10]}")
    c.drawString(50, h - 98, f"Seller:  {inv.get('seller_name') or '—'}  (INN: {inv.get('seller_inn') or '—'})")
    c.drawString(50, h - 116, f"Buyer:   {inv.get('buyer_name') or '—'}  (INN: {inv.get('buyer_inn') or '—'})")
    y = h - 150
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Subtotal:"); c.drawString(200, y, f"{float(inv.get('subtotal') or 0):.2f} GEL")
    y -= 16
    c.drawString(50, y, "VAT (18%):"); c.drawString(200, y, f"{float(inv.get('vat_amount') or 0):.2f} GEL")
    y -= 16
    c.drawString(50, y, "TOTAL:"); c.drawString(200, y, f"{float(inv.get('total_amount') or 0):.2f} GEL")
    if inv.get("related_waybill_number"):
        y -= 20
        c.setFont("Helvetica", 9)
        c.drawString(50, y, f"Waybill: {inv['related_waybill_number']}")
    if inv.get("notes"):
        y -= 16
        c.setFont("Helvetica", 9)
        c.drawString(50, y, f"Notes: {str(inv['notes'])[:100]}")
    c.save()
    buf.seek(0)
    pdf_bytes = buf.read()

    # ── Send email ────────────────────────────────────────────
    try:
        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = recipient
        inv_num = inv.get("invoice_number") or f"#{invoice_id}"
        msg["Subject"] = f"Tax Invoice {inv_num}"
        body = (
            f"Please find the attached tax invoice {inv_num}.\n"
            f"Total: {float(inv.get('total_amount') or 0):.2f} GEL\n\n"
            f"Bridge Hub"
        )
        msg.attach(MIMEText(body, "plain", "utf-8"))
        part = MIMEBase("application", "pdf")
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="tax_invoice_{inv_num}.pdf"')
        msg.attach(part)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, recipient, msg.as_string())
    except Exception as e:
        log.error("send_tax_invoice_email failed: %s", e)
        return error_response("Email send failed", "SMTP_ERROR", str(e))

    log.info("action=tax_invoice_emailed tenant=%s id=%s to=%s", tenant_id, invoice_id, recipient)
    return ok_response("ინვოისი გაიგზავნა", {"sent_to": recipient, "invoice_number": inv_num})


# ─────────────────────────────────────────────────────────────
# Original file preview endpoint
# ─────────────────────────────────────────────────────────────

@router.get("/{doc_id}")
async def get_document_meta(doc_id: int, request: Request = None):
    """Return extracted metadata for a processed document (no file bytes)."""
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None) if request else None)
    async with get_conn() as conn:
        row = await conn.fetchrow(_q(
            """SELECT id, file_name, mime_type, file_size_bytes, extraction_method,
                      raw_text, extracted_data, created_at
               FROM processed_documents WHERE id = %s AND tenant_id = %s"""
        ), doc_id, tenant_id)

    if not row:
        return http_error(404, "Document not found", "NOT_FOUND")

    import json as _json
    extracted_data = row["extracted_data"]
    extracted = {}
    if extracted_data:
        try:
            extracted = _json.loads(extracted_data) if isinstance(extracted_data, str) else extracted_data
        except Exception:
            extracted = {}

    return ok_response("Document metadata", {
        "id": row["id"],
        "file_name": row["file_name"],
        "mime_type": row["mime_type"],
        "file_size_bytes": row["file_size_bytes"],
        "extraction_method": row["extraction_method"],
        "extracted": extracted,
        "created_at": str(row["created_at"]) if row["created_at"] else None,
    })


@router.get("/{doc_id}/file")
async def get_document_file(doc_id: int, request: Request = None):
    """Serve the original uploaded file bytes for invoice/document preview."""
    import time
    from fastapi.responses import Response
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None) if request else None)
    async with get_conn() as conn:
        row = await conn.fetchrow(_q(
            "SELECT file_name, mime_type, gcs_path, file_content FROM processed_documents "
            "WHERE id = %s AND tenant_id = %s"
        ), doc_id, tenant_id)

    if not row:
        return http_error(404, "Document not found", "NOT_FOUND")

    file_name = row["file_name"]
    mime_type = row["mime_type"]
    gcs_path = row["gcs_path"]
    file_content = row["file_content"]

    _t0 = time.time()
    content = safe_download(gcs_path, file_content)
    method = "gcs" if gcs_path else "db"
    FILE_PREVIEW_DURATION.labels(method=method).observe(time.time() - _t0)

    if not content:
        return http_error(404, "File not available — please re-upload", "NOT_FOUND")

    return Response(
        content=content,
        media_type=mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{file_name or "document"}"'},
    )


@router.get("/{doc_id}/url")
async def get_document_signed_url(doc_id: int, request: Request = None):
    """Return a short-lived GCS signed URL for direct browser preview.
    Falls back to {"signed_url": null, "fallback": true} when GCS is unavailable."""
    from app.api.services.storage_service import generate_signed_url
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None) if request else None)
    async with get_conn() as conn:
        row = await conn.fetchrow(_q(
            "SELECT file_name, mime_type, gcs_path FROM processed_documents "
            "WHERE id = %s AND tenant_id = %s"
        ), doc_id, tenant_id)

    if not row:
        return http_error(404, "Document not found", "NOT_FOUND")

    file_name = row["file_name"]
    mime_type = row["mime_type"]
    gcs_path = row["gcs_path"]

    if gcs_path:
        import time as _time
        _t0 = _time.time()
        signed_url = generate_signed_url(gcs_path, expires_in=900)
        FILE_PREVIEW_DURATION.labels(method="signed_url").observe(_time.time() - _t0)
        if signed_url:
            return ok_response("Signed URL", {"signed_url": signed_url, "file_name": file_name, "fallback": False})

    return ok_response("No GCS path", {"signed_url": None, "file_name": file_name, "fallback": True})
