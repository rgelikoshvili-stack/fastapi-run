"""app/api/services/email_collector.py
Bridge Hub — Per-tenant Email IMAP Collector (STEP 1.4)
Each tenant has its own Gmail credentials stored in DB.
Polls inbox, extracts PDFs, triggers AI processing.
"""
import email as emaillib
import imaplib
import logging
import os
from datetime import datetime, timezone
from email.header import decode_header
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

log = logging.getLogger(__name__)

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
ALLOWED_EXTS = (".pdf", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".doc", ".docx")


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_db():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not configured")
    return psycopg2.connect(url)


def _ensure_tables():
    """Create tenant_email_credentials and email_documents tables if missing."""
    conn = _get_db()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tenant_email_credentials (
                id          SERIAL PRIMARY KEY,
                tenant_id   TEXT NOT NULL UNIQUE,
                email       TEXT NOT NULL,
                app_password TEXT NOT NULL,
                active      BOOLEAN DEFAULT TRUE,
                created_at  TIMESTAMPTZ DEFAULT NOW(),
                updated_at  TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS email_documents (
                id           SERIAL PRIMARY KEY,
                tenant_id    TEXT NOT NULL,
                message_uid  TEXT NOT NULL,
                filename     TEXT,
                raw_bytes    BYTEA,
                raw_text     TEXT,
                source       TEXT DEFAULT 'email',
                status       TEXT DEFAULT 'pending',
                draft_id     INTEGER,
                created_at   TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (tenant_id, message_uid, filename)
            );
        """)
    conn.commit()
    conn.close()


def get_tenant_email_credentials(tenant_id: str) -> Optional[dict]:
    try:
        conn = _get_db()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT email, app_password FROM tenant_email_credentials "
                "WHERE tenant_id = %s AND active = TRUE",
                (tenant_id,),
            )
            row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        log.warning("get_tenant_email_credentials: %s", e)
        return None


def save_tenant_email_credentials(tenant_id: str, email_addr: str, app_password: str) -> bool:
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tenant_email_credentials (tenant_id, email, app_password, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tenant_id) DO UPDATE
                    SET email = EXCLUDED.email,
                        app_password = EXCLUDED.app_password,
                        active = TRUE,
                        updated_at = EXCLUDED.updated_at
                """,
                (tenant_id, email_addr, app_password, datetime.now(timezone.utc)),
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        log.error("save_tenant_email_credentials: %s", e)
        return False


def _already_processed(tenant_id: str, message_uid: str, filename: str) -> bool:
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM email_documents WHERE tenant_id=%s AND message_uid=%s AND filename=%s",
                (tenant_id, message_uid, filename),
            )
            found = cur.fetchone() is not None
        conn.close()
        return found
    except Exception:
        return False


