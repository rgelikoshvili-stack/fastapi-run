"""
app/api/services/email_invoice_service.py
Bridge Hub — Email → Invoice Service
ყველა email წაიკითხავს, attachment-ებს ამოიღებს,
მომხმარებელი ადასტურებს — მერე გაატარებს.
"""
import imaplib
import email
import os
from datetime import datetime
from app.api.services.ocr_service import extract_invoice_fields, create_draft_from_invoice

IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER = os.getenv("SMTP_USER", "")
IMAP_PASS = os.getenv("SMTP_PASS", "")

ALLOWED = (".pdf", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".doc", ".docx")


def fetch_all_emails(limit: int = 20, folder: str = "INBOX") -> dict:
    """
    Gmail-იდან ყველა email წაიკითხავს (subject ფილტრი გამორთულია).
    attachment-ების სია მომხმარებელს აჩვენებს — draft არ იქმნება.
    """
    if not IMAP_USER or not IMAP_PASS:
        return _demo_response()

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select(folder)

        # ყველა email — subject ფილტრი არ არის
        _, msg_ids = mail.search(None, "ALL")

        emails = []
        ids = msg_ids[0].split()[-limit:]

        for msg_id in reversed(ids):
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            attachments = _extract_attachments(msg)
            emails.append({
                "message_id": msg_id.decode(),
                "subject": msg.get("Subject", "(no subject)"),
                "from": msg.get("From", ""),
                "date": msg.get("Date", ""),
                "has_attachments": len(attachments) > 0,
                "attachments": [
                    {"filename": a["filename"], "size": a["size"]}
                    for a in attachments
                ],
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


def fetch_invoice_emails(limit: int = 10, folder: str = "INBOX") -> dict:
    """fetch_all_emails alias — backward compat."""
    return fetch_all_emails(limit=limit, folder=folder)


def process_email_by_id(
    message_id: str,
    tenant_id: str = "default",
    folder: str = "INBOX",
    force: bool = False,
) -> dict:
    """
    მომხმარებლის დადასტურების შემდეგ კონკრეტული email-ის დამუშავება.
    message_id — fetch_all_emails-დან მოსული id.
    """
    if not IMAP_USER or not IMAP_PASS:
        return {"ok": False, "error": "IMAP not configured"}

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select(folder)

        _, msg_data = mail.fetch(message_id.encode(), "(RFC822)")
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        mail.logout()

        attachments = _extract_attachments_with_data(msg)

        if not attachments:
            return {
                "ok": False,
                "error": "email-ს attachment არ აქვს",
                "subject": msg.get("Subject", ""),
            }

        results = []
        errors = []

        for att in attachments:
            try:
                fields = extract_invoice_fields(att["filename"], att["data"])
                if fields.get("amount"):
                    draft = create_draft_from_invoice(
                        fields,
                        tenant_id=tenant_id,
                        source_type="email_invoice",
                        force=force,
                    )
                    results.append({
                        "filename": att["filename"],
                        "amount": fields.get("amount"),
                        "partner": fields.get("partner"),
                        "draft": draft,
                        "duplicate": draft.get("duplicate", False),
                    })
                else:
                    errors.append({
                        "filename": att["filename"],
                        "error": "თანხა ვერ ამოიღო",
                    })
            except Exception as e:
                errors.append({"filename": att["filename"], "error": str(e)})

        return {
            "ok": True,
            "message_id": message_id,
            "subject": msg.get("Subject", ""),
            "from": msg.get("From", ""),
            "processed": len(results),
            "errors": len(errors),
            "results": results,
            "failed": errors,
        }

    except Exception as e:
        return {"ok": False, "error": str(e)}


def process_email_invoices(
    tenant_id: str = "default",
    limit: int = 10,
    folder: str = "INBOX",
) -> dict:
    """ყველა email-ის batch დამუშავება."""
    result = fetch_all_emails(limit=limit, folder=folder)
    if not result.get("ok") or result.get("mode") == "demo":
        return result

    if not IMAP_USER or not IMAP_PASS:
        return result

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select(folder)
        _, msg_ids = mail.search(None, "ALL")
        ids = msg_ids[0].split()[-limit:]

        processed = []
        errors = []

        for msg_id in ids:
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            attachments = _extract_attachments_with_data(msg)

            for att in attachments:
                try:
                    fields = extract_invoice_fields(att["filename"], att["data"])
                    if fields.get("amount"):
                        draft = create_draft_from_invoice(
                            fields, tenant_id=tenant_id, source_type="email_invoice"
                        )
                        processed.append({
                            "email_subject": msg.get("Subject", ""),
                            "email_from": msg.get("From", ""),
                            "filename": att["filename"],
                            "amount": fields.get("amount"),
                            "draft_id": draft.get("draft_id"),
                            "ok": draft.get("ok"),
                            "duplicate": draft.get("duplicate", False),
                        })
                    else:
                        errors.append({"filename": att["filename"], "error": "თანხა ვერ ამოიღო"})
                except Exception as e:
                    errors.append({"filename": att.get("filename", "?"), "error": str(e)})

        mail.logout()
        return {
            "ok": True,
            "mode": "live",
            "processed": len(processed),
            "errors": len(errors),
            "drafts": processed,
            "failed": errors,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _extract_attachments(msg) -> list:
    """attachment სია — data გარეშე (preview-ისთვის)."""
    result = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = part.get_filename()
        if not filename:
            continue
        if not any(filename.lower().endswith(ext) for ext in ALLOWED):
            continue
        data = part.get_payload(decode=True)
        result.append({"filename": filename, "size": len(data) if data else 0})
    return result


def _extract_attachments_with_data(msg) -> list:
    """attachment სია data-ით (დამუშავებისთვის)."""
    result = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = part.get_filename()
        if not filename:
            continue
        if not any(filename.lower().endswith(ext) for ext in ALLOWED):
            continue
        data = part.get_payload(decode=True)
        if data:
            result.append({"filename": filename, "size": len(data), "data": data})
    return result


def _demo_response() -> dict:
    return {
        "ok": True,
        "mode": "demo",
        "message": "DEMO — IMAP არ არის კონფიგურირებული",
        "count": 2,
        "emails": [
            {
                "message_id": "demo_1",
                "subject": "Invoice #INV-2026-001 — შპს მაგთიკომი",
                "from": "billing@magticom.ge",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "has_attachments": True,
                "attachments": [{"filename": "invoice_001.pdf", "size": 45231}],
            },
            {
                "message_id": "demo_2",
                "subject": "ანგარიშ-ფაქტურა — Geocell",
                "from": "invoice@geocell.ge",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "has_attachments": True,
                "attachments": [{"filename": "geocell_march.xlsx", "size": 32100}],
            },
        ],
    }


def get_email_status() -> dict:
    configured = bool(IMAP_USER and IMAP_PASS)
    return {
        "ok": True,
        "configured": configured,
        "mode": "live" if configured else "demo",
        "imap_host": IMAP_HOST,
        "imap_port": IMAP_PORT,
        "user": IMAP_USER[:3] + "***" if IMAP_USER else None,
        "features": [
            "ყველა Gmail email წაიკითხავს",
            "PDF/Excel/Word/Image attachment support",
            "Duplicate detection",
            "მომხმარებლის დადასტურება → გატარება",
        ],
    }
