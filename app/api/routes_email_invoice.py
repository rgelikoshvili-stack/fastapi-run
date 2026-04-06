"""
app/api/routes_email_invoice.py
Bridge Hub — Email → Invoice Routes
"""
from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional
import imaplib
import email as emaillib
import os

from app.api.tenant_context import resolve_tenant_id
from app.api.services.email_invoice_service import (
    fetch_all_emails,
    process_email_by_id,
    process_email_invoices,
    get_email_status,
)
from app.api.services.ocr_service import extract_invoice_fields, create_draft_from_invoice

router = APIRouter(prefix="/email-invoice", tags=["email-invoice"])

IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER = os.getenv("SMTP_USER", "")
IMAP_PASS = os.getenv("SMTP_PASS", "")


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
    return fetch_all_emails(limit=limit)


@router.get("/fetch")
def fetch_emails(request: Request, limit: int = 10):
    return fetch_all_emails(limit=limit)


@router.post("/confirm-process")
def confirm_process(req: ProcessByIdRequest, request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return process_email_by_id(
        message_id=req.message_id,
        tenant_id=tenant_id,
        force=req.force,
    )


@router.post("/process")
def process_all(req: ProcessEmailRequest, request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return process_email_invoices(
        tenant_id=tenant_id,
        limit=req.limit,
        folder=req.folder,
    )


@router.post("/manual-upload")
async def manual_upload(request: Request, file: UploadFile = File(...)):
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
        "message": "✅ ინვოისი დამუშავდა",
    }


@router.get("/preview/{message_id}/{filename}")
async def preview_attachment(message_id: str, filename: str, request: Request):
    """
    PDF preview — ბრაუზერში გასახსნელად.
    მომხმარებელი ნახავს invoice-ს დადასტურებამდე.
    """
    if not IMAP_USER or not IMAP_PASS:
        return Response(content=b"IMAP not configured", status_code=503)
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select("INBOX")
        _, msg_data = mail.fetch(message_id.encode(), "(RFC822)")
        msg = emaillib.message_from_bytes(msg_data[0][1])
        mail.logout()
        for part in msg.walk():
            if part.get_filename() == filename:
                data = part.get_payload(decode=True)
                ct = part.get_content_type() or "application/octet-stream"
                disp = "inline" if ct == "application/pdf" else "attachment"
                return Response(
                    content=data, media_type=ct,
                    headers={"Content-Disposition": f"{disp}; filename={filename}"}
                )
        return Response(content=b"Not found", status_code=404)
    except Exception as e:
        return Response(content=str(e).encode(), status_code=500)


@router.get("/pipeline-info")
def pipeline_info():
    return {
        "ok": True,
        "workflow": [
            {"step": 1, "action": "GET /email-invoice/inbox", "desc": "სია"},
            {"step": 2, "action": "GET /email-invoice/preview/{id}/{file}", "desc": "PDF ნახვა"},
            {"step": 3, "action": "POST /email-invoice/confirm-process", "desc": "გატარება"},
            {"step": 4, "action": "duplicate check", "desc": "გაფრთხილება"},
            {"step": 5, "action": "pending_approval queue", "desc": "დამტკიცება"},
        ],
        "supported_formats": [".pdf", ".xlsx", ".xls", ".png", ".jpg", ".doc", ".docx"],
    }