def _save_email_document(
    tenant_id: str, message_uid: str, filename: str,
    raw_bytes: bytes, raw_text: str = "",
) -> int:
    conn = _get_db()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO email_documents (tenant_id, message_uid, filename, raw_bytes, raw_text, status)
            VALUES (%s, %s, %s, %s, %s, 'pending')
            ON CONFLICT (tenant_id, message_uid, filename) DO UPDATE
                SET status = 'pending', raw_text = EXCLUDED.raw_text
            RETURNING id
            """,
            (tenant_id, message_uid, filename, psycopg2.Binary(raw_bytes), raw_text),
        )
        doc_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return doc_id


def _update_doc_draft(doc_id: int, draft_id: int, status: str = "processed"):
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE email_documents SET draft_id=%s, status=%s WHERE id=%s",
                (draft_id, status, doc_id),
            )
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning("_update_doc_draft: %s", e)


# ── IMAP helpers ──────────────────────────────────────────────────────────────

def _decode_header_str(value: str) -> str:
    parts = decode_header(value or "")
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def _extract_pdf_attachments(msg) -> list[dict]:
    """Return list of {filename, data} for supported attachments."""
    attachments = []
    for part in msg.walk():
        content_disp = part.get("Content-Disposition", "")
        filename = part.get_filename()
        if not filename:
            continue
        filename = _decode_header_str(filename)
        ext = os.path.splitext(filename.lower())[1]
        if ext not in ALLOWED_EXTS:
            continue
        if "attachment" in content_disp or ext in (".pdf", ".xlsx", ".xls"):
            data = part.get_payload(decode=True)
            if data:
                attachments.append({"filename": filename, "data": data})
    return attachments


def _extract_text_from_pdf(data: bytes) -> str:
    """Best-effort text extraction from PDF bytes."""
    try:
        import fitz
        doc = fitz.open(stream=data, filetype="pdf")
        pages = [doc[i].get_text() for i in range(min(len(doc), 10))]
        return "\n".join(pages).strip()
    except Exception:
        pass
    try:
        # fallback: raw bytes scan for readable text
        text = data.decode("latin-1", errors="replace")
        import re
        readable = re.findall(r'[\x20-\x7e\u10d0-\u10ff]{4,}', text)
        return " ".join(readable[:200])
    except Exception:
        return ""


# ── Public API ────────────────────────────────────────────────────────────────

def test_imap_connection(email_addr: str, app_password: str) -> dict:
    """Test IMAP credentials without storing them."""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(email_addr, app_password)
        mail.select("INBOX")
        mail.logout()
        return {"ok": True, "message": "კავშირი წარმატებულია"}
    except imaplib.IMAP4.error as e:
        return {"ok": False, "error": f"IMAP auth error: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def collect_tenant_inbox(tenant_id: str) -> dict:
    """
    Poll one tenant's inbox for unseen attachments.
    Saves documents to DB and triggers AI processing for each.
    Returns a summary dict.
    """
    from app.api.services.ai_processor import ai_process_document

    creds = get_tenant_email_credentials(tenant_id)
    if not creds:
        return {"status": "no_credentials", "tenant_id": tenant_id}

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(creds["email"], creds["app_password"])
        mail.select("INBOX")
    except Exception as e:
        log.error("IMAP login failed for tenant %s: %s", tenant_id, e)
        return {"status": "error", "error": str(e), "tenant_id": tenant_id}

    try:
        _, data = mail.search(None, "UNSEEN")
        msg_ids = data[0].split() if data[0] else []
    except Exception as e:
        mail.logout()
        return {"status": "error", "error": str(e), "tenant_id": tenant_id}

    processed = []
    errors = []

    for msg_id in msg_ids:
        try:
            uid = msg_id.decode()
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            raw = msg_data[0][1]
            msg = emaillib.message_from_bytes(raw)

            attachments = _extract_pdf_attachments(msg)
            if not attachments:
                continue

            for att in attachments:
                filename = att["filename"]
                file_data = att["data"]

                if _already_processed(tenant_id, uid, filename):
                    log.info("skip duplicate: %s / %s", tenant_id, filename)
                    continue

                raw_text = ""
                if filename.lower().endswith(".pdf"):
                    raw_text = _extract_text_from_pdf(file_data)

                doc_id = _save_email_document(tenant_id, uid, filename, file_data, raw_text)

                ai_result = await ai_process_document(
                    tenant_id=tenant_id,
                    doc_id=doc_id,
                    doc_text=raw_text or None,
                )

                if ai_result.get("ok"):
                    _update_doc_draft(doc_id, ai_result["draft_id"])
                    processed.append({
                        "filename": filename,
                        "draft_id": ai_result["draft_id"],
                        "model": ai_result.get("model"),
                        "confidence": ai_result.get("confidence"),
                    })
                else:
                    _update_doc_draft(doc_id, 0, "ai_failed")
                    errors.append({"filename": filename, "error": ai_result.get("error")})

            # Mark as seen after processing
            mail.store(msg_id, "+FLAGS", "\\Seen")

        except Exception as e:
            log.error("collect_tenant_inbox msg %s error: %s", msg_id, e)
            errors.append({"msg_id": msg_id.decode(), "error": str(e)})

    mail.logout()

    return {
        "status": "ok",
        "tenant_id": tenant_id,
        "processed": len(processed),
        "errors": len(errors),
        "drafts": processed,
        "error_details": errors,
    }


def get_all_active_tenants() -> list[str]:
    """Return list of tenant_ids that have active email credentials."""
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tenant_id FROM tenant_email_credentials WHERE active = TRUE"
            )
            rows = cur.fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception as e:
        log.warning("get_all_active_tenants: %s", e)
        return []
