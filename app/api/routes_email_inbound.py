"""app/api/routes_email_inbound.py
Dext-style dedicated submit email per tenant.

Each tenant gets a unique address:  {token}@{INBOUND_EMAIL_DOMAIN}
Email providers (SendGrid Inbound Parse, Mailgun Routes) POST to:
  POST /email-invoice/inbound

The handler:
  1. Parses `to` field → extracts token → finds tenant
  2. Saves attachments to email_documents
  3. Runs AI processing → creates journal drafts
  4. Returns 200 OK (both SendGrid and Mailgun expect 200)

Setup (done once by admin):
  - SendGrid: Inbound Parse → MX record for INBOUND_EMAIL_DOMAIN → webhook URL
  - Mailgun:  Routes → match_recipient(".*@INBOUND_EMAIL_DOMAIN") → forward webhook URL
  - Env var:  INBOUND_EMAIL_DOMAIN=mail.yourdomain.com
              INBOUND_WEBHOOK_SECRET=<optional shared secret>
"""
import json
import logging
import os
import re
import secrets

import psycopg2
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.api.authz import require_permission
from psycopg2.extras import RealDictCursor

from app.api.services.email_collector import (
    ALLOWED_EXTS,
    _already_processed,
    _extract_text_from_pdf,
    _save_email_document,
    _update_doc_draft,
    _get_db,
)

log = logging.getLogger(__name__)
router = APIRouter(tags=["email-inbound"])

INBOUND_EMAIL_DOMAIN = os.environ.get("INBOUND_EMAIL_DOMAIN", "mail.bridgehub.app")
INBOUND_WEBHOOK_SECRET = os.environ.get("INBOUND_WEBHOOK_SECRET", "")


# ── helpers ───────────────────────────────────────────────────────────────────

def _extract_token_from_to(to_header: str) -> str | None:
    """Extract token from 'something <token@domain>' or 'token@domain'."""
    addresses = re.findall(r'[\w.+-]+@[\w.-]+', to_header or "")
    for addr in addresses:
        local, domain = addr.split("@", 1)
        if domain.lower() == INBOUND_EMAIL_DOMAIN.lower():
            return local.lower()
    return None


def _find_tenant_by_token(token: str) -> str | None:
    try:
        conn = _get_db()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id FROM tenants WHERE submit_token = %s LIMIT 1",
                (token,),
            )
            row = cur.fetchone()
        conn.close()
        return row["id"] if row else None
    except Exception as e:
        log.warning("_find_tenant_by_token: %s", e)
        return None


def _get_or_create_submit_token(tenant_id: str) -> str:
    """Return existing submit_token or generate and save a new one."""
    conn = _get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT submit_token FROM tenants WHERE id = %s", (tenant_id,))
            row = cur.fetchone()
            if row and row.get("submit_token"):
                return row["submit_token"]
            token = secrets.token_hex(5)  # 10 hex chars, e.g. "a3f8c02e14"
            cur.execute(
                "UPDATE tenants SET submit_token = %s WHERE id = %s",
                (token, tenant_id),
            )
        conn.commit()
        return token
    except Exception as e:
        conn.rollback()
        log.error("_get_or_create_submit_token: %s", e)
        return secrets.token_hex(5)
    finally:
        conn.close()


def _submit_email_address(token: str) -> str:
    return f"{token}@{INBOUND_EMAIL_DOMAIN}"


# ── webhook endpoint ──────────────────────────────────────────────────────────

