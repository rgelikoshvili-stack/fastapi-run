"""app/api/services/worker_client.py
Cloud Run → Hetzner job dispatch.

Job flow:
  1. Cloud Run calls dispatch_job() with job type + GCS path
  2. Hetzner worker receives POST /worker/job
  3. Worker downloads file from GCS, processes it, POSTs result back
  4. Cloud Run receives result at POST /worker/result

Environment variables required on Cloud Run:
  HETZNER_WORKER_URL   = https://<hetzner-ip>/worker   (or http if internal)
  HETZNER_WORKER_TOKEN = <shared-secret>               (min 32 chars)
"""
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Optional

import httpx

log = logging.getLogger(__name__)

WORKER_URL   = os.environ.get("HETZNER_WORKER_URL", "").rstrip("/")
WORKER_TOKEN = os.environ.get("HETZNER_WORKER_TOKEN", "")

_TIMEOUT = 10.0  # seconds — fire-and-forget; worker calls back async
_OCR_CALLBACK_AUDIENCE = "bridge-hub-ocr-callback"


def _sign_payload(body: bytes) -> str:
    """HMAC-SHA256 signature so worker verifies requests come from Cloud Run."""
    return hmac.new(WORKER_TOKEN.encode(), body, hashlib.sha256).hexdigest()


def worker_available() -> bool:
    return bool(WORKER_URL and WORKER_TOKEN)


def create_callback_token(
    *, tenant_id: str, doc_id: int, job_type: str, job_id: Optional[str] = None
) -> str:
    """Create a server-authenticated tenant/job claim for the OCR callback."""
    from app.api.db import require_current_tenant_id
    import jwt
    from app.api.services.auth_service import ALGORITHM, _get_secret_key

    trusted_tenant_id = require_current_tenant_id(tenant_id)
    now = datetime.now(timezone.utc)
    return jwt.encode({
        "type": "worker_job",
        "purpose": "ocr_callback",
        "audience": _OCR_CALLBACK_AUDIENCE,
        "job_id": job_id or uuid4().hex,
        "tenant_id": trusted_tenant_id,
        "doc_id": int(doc_id),
        "job_type": job_type,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp()),
    }, _get_secret_key(), algorithm=ALGORITHM)


def verify_callback_token(token: str) -> Optional[dict]:
    """Verify a Bridge Hub-signed job token; worker HMAC alone is not tenant authority."""
    if not isinstance(token, str) or not token:
        return None
    from app.api.db import _validate_tenant_id
    from app.api.services.auth_service import verify_token

    claims = verify_token(token, expected_type="worker_job")
    if not claims or claims.get("purpose") != "ocr_callback":
        return None
    try:
        _validate_tenant_id(claims.get("tenant_id"))
        claims["doc_id"] = int(claims["doc_id"])
    except (KeyError, TypeError, ValueError):
        return None
    if (
        not claims.get("job_id")
        or not claims.get("job_type")
        or claims.get("audience") != _OCR_CALLBACK_AUDIENCE
    ):
        return None
    return claims


def authorize_callback_payload(data: dict) -> Optional[dict]:
    """Bind callback hints to immutable claims signed by Bridge Hub at dispatch."""
    if not isinstance(data, dict):
        return None
    claims = verify_callback_token(data.get("callback_token"))
    if not claims:
        return None
    try:
        callback_doc_id = int(data.get("doc_id"))
    except (TypeError, ValueError):
        return None
    if (
        callback_doc_id != claims["doc_id"]
        or data.get("job_type") != claims["job_type"]
        or data.get("job_id") != claims["job_id"]
    ):
        return None
    tenant_hint = data.get("tenant_id")
    if tenant_hint is not None and tenant_hint != claims["tenant_id"]:
        return None
    return claims


async def dispatch_job(
    job_type: str,
    tenant_id: str,
    gcs_path: str,
    doc_id: int,
    callback_doc_id: Optional[int] = None,
    extra: Optional[dict] = None,
) -> dict:
    """
    Send a job to the Hetzner worker asynchronously.
    Returns {"dispatched": True/False, "reason": str}.

    job_type options:
      "ocr"          — heavy OCR on scanned PDF (Tesseract Georgian)
      "ocr_vision"   — vision-LLM fallback for low-quality scans
      "pdf_split"    — split multi-page PDF into individual pages
    """
    if not worker_available():
        return {"dispatched": False, "reason": "HETZNER_WORKER_URL not configured"}

    job_id = uuid4().hex
    callback_document_id = callback_doc_id if callback_doc_id is not None else doc_id
    callback_token = create_callback_token(
        tenant_id=tenant_id,
        doc_id=callback_document_id,
        job_type=job_type,
        job_id=job_id,
    )
    payload = {
        **(extra or {}),
        "job_type": job_type,
        "tenant_id": tenant_id,
        "gcs_path": gcs_path,
        "doc_id": doc_id,
        "callback_doc_id": callback_document_id,
        "job_id": job_id,
        "callback_token": callback_token,
        "issued_at": int(time.time()),
    }
    body = json.dumps(payload, ensure_ascii=False).encode()
    sig  = _sign_payload(body)

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{WORKER_URL}/job",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Worker-Signature": sig,
                },
            )
        if resp.status_code == 202:
            log.info("action=worker_job_dispatched type=%s doc=%s tenant=%s", job_type, doc_id, tenant_id)
            # The Bridge Hub-generated ID is the signed callback identity. A
            # worker response must not replace that authoritative identifier.
            return {"dispatched": True, "job_id": job_id}
        # Worker error bodies may echo the short-lived signed callback token.
        log.warning("action=worker_dispatch_failed status=%d", resp.status_code)
        return {"dispatched": False, "reason": f"worker HTTP {resp.status_code}"}
    except Exception:
        # Exception strings can include request payloads; callback_token is a
        # short-lived bearer credential and must not be written to logs/output.
        log.warning("action=worker_dispatch_error")
        return {"dispatched": False, "reason": "worker dispatch failed"}


def verify_worker_signature(body: bytes, signature: str) -> bool:
    """Used by routes_worker.py to verify results sent back from Hetzner."""
    if not WORKER_TOKEN:
        return False
    expected = _sign_payload(body)
    return hmac.compare_digest(expected, signature or "")
