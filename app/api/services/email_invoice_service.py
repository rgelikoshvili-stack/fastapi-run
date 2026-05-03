"""
app/api/services/email_invoice_service.py
Bridge Hub — Email → Invoice Service
ყველა email წაიკითხავს, attachment-ებს ამოიღებს,
მომხმარებელი ადასტურებს — მერე გაატარებს.
"""
import imaplib
import email
import email.header
import socket
import os
from datetime import datetime
from app.api.services.ocr_service import extract_invoice_fields, create_draft_from_invoice

IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER = os.getenv("SMTP_USER", "")
IMAP_PASS = os.getenv("SMTP_PASS", "")


def _imap_connect(imap_user: str, imap_pass: str, folder: str = "INBOX"):
    """Open a fresh IMAP connection with 60s socket timeout."""
    socket.setdefaulttimeout(60)
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(imap_user, imap_pass)
    try:
        mail.select(folder)
    except IndexError:
        # imaplib bug: Gmail returns empty EXISTS response on SELECT
        # Connection is still usable — proceed without raising
        pass
    return mail


def _imap_uid_fetch(mail, uid: str):
    """Fetch full message by UID. Returns raw bytes or None."""
    try:
        status, data = mail.uid("FETCH", uid.encode() if isinstance(uid, str) else uid, "(RFC822)")
        if status == "OK" and data and data[0] and isinstance(data[0], tuple) and data[0][1]:
            return data[0][1]
    except Exception:
        pass
    # Fallback: sequence number fetch
    try:
        status2, data2 = mail.fetch(uid.encode() if isinstance(uid, str) else uid, "(RFC822)")
        if status2 == "OK" and data2 and data2[0] and isinstance(data2[0], tuple) and data2[0][1]:
            return data2[0][1]
    except Exception:
        pass
    return None

ALLOWED = (".pdf", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".doc", ".docx")


def _get_tenant_imap_creds(tenant_id: str = None):
    """Return (user, password) — tenant DB creds first, fallback to env vars."""
    if tenant_id:
        try:
            from app.api.services.email_collector import get_tenant_email_credentials
            creds = get_tenant_email_credentials(tenant_id)
            if creds:
                return creds["email"], creds["app_password"]
        except Exception:
            pass
    return IMAP_USER, IMAP_PASS


