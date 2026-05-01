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
from typing import Optional

import httpx

log = logging.getLogger(__name__)

WORKER_URL   = os.environ.get("HETZNER_WORKER_URL", "").rstrip("/")
WORKER_TOKEN = os.environ.get("HETZNER_WORKER_TOKEN", "")

_TIMEOUT = 10.0  # seconds — fire-and-forget; worker calls back async


def _sign_payload(body: bytes) -> str:
    """HMAC-SHA256 signature so worker verifies requests come from Cloud Run."""
    return hmac.new(WORKER_TOKEN.encode(), body, hashlib.sha256).hexdigest()


def worker_available() -> bool:
    return bool(WORKER_URL and WORKER_TOKEN)


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

    payload = {
        "job_type": job_type,
        "tenant_id": tenant_id,
        "gcs_path": gcs_path,
        "doc_id": doc_id,
        "callback_doc_id": callback_doc_id or doc_id,
        "issued_at": int(time.time()),
        **(extra or {}),
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
            return {"dispatched": True, "job_id": resp.json().get("job_id")}
        log.warning("action=worker_dispatch_failed status=%d body=%s", resp.status_code, resp.text[:200])
        return {"dispatched": False, "reason": f"worker HTTP {resp.status_code}"}
    except Exception as e:
        log.warning("action=worker_dispatch_error err=%s", e)
        return {"dispatched": False, "reason": str(e)}


def verify_worker_signature(body: bytes, signature: str) -> bool:
    """Used by routes_worker.py to verify results sent back from Hetzner."""
    if not WORKER_TOKEN:
        return False
    expected = _sign_payload(body)
    return hmac.compare_digest(expected, signature or "")