@router.post("/email-invoice/inbound", include_in_schema=False)
async def email_inbound_webhook(request: Request):
    """
    Receives inbound email from SendGrid Inbound Parse or Mailgun Routes.
    No auth header required — secured by token in To address + optional shared secret.
    """
    # Optional shared-secret header check (SendGrid sends X-Webhook-Secret, Mailgun doesn't)
    require_permission(request, "settings:write")
    if INBOUND_WEBHOOK_SECRET:
        incoming = (
            request.headers.get("X-Webhook-Secret")
            or request.headers.get("X-Inbound-Secret")
            or ""
        )
        if not secrets.compare_digest(incoming, INBOUND_WEBHOOK_SECRET):
            log.warning("inbound webhook: bad secret")
            return JSONResponse({"ok": False}, status_code=403)

    try:
        form = await request.form()
    except Exception as e:
        log.error("inbound webhook: cannot parse form: %s", e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    to_header = form.get("to") or form.get("recipient") or ""
    from_addr = form.get("from") or form.get("sender") or "unknown"
    subject   = form.get("subject") or "(no subject)"
    body_text = form.get("text") or form.get("body-plain") or ""

    token = _extract_token_from_to(to_header)
    if not token:
        log.warning("inbound: no matching token in To=%r", to_header)
        return JSONResponse({"ok": False, "error": "unknown recipient"}, status_code=200)

    tenant_id = _find_tenant_by_token(token)
    if not tenant_id:
        log.warning("inbound: token %r not found in DB", token)
        return JSONResponse({"ok": False, "error": "tenant not found"}, status_code=200)

    log.info("inbound email → tenant=%s from=%s subject=%r", tenant_id, from_addr, subject)

    # Collect attachments — SendGrid numbers them attachment1, attachment2...
    # Mailgun uses 'attachment-1', 'attachment-2'...
    attachments = []
    for key in form:
        if not key.startswith("attachment"):
            continue
        val = form[key]
        if hasattr(val, "filename") and val.filename:
            ext = os.path.splitext(val.filename.lower())[1]
            if ext in ALLOWED_EXTS:
                data = await val.read()
                attachments.append({"filename": val.filename, "data": data})

    if not attachments:
        log.info("inbound: no attachments from %s — skipping", from_addr)
        return JSONResponse({"ok": True, "drafts": [], "note": "no attachments"})

    from app.api.services.ai_processor import ai_process_document

    processed = []
    errors = []
    # Use subject+from as a stable UID for deduplication
    msg_uid = f"inbound:{subject[:60]}:{from_addr}"

    for att in attachments:
        filename = att["filename"]
        file_data = att["data"]

        if _already_processed(tenant_id, msg_uid, filename):
            log.info("inbound: skip duplicate %s / %s", tenant_id, filename)
            continue

        raw_text = ""
        if filename.lower().endswith(".pdf"):
            raw_text = _extract_text_from_pdf(file_data)

        doc_id = _save_email_document(tenant_id, msg_uid, filename, file_data, raw_text)

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
                "confidence": ai_result.get("confidence"),
            })
        else:
            _update_doc_draft(doc_id, 0, "ai_failed")
            errors.append({"filename": filename, "error": ai_result.get("error")})

    log.info("inbound: tenant=%s processed=%d errors=%d", tenant_id, len(processed), len(errors))
    return JSONResponse({
        "ok": True,
        "tenant_id": tenant_id,
        "drafts_created": len(processed),
        "drafts": processed,
        "errors": errors,
    })


# ── management endpoints (authenticated) ─────────────────────────────────────

@router.get("/email-invoice/submit-address")
async def get_submit_address(request: Request):
    """Return this tenant's dedicated invoice submission email address."""
    require_permission(request, "settings:write")
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        return JSONResponse({"ok": False, "error": "not authenticated"}, status_code=401)
    token = _get_or_create_submit_token(tenant_id)
    address = _submit_email_address(token)
    return JSONResponse({
        "ok": True,
        "data": {
            "submit_email": address,
            "token": token,
            "domain": INBOUND_EMAIL_DOMAIN,
            "instructions": (
                f"გამოგზავნეთ ინვოისი {address}-ზე. "
                "PDF ან Excel დანართები ავტომატურად გატარდება."
            ),
        }
    })


@router.post("/email-invoice/regenerate-token")
async def regenerate_submit_token(request: Request):
    """Generate a new submit token (invalidates old address)."""
    require_permission(request, "settings:write")
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        return JSONResponse({"ok": False, "error": "not authenticated"}, status_code=401)
    new_token = secrets.token_hex(5)
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tenants SET submit_token = %s WHERE id = %s",
                (new_token, tenant_id),
            )
        conn.commit()
        conn.close()
    except Exception as e:
        log.error("regenerate_submit_token: %s", e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    return JSONResponse({
        "ok": True,
        "data": {"submit_email": _submit_email_address(new_token), "token": new_token}
    })