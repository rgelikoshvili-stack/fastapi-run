import logging
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
from app.api.response_utils import ok_response, error_response
from app.api.services.email_invoice_service import (
    fetch_all_emails,
    process_email_by_id,
    process_email_invoices,
    get_email_status,
)
from app.api.services.ocr_service import extract_invoice_fields, create_draft_from_invoice
from app.api.authz import require_permission
log = logging.getLogger(__name__)


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
    require_permission(request, "approval:write")
    return get_email_status()


@router.get("/inbox")
def get_inbox(request: Request, limit: int = 20):
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return fetch_all_emails(limit=limit, tenant_id=tenant_id)


@router.get("/fetch")
def fetch_emails(request: Request, limit: int = 10):
    require_permission(request, "approval:write")
    return fetch_all_emails(limit=limit)


@router.post("/confirm-process")
def confirm_process(req: ProcessByIdRequest, request: Request):
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return process_email_by_id(
        message_id=req.message_id,
        tenant_id=tenant_id,
        force=req.force,
    )


@router.post("/process")
def process_all(req: ProcessEmailRequest, request: Request):
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return process_email_invoices(
        tenant_id=tenant_id,
        limit=req.limit,
        folder=req.folder,
    )


@router.post("/manual-upload")
async def manual_upload(request: Request, file: UploadFile = File(...)):
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    data = await file.read()
    fields = extract_invoice_fields(file.filename, data)
    if not fields.get("amount"):
        return error_response("თანხა ვერ ამოიღო", "AMOUNT_MISSING", str(fields))
    draft = create_draft_from_invoice(fields, tenant_id=tenant_id, force=False)
    if draft.get("duplicate"):
        existing = draft.get("existing_draft", {})
        return error_response(f"⚠️ ეს ინვოისი უკვე გატარებულია! Draft #{existing.get('id')}", "DUPLICATE", str(existing))
    return ok_response("Invoice processed", {
        "tenant_id": tenant_id,
        "filename": file.filename,
        "fields": fields,
        "draft": draft,
    })


@router.get("/preview/{message_id}/{filename}")
async def preview_attachment(message_id: str, filename: str, request: Request):
    """PDF preview — authenticated fetch → blob URL in browser."""
    from app.api.services.email_invoice_service import _get_tenant_imap_creds
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    imap_user, imap_pass = _get_tenant_imap_creds(tenant_id)
    if not imap_user or not imap_pass:
        return Response(content=b"IMAP not configured", status_code=503)
    try:
        imap_host = os.getenv("IMAP_HOST", "imap.gmail.com")
        imap_port = int(os.getenv("IMAP_PORT", "993"))
        import socket
        socket.setdefaulttimeout(60)
        mail = imaplib.IMAP4_SSL(imap_host, imap_port)
        mail.login(imap_user, imap_pass)
        try:
            mail.select("INBOX")
        except IndexError as e:
            log.warning("unexpected error: %s", e)
        # message_id is a UID — use uid("FETCH") not fetch() which uses sequence numbers
        _, msg_data = mail.uid("FETCH", message_id.encode(), "(RFC822)")

        # Guard against malformed IMAP response
        if not msg_data or not msg_data[0] or not isinstance(msg_data[0], tuple) or not msg_data[0][1]:
            mail.logout()
            return Response(content=b"Message not found or empty", status_code=404)

        msg = emaillib.message_from_bytes(msg_data[0][1])
        mail.logout()

        from app.api.services.email_invoice_service import _get_part_filename
        for part in msg.walk():
            fn = _get_part_filename(part)
            if not fn:
                continue
            # Match decoded filename, case-insensitive, ignoring whitespace
            if fn.strip().lower() == filename.strip().lower():
                data = part.get_payload(decode=True)
                if not data:
                    return Response(content=b"Attachment data empty", status_code=404)
                ct = part.get_content_type() or "application/octet-stream"
                disp = "inline" if ct == "application/pdf" else "attachment"
                from urllib.parse import quote
                encoded_name = quote(filename, safe="")
                return Response(
                    content=data, media_type=ct,
                    headers={"Content-Disposition": f"{disp}; filename*=UTF-8''{encoded_name}"}
                )
        return Response(content=f"Attachment '{filename}' not found in message".encode(), status_code=404)
    except Exception as e:
        import traceback
        msg = f"Error: {e}\n{traceback.format_exc()}"
        return Response(content=msg.encode("utf-8"), status_code=500,
                        media_type="text/plain; charset=utf-8")


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
