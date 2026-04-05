"""
app/api/services/email_invoice_service.py
Bridge Hub — Email → Invoice Service
Gmail/IMAP-იდან attachment-ების წამოღება და OCR-ით draft-ის შექმნა.
"""
import imaplib
import email
import os
from datetime import datetime
from typing import Optional
from app.api.services.ocr_service import extract_invoice_fields, create_draft_from_invoice


# ========== Config ==========

IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER = os.getenv("SMTP_USER", "")
IMAP_PASS = os.getenv("SMTP_PASS", "")


# ========== Email Fetching ==========

def fetch_invoice_emails(
    limit: int = 10,
    folder: str = "INBOX",
    subject_filter: str = "invoice",
) -> dict:
    """
    Gmail/IMAP-იდან ინვოისის email-ების წამოღება.
    DEMO mode — credentials-ის გარეშე.
    """
    if not IMAP_USER or not IMAP_PASS:
        return _demo_response()

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select(folder)

        search_criteria = f'(SUBJECT "{subject_filter}")'
        _, msg_ids = mail.search(None, search_criteria)

        emails = []
        ids = msg_ids[0].split()[-limit:]

        for msg_id in ids:
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            attachments = _extract_attachments(msg)
            emails.append({
                "message_id": msg_id.decode(),
                "subject": msg.get("Subject", ""),
                "from": msg.get("From", ""),
                "date": msg.get("Date", ""),
                "attachments": attachments,
            })

        mail.logout()
        return {
            "ok": True,
            "mode": "live",
            "count": len(emails),
            "emails": emails,
        }

    except Exception as e:
        return {"ok": False, "error": str(e), "mode": "live"}


def _extract_attachments(msg) -> list:
    """
    Email-იდან attachment-ების ამოღება.
    """
    attachments = []
    allowed = (".pdf", ".xlsx", ".xls", ".png", ".jpg", ".jpeg")

    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get("Content-Disposition") is None:
            continue

        filename = part.get_filename()
        if not filename:
            continue

        if not any(filename.lower().endswith(ext) for ext in allowed):
            continue

        data = part.get_payload(decode=True)
        attachments.append({
            "filename": filename,
            "size": len(data) if data else 0,
            "data": data,
        })

    return attachments


# ========== Process Emails ==========

def process_email_invoices(
    tenant_id: str = "default",
    limit: int = 10,
    folder: str = "INBOX",
) -> dict:
    """
    Email-ებიდან ინვოისების დამუშავება და draft-ების შექმნა.
    """
    result = fetch_invoice_emails(limit=limit, folder=folder)

    if not result.get("ok"):
        return result

    if result.get("mode") == "demo":
        return result

    processed = []
    errors = []

    for em in result.get("emails", []):
        for att in em.get("attachments", []):
            data = att.get("data")
            if not data:
                continue

            try:
                fields = extract_invoice_fields(att["filename"], data)
                if fields.get("amount"):
                    draft = create_draft_from_invoice(
                        fields,
                        tenant_id=tenant_id,
                        source_type="email_invoice",
                    )
                    processed.append({
                        "email_subject": em["subject"],
                        "email_from": em["from"],
                        "filename": att["filename"],
                        "amount": fields.get("amount"),
                        "draft_id": draft.get("draft_id"),
                        "ok": draft.get("ok"),
                    })
                else:
                    errors.append({
                        "filename": att["filename"],
                        "error": "თანხა ვერ ამოიღო",
                    })
            except Exception as e:
                errors.append({
                    "filename": att.get("filename", "unknown"),
                    "error": str(e),
                })

    return {
        "ok": True,
        "mode": "live",
        "processed": len(processed),
        "errors": len(errors),
        "drafts": processed,
        "failed": errors,
    }


# ========== Demo Mode ==========

def _demo_response() -> dict:
    """
    DEMO mode — IMAP credentials არ არის.
    """
    return {
        "ok": True,
        "mode": "demo",
        "message": "DEMO — IMAP_USER/IMAP_PASS არ არის კონფიგურირებული",
        "setup_required": {
            "SMTP_USER": "your@gmail.com",
            "SMTP_PASS": "gmail_app_password",
            "IMAP_HOST": "imap.gmail.com",
            "IMAP_PORT": "993",
        },
        "demo_emails": [
            {
                "subject": "Invoice #INV-2026-001 from შპს მაგთიკომი",
                "from": "billing@magticom.ge",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "attachments": [{"filename": "invoice_001.pdf", "size": 45231}],
            },
            {
                "subject": "Invoice from Geocell",
                "from": "invoice@geocell.ge",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "attachments": [{"filename": "geocell_invoice.pdf", "size": 32100}],
            },
        ],
    }


def get_email_status() -> dict:
    """
    Email სერვისის სტატუსი.
    """
    configured = bool(IMAP_USER and IMAP_PASS)
    return {
        "ok": True,
        "configured": configured,
        "mode": "live" if configured else "demo",
        "imap_host": IMAP_HOST,
        "imap_port": IMAP_PORT,
        "user": IMAP_USER[:3] + "***" if IMAP_USER else None,
        "features": [
            "Gmail/IMAP attachment წამოღება",
            "PDF/Excel OCR → Draft",
            "ავტომატური queue-ში დამატება",
        ],
    }