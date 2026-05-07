import logging
"""
app/api/routes_client_portal.py
Bridge Hub — Client Portal
კლიენტი ხედავს მხოლოდ საკუთარ ტრანზაქციებს.
Core approval logic არ ეხება.
"""
from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.api.authz import require_permission
from datetime import datetime
from app.api.db import get_conn, _q
from app.api.tenant_context import resolve_tenant_id
from app.api.response_utils import ok_response, error_response
log = logging.getLogger(__name__)


router = APIRouter(prefix="/client", tags=["client-portal"])


# ========== Models ==========

class ClientUploadRequest(BaseModel):
    description: Optional[str] = None
    partner: Optional[str] = None
    amount: Optional[float] = None


# ========== Client Dashboard ==========

@router.get("/dashboard")
async def client_dashboard(request: Request):
    """
    კლიენტის მთავარი გვერდი — საკუთარი ტრანზაქციების შეჯამება.
    """
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    client_id = request.headers.get("X-Client-ID", "default_client")

    async with get_conn() as conn:
        stats = dict(await conn.fetchrow(_q("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved,
                COUNT(CASE WHEN status = 'auto_approved' THEN 1 END) as auto_approved,
                COUNT(CASE WHEN status = 'pending_approval' THEN 1 END) as pending,
                COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected,
                COALESCE(SUM(amount), 0) as total_amount
            FROM journal_drafts
            WHERE tenant_id = %s AND partner = %s
        """), tenant_id, client_id))

        recent = [dict(r) for r in await conn.fetch(_q("""
            SELECT id, date, description, amount, status, created_at
            FROM journal_drafts
            WHERE tenant_id = %s AND partner = %s
            ORDER BY created_at DESC LIMIT 10
        """), tenant_id, client_id)]

    return {
        "ok": True,
        "client_id": client_id,
        "tenant_id": tenant_id,
        "stats": {
            "total": stats["total"],
            "approved": stats["approved"],
            "auto_approved": stats["auto_approved"],
            "pending": stats["pending"],
            "rejected": stats["rejected"],
            "total_amount": round(float(stats["total_amount"]), 2),
        },
        "recent_transactions": recent,
        "generated_at": datetime.now().isoformat(),
    }


# ========== Client Transactions ==========

@router.get("/transactions")
async def client_transactions(
    request: Request,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """
    კლიენტის ტრანზაქციების სია.
    """
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    client_id = request.headers.get("X-Client-ID", "default_client")

    async with get_conn() as conn:
        if status:
            items = [dict(r) for r in await conn.fetch(_q("""
                SELECT id, date, description, amount, status,
                       account_code, confidence, created_at, source_type
                FROM journal_drafts
                WHERE tenant_id = %s AND partner = %s AND status = %s
                ORDER BY created_at DESC LIMIT %s OFFSET %s
            """), tenant_id, client_id, status, limit, offset)]
        else:
            items = [dict(r) for r in await conn.fetch(_q("""
                SELECT id, date, description, amount, status,
                       account_code, confidence, created_at, source_type
                FROM journal_drafts
                WHERE tenant_id = %s AND partner = %s
                ORDER BY created_at DESC LIMIT %s OFFSET %s
            """), tenant_id, client_id, limit, offset)]

    return {
        "ok": True,
        "client_id": client_id,
        "tenant_id": tenant_id,
        "count": len(items),
        "limit": limit,
        "offset": offset,
        "transactions": items,
    }


# ========== Client Upload ==========

@router.post("/upload")
async def client_upload(
    request: Request,
    file: UploadFile = File(...),
):
    """
    კლიენტი ატვირთავს დოკუმენტს.
    OCR → Draft → pending_approval queue-ში.
    """
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    client_id = request.headers.get("X-Client-ID", "default_client")

    if not file.filename:
        raise HTTPException(status_code=400, detail="ფაილი სავალდებულოა")

    allowed = (".pdf", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".csv")
    if not any(file.filename.lower().endswith(ext) for ext in allowed):
        raise HTTPException(
            status_code=400,
            detail=f"დასაშვები ფორმატები: {', '.join(allowed)}"
        )

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="ფაილი 10MB-ზე მეტია")

    from app.api.services.ocr_service import extract_invoice_fields, create_draft_from_invoice_async
    fields = extract_invoice_fields(file.filename, data)

    if fields.get("amount"):
        fields["partner"] = client_id
        draft = await create_draft_from_invoice_async(
            fields,
            tenant_id=tenant_id,
            source_type="client_upload",
        )
    else:
        try:
            async with get_conn() as conn:
                draft_id = await conn.fetchval(_q("""
                    INSERT INTO journal_drafts (
                        date, description, partner, amount,
                        debit_account, credit_account, account_code,
                        reason, confidence, status, source_type, tenant_id, created_at
                    ) VALUES (
                        NOW()::date, %s, %s, 0,
                        '7100', '1210', '7100',
                        'client_upload', 0.5, 'pending_approval',
                        'client_upload', %s, NOW()
                    ) RETURNING id
                """), f"Client upload: {file.filename}", client_id, tenant_id)
            draft = {"ok": True, "draft_id": draft_id, "status": "pending_approval"}
        except Exception as e:
            draft = {"ok": False, "error": str(e)}

    return {
        "ok": True,
        "client_id": client_id,
        "tenant_id": tenant_id,
        "filename": file.filename,
        "extracted_fields": fields,
        "draft": draft,
        "message": "დოკუმენტი მიღებულია. ბუღალტერი განიხილავს.",
    }


# ========== Transaction Detail ==========

@router.get("/transactions/{draft_id}")
async def client_transaction_detail(draft_id: int, request: Request):
    """
    კლიენტი ხედავს ერთი ტრანზაქციის დეტალებს.
    """
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    client_id = request.headers.get("X-Client-ID", "default_client")

    async with get_conn() as conn:
        row = await conn.fetchrow(_q("""
            SELECT id, date, description, amount, status,
                   account_code, confidence, created_at,
                   source_type, debit_account, credit_account
            FROM journal_drafts
            WHERE id = %s AND tenant_id = %s AND partner = %s
        """), draft_id, tenant_id, client_id)

        if not row:
            raise HTTPException(status_code=404, detail="ტრანზაქცია ვერ მოიძებნა")

        comments = []
        try:
            comments = [dict(r) for r in await conn.fetch(_q("""
                SELECT author, comment_text, comment_type, created_at
                FROM draft_comments
                WHERE draft_id = %s AND tenant_id = %s
                ORDER BY created_at ASC
            """), draft_id, tenant_id)]
        except Exception as e:
            log.warning("unexpected error: %s", e)

    return {
        "ok": True,
        "transaction": dict(row),
        "comments": comments,
    }


# ========== Invoices for client ==========

@router.get("/invoices")
async def client_invoices(request: Request):
    """Client sees their own invoices — amount, status, due date."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            rows = [dict(r) for r in await conn.fetch(_q("""
                SELECT id, invoice_number, issue_date, due_date,
                       total, currency, status, notes
                FROM invoices
                WHERE tenant_id = %s
                ORDER BY issue_date DESC LIMIT 100
            """), tenant_id)]
        for r in rows:
            for f in ("issue_date", "due_date"):
                if r.get(f):
                    r[f] = str(r[f])[:10]
    except Exception:
        rows = []

    total_outstanding = sum(
        float(r.get("total") or 0) for r in rows
        if r.get("status") not in ("paid", "cancelled")
    )
    return ok_response("Invoices", {"invoices": rows,
            "summary": {"total_outstanding": total_outstanding,
                        "count": len(rows)}})


@router.get("/invoices/{invoice_id}/pdf")
async def client_invoice_pdf(invoice_id: int, request: Request):
    """Download invoice as PDF."""
    require_permission(request, "reports:read")
    from fastapi.responses import StreamingResponse
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    import io as _io

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        inv = await conn.fetchrow(_q(
            "SELECT * FROM invoices WHERE id = %s AND tenant_id = %s"
        ), invoice_id, tenant_id)

    if not inv:
        from app.api.response_utils import http_error
        return http_error(404, "Invoice not found", "NOT_FOUND")

    inv = dict(inv)
    buf = _io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             leftMargin=2*cm, rightMargin=2*cm,
                             topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("T", parent=styles["Heading1"],
                                  fontSize=18, textColor=colors.HexColor("#1a365d"))
    story = [
        Paragraph("Bridge Hub — Invoice", title_style),
        Spacer(1, 0.5*cm),
    ]

    meta = [
        ["Invoice #", str(inv.get("invoice_number") or invoice_id)],
        ["Date", str(inv.get("issue_date") or "")[:10]],
        ["Due Date", str(inv.get("due_date") or "")[:10]],
        ["Status", str(inv.get("status") or "").upper()],
        ["Currency", str(inv.get("currency") or "GEL")],
    ]
    meta_tbl = Table(meta, colWidths=[5*cm, 10*cm])
    meta_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dee2e6")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 0.5*cm))

    totals = [
        ["Subtotal", f"{float(inv.get('subtotal') or 0):,.2f}"],
        ["VAT", f"{float(inv.get('vat_amount') or 0):,.2f}"],
        ["TOTAL", f"{float(inv.get('total') or 0):,.2f} {inv.get('currency','GEL')}"],
    ]
    tot_tbl = Table(totals, colWidths=[10*cm, 5*cm])
    tot_tbl.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dee2e6")),
        ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#e8f5e9")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(tot_tbl)

    if inv.get("notes"):
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(f"Notes: {inv['notes']}", styles["Normal"]))

    doc.build(story)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="invoice_{invoice_id}.pdf"'},
    )


@router.get("/statement")
async def client_statement(request: Request):
    """Account statement — all transactions summary for client."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            rows = [dict(r) for r in await conn.fetch(_q("""
                SELECT DATE_TRUNC('month', created_at) AS month,
                       COUNT(*) AS transactions,
                       SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS total_income,
                       SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) AS total_expense
                FROM journal_drafts
                WHERE tenant_id = %s AND status = 'approved'
                GROUP BY 1 ORDER BY 1 DESC LIMIT 12
            """), tenant_id)]
        for r in rows:
            if r.get("month"):
                r["month"] = str(r["month"])[:7]
            for f in ("total_income", "total_expense"):
                if r.get(f):
                    r[f] = float(r[f])
    except Exception:
        rows = []

    return ok_response("ok", {"statement": rows})


# ========== Status ==========

@router.get("/status")
def client_portal_status():
    return {
        "ok": True,
        "portal": "active",
        "features": [
            "dashboard", "transactions", "upload", "detail",
            "invoices", "invoices/{id}/pdf", "statement",
        ],
    }