def _extract_body(msg) -> str:
    """Extract plain text body from email message."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in cd:
                try:
                    charset = part.get_content_charset() or "utf-8"
                    body = part.get_payload(decode=True).decode(charset, errors="replace")
                    break
                except Exception:
                    pass
    else:
        if msg.get_content_type() == "text/plain":
            try:
                charset = msg.get_content_charset() or "utf-8"
                body = msg.get_payload(decode=True).decode(charset, errors="replace")
            except Exception:
                pass
    return body.strip()[:2000]  # cap at 2000 chars


def fetch_all_emails(limit: int = 20, folder: str = "INBOX", tenant_id: str = None) -> dict:
    """
    Gmail-იდან ყველა email წაიკითხავს (subject ფილტრი გამორთულია).
    attachment-ების სია მომხმარებელს აჩვენებს — draft არ იქმნება.
    """
    imap_user, imap_pass = _get_tenant_imap_creds(tenant_id)
    if not imap_user or not imap_pass:
        return _demo_response()

    mail = None
    try:
        mail = _imap_connect(imap_user, imap_pass, folder)

        # Use UIDs (stable across sessions) instead of sequence numbers
        _, uid_data = mail.uid("SEARCH", None, "ALL")
        all_uids = uid_data[0].split() if uid_data and uid_data[0] else []

        emails = []
        for uid in reversed(all_uids[-limit:]):
            raw = _imap_uid_fetch(mail, uid.decode())
            if not raw:
                continue
            msg = email.message_from_bytes(raw)
            attachments = _extract_attachments(msg)
            body = _extract_body(msg)
            emails.append({
                "message_id": uid.decode(),
                "subject": msg.get("Subject", "(no subject)"),
                "from": msg.get("From", ""),
                "to": msg.get("To", ""),
                "date": msg.get("Date", ""),
                "body": body,
                "snippet": body[:120] if body else "",
                "has_attachments": len(attachments) > 0,
                "attachment_count": len(attachments),
                "attachments": [
                    {"filename": a["filename"], "size": a["size"]}
                    for a in attachments
                ],
            })

        return {
            "ok": True,
            "mode": "live",
            "count": len(emails),
            "emails": emails,
        }

    except Exception as e:
        return {"ok": False, "error": str(e), "mode": "live"}
    finally:
        try:
            if mail:
                mail.logout()
        except Exception:
            pass


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
    imap_user, imap_pass = _get_tenant_imap_creds(tenant_id)
    if not imap_user or not imap_pass:
        return {"ok": False, "error": "IMAP not configured — Settings → Email-ში შეიყვანეთ Gmail credentials"}

    mail = None
    try:
        mail = _imap_connect(imap_user, imap_pass, folder)

        raw = _imap_uid_fetch(mail, message_id)
        if not raw:
            return {"ok": False, "error": f"Message {message_id} not found — inbox განახლება სცადე (Refresh)"}

        msg = email.message_from_bytes(raw)
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
                if not fields.get("amount"):
                    errors.append({
                        "filename": att["filename"],
                        "error": "თანხა ვერ ამოიღო — გადაამოწმეთ ხელით",
                    })
                    continue

                draft = create_draft_from_invoice(
                    fields,
                    tenant_id=tenant_id,
                    source_type="email_invoice",
                    force=force,
                )

                if draft.get("duplicate"):
                    # Surface duplicate as a warning, not silent success
                    errors.append({
                        "filename": att["filename"],
                        "error": f"⚠️ დუბლიკატი — Draft #{draft.get('draft_id')} უკვე არსებობს",
                        "duplicate": True,
                        "existing_draft_id": draft.get("draft_id"),
                    })
                    continue

                if not draft.get("ok"):
                    errors.append({
                        "filename": att["filename"],
                        "error": draft.get("error", "draft შექმნა ვერ მოხდა"),
                    })
                    continue

                draft_id = draft.get("draft_id")
                # Save original file as draft attachment
                _attach_file_to_draft(draft_id, att["filename"], att["data"], tenant_id)

                results.append({
                    "filename": att["filename"],
                    "amount": fields.get("amount"),
                    "partner": fields.get("partner"),
                    "draft_id": draft_id,
                    "draft": draft,
                })
            except Exception as e:
                errors.append({"filename": att["filename"], "error": str(e)})

        # Collect all draft IDs for easy frontend access
        draft_ids = [
            r["draft"].get("draft_id") or r["draft"].get("id")
            for r in results
            if r.get("draft") and (r["draft"].get("draft_id") or r["draft"].get("id"))
        ]
        return {
            "ok": len(results) > 0,
            "message_id": message_id,
            "subject": msg.get("Subject", ""),
            "from": msg.get("From", ""),
            "processed": len(results),
            "errors": len(errors),
            "draft_id": draft_ids[0] if draft_ids else None,
            "draft_ids": draft_ids,
            "results": results,
            "failed": errors,
        }

    except Exception as e:
        import traceback
        return {"ok": False, "error": str(e), "traceback": traceback.format_exc()[-800:]}
    finally:
        try:
            if mail:
                mail.logout()
        except Exception:
            pass


def process_email_invoices(
    tenant_id: str = "default",
    limit: int = 10,
    folder: str = "INBOX",
) -> dict:
    """ყველა email-ის batch დამუშავება."""
    imap_user, imap_pass = _get_tenant_imap_creds(tenant_id)
    if not imap_user or not imap_pass:
        return {"ok": False, "error": "IMAP not configured"}

    result = fetch_all_emails(limit=limit, folder=folder, tenant_id=tenant_id)
    if not result.get("ok") or result.get("mode") == "demo":
        return result

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(imap_user, imap_pass)
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


def _decode_filename(raw: str) -> str:
    """RFC 2047 encoded filename → unicode string (handles Georgian, etc.)."""
    if not raw:
        return raw
    parts = email.header.decode_header(raw)
    decoded = []
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            decoded.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(chunk)
    return "".join(decoded)


def _get_part_filename(part) -> str | None:
    """Get attachment filename, trying Content-Disposition and Content-Type."""
    raw = part.get_filename()
    if not raw:
        # Some mailers put filename only in Content-Type name param
        raw = part.get_param("name")
    if not raw:
        return None
    return _decode_filename(raw)


def _extract_attachments(msg) -> list:
    """attachment სია — data გარეშე (preview-ისთვის)."""
    result = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = _get_part_filename(part)
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
        filename = _get_part_filename(part)
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


def _attach_file_to_draft(draft_id: int, filename: str, data: bytes, tenant_id: str) -> None:
    """Upload file bytes to storage and link to journal_drafts row. Failures are silent."""
    if not draft_id or not data:
        return
    try:
        import mimetypes
        from app.api.services.storage_service import upload_file
        from app.api.db import get_db
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        path = upload_file(data, filename, mime, tenant_id)
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE journal_drafts SET attached_file_path=%s, attached_file_name=%s, attached_file_size=%s "
                "WHERE id=%s AND tenant_id=%s",
                (path, filename, len(data), draft_id, tenant_id),
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()
    except Exception:
        pass


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
