"""
app/api/routes_email_invoice.py
Bridge Hub — Email → Invoice Routes
"""
from fastapi import APIRouter, Request, UploadFile, File
from pydantic import BaseModel
from typing import Optional
from app.api.tenant_context import resolve_tenant_id
from app.api.services.email_invoice_service import (
    fetch_all_emails,
    process_email_by_id,
    process_email_invoices,
    get_email_status,
)
from app.api.services.ocr_service import extract_invoice_fields, create_draft_from_invoice

router = APIRouter(prefix="/email-invoice", tags=["email-invoice"])


class ProcessByIdRequest(BaseModel):
    message_id: str
    force: Optional[bool] = False


class ProcessEmailRequest(BaseModel):
    limit: Optional[int] = 10
    folder: Optional[str] = "INBOX"


@router.get("/status")
def email_status():
    return get_email_status()


@router.get("/inbox")
def get_inbox(request: Request, limit: int = 20):
    """
    Gmail inbox — ყველა email სია attachment-ებით.
    მომხმარებელი ხედავს რა არის მოსული.
    Draft არ იქმნება.
    """
    result = fetch_all_emails(limit=limit)
    return result


@router.get("/fetch")
def fetch_emails(request: Request, limit: int = 10):
    """backward compat alias."""
    return fetch_all_emails(limit=limit)


@router.post("/confirm-process")
def confirm_process(req: ProcessByIdRequest, request: Request):
    """
    მომხმარებლის დადასტურების შემდეგ კონკრეტული email-ის გატარება.
    message_id — /email-invoice/inbox-დან.
    force=True — duplicate-ის შემთხვევაშიც გაატარებს.
    """
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = process_email_by_id(
        message_id=req.message_id,
        tenant_id=tenant_id,
        force=req.force,
    )
    return result


@router.post("/process")
def process_all(req: ProcessEmailRequest, request: Request):
    """ყველა email-ის batch დამუშავება."""
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return process_email_invoices(
        tenant_id=tenant_id,
        limit=req.limit,
        folder=req.folder,
    )


@router.post("/manual-upload")
async def manual_upload(request: Request, file: UploadFile = File(...)):
    """ხელით ატვირთვა + duplicate check."""
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    data = await file.read()
    fields = extract_invoice_fields(file.filename, data)
    if not fields.get("amount"):
        return {"ok": False, "error": "თანხა ვერ ამოიღო", "fields": fields}
    draft = create_draft_from_invoice(fields, tenant_id=tenant_id, force=False)
    if draft.get("duplicate"):
        existing = draft.get("existing_draft", {})
        return {
            "ok": False,
            "duplicate": True,
            "warning": f"⚠️ ეს ინვოისი უკვე გატარებულია! Draft #{existing.get('id')}",
            "existing_draft": existing,
            "extracted_fields": fields,
        }
    return {
        "ok": True,
        "tenant_id": tenant_id,
        "filename": file.filename,
        "fields": fields,
        "draft": draft,
        "message": "✅ ინვოისი დამუშავდა და queue-ში დაემატა",
    }


@router.get("/pipeline-info")
def pipeline_info():
    return {
        "ok": True,
        "workflow": [
            {"step": 1, "action": "GET /email-invoice/inbox", "desc": "ყველა email-ის სია"},
            {"step": 2, "action": "მომხმარებელი ირჩევს email-ს", "desc": "UI-ში ხედავს სიას"},
            {"step": 3, "action": "POST /email-invoice/confirm-process", "desc": "დადასტურება → გატარება"},
            {"step": 4, "action": "duplicate check", "desc": "თუ დუბლიკატია — გაფრთხილება"},
            {"step": 5, "action": "pending_approval queue", "desc": "ბუღალტერი ამტკიცებს"},
        ],
        "supported_formats": [".pdf", ".xlsx", ".xls", ".png", ".jpg", ".doc", ".docx"],
    }
