"""
app/api/routes_email_invoice.py
Bridge Hub — Email → Invoice Routes
Gmail/IMAP → OCR → Draft pipeline
"""
from fastapi import APIRouter, Request, UploadFile, File
from pydantic import BaseModel
from typing import Optional
from app.api.tenant_context import resolve_tenant_id
from app.api.services.email_invoice_service import (
    fetch_invoice_emails,
    process_email_invoices,
    get_email_status,
)
from app.api.services.ocr_service import extract_invoice_fields, create_draft_from_invoice

router = APIRouter(prefix="/email-invoice", tags=["email-invoice"])


# ========== Models ==========

class ProcessEmailRequest(BaseModel):
    limit: Optional[int] = 10
    folder: Optional[str] = "INBOX"


# ========== Endpoints ==========

@router.get("/status")
def email_invoice_status():
    """
    Email → Invoice სერვისის სტატუსი.
    """
    return get_email_status()


@router.get("/fetch")
def fetch_emails(request: Request, limit: int = 10):
    """
    Gmail-იდან ახალი ინვოისების წამოღება (draft-ები არ იქმნება).
    """
    result = fetch_invoice_emails(limit=limit)
    return result


@router.post("/process")
def process_emails(req: ProcessEmailRequest, request: Request):
    """
    Gmail-იდან ინვოისების წამოღება + OCR + Draft შექმნა.
    """
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = process_email_invoices(
        tenant_id=tenant_id,
        limit=req.limit,
        folder=req.folder,
    )
    return result


@router.post("/manual-upload")
async def manual_upload(
    request: Request,
    file: UploadFile = File(...),
):
    """
    ხელით ინვოისის ატვირთვა და draft-ის შექმნა.
    იგივე pipeline — Email-ის გარეშე.
    """
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    data = await file.read()
    fields = extract_invoice_fields(file.filename, data)

    if not fields.get("amount"):
        return {
            "ok": False,
            "error": "თანხა ვერ ამოიღო",
            "fields": fields,
        }

    draft = create_draft_from_invoice(
        fields,
        tenant_id=tenant_id,
        source_type="email_manual_upload",
    )

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "filename": file.filename,
        "fields": fields,
        "draft": draft,
        "message": "ინვოისი დამუშავდა და queue-ში დაემატა",
    }


@router.get("/pipeline-info")
def pipeline_info():
    """
    Email → Invoice pipeline-ის აღწერა.
    """
    return {
        "ok": True,
        "pipeline": [
            {"step": 1, "name": "Gmail IMAP", "description": "ახალი email-ების წამოღება"},
            {"step": 2, "name": "Attachment Filter", "description": "PDF/Excel attachment-ების ფილტრაცია"},
            {"step": 3, "name": "OCR Extract", "description": "ველების ამოღება (amount, date, partner)"},
            {"step": 4, "name": "Draft Create", "description": "journal_draft შექმნა"},
            {"step": 5, "name": "Queue", "description": "pending_approval queue-ში დამატება"},
            {"step": 6, "name": "Approve", "description": "ბუღალტერი ამტკიცებს"},
            {"step": 7, "name": "Balance.ge", "description": "ავტომატური posting"},
        ],
        "supported_formats": [".pdf", ".xlsx", ".xls", ".png", ".jpg"],
        "mode": get_email_status().get("mode"),
    }