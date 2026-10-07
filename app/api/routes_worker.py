"""app/api/routes_worker.py
Receives job results POSTed back from the Hetzner worker.

Endpoint: POST /worker/result
Auth: HMAC-SHA256 signature in X-Worker-Signature header (same shared token).

Result flow:
  Hetzner worker finishes OCR → POST /worker/result →
  update processed_documents.raw_text → re-trigger pipeline
"""
import json
import logging
import asyncio

from fastapi import APIRouter, Request

from app.api.db import get_conn, _q, tenant_db_context
from app.api.response_utils import ok_response, error_response, http_error
from app.api.services.worker_client import verify_worker_signature, authorize_callback_payload
from app.api.services.ocr_callback_receipts import accept_callback_result, complete_callback

router = APIRouter(prefix="/worker", tags=["worker"])
log = logging.getLogger(__name__)


@router.post("/result")
async def worker_result(request: Request):
    """
    Called by Hetzner worker when a job completes.
    Body (JSON):
      {
        "job_type":   "ocr",
        "tenant_id":  "server-signed tenant claim",
        "doc_id":     123,
        "callback_token": "Bridge Hub-signed job authorization",
        "status":     "ok" | "failed",
        "raw_text":   "...",    # for OCR jobs
        "method":     "tesseract_pdf",
        "error":      "..."     # if status == "failed"
      }
    """
    body = await request.body()
    sig  = request.headers.get("X-Worker-Signature", "")

    if not verify_worker_signature(body, sig):
        log.warning("action=worker_result_rejected reason=bad_signature")
        return error_response("Invalid signature", "UNAUTHORIZED")

    try:
        data = json.loads(body)
    except Exception:
        return error_response("Invalid JSON", "BAD_REQUEST")
    if not isinstance(data, dict):
        return error_response("Invalid worker result", "BAD_REQUEST")

    claims = authorize_callback_payload(data)
    if not claims:
        log.warning("action=worker_result_rejected reason=job_claim_mismatch")
        return error_response("Invalid internal job authorization", "UNAUTHORIZED")

    tenant_id = claims["tenant_id"]
    doc_id    = claims["doc_id"]
    status    = data.get("status")
    job_type  = data.get("job_type")
    if status not in {"ok", "failed"} or job_type != "ocr":
        return error_response("Invalid worker result", "BAD_REQUEST")
    job_id = claims["job_id"]
    raw_text = (data.get("raw_text") or "")[:10000] if status == "ok" else ""
    method = str(data.get("method") or "hetzner_ocr") if status == "ok" else ""

    log.info("action=worker_result type=%s doc=%s tenant=%s status=%s",
             job_type, doc_id, tenant_id, status)

    async with tenant_db_context(tenant_id):
        try:
            receipt = await accept_callback_result(
                tenant_id=tenant_id,
                job_id=job_id,
                doc_id=doc_id,
                job_type=job_type,
                status=status,
                raw_text=raw_text,
                method=method,
            )
        except LookupError:
            return error_response("OCR job is unavailable", "NOT_FOUND")
        except Exception:
            log.warning("action=worker_result_receipt_failed job=%s", job_id)
            return error_response("Unable to accept worker result", "RETRY")

        if receipt == "conflict":
            log.warning("action=worker_result_conflict job=%s tenant=%s", job_id, tenant_id)
            return http_error(409, "Conflicting callback result", "CALLBACK_CONFLICT")
        if receipt == "duplicate":
            log.info("action=worker_result_duplicate job=%s tenant=%s", job_id, tenant_id)
            return ok_response("duplicate result acknowledged", {
                "doc_id": doc_id, "status": "duplicate",
            })

        if status == "failed":
            await complete_callback(tenant_id, job_id)
        else:
            asyncio.create_task(
                _process_and_complete(tenant_id, doc_id, job_id, raw_text, method)
            )

    return ok_response("result received", {"doc_id": doc_id, "status": status})


async def _mark_doc_status(tenant_id: str, doc_id: int, status: str):
    async with get_conn() as conn:
        await conn.execute(_q(
            "UPDATE processed_documents SET status=%s WHERE id=%s AND tenant_id=%s"
        ), status, doc_id, tenant_id)


async def _retrigger_pipeline(tenant_id: str, doc_id: int, raw_text: str, method: str):
    """After OCR completes on Hetzner, run the extract→classify→draft pipeline."""
    try:
        import asyncio
        async with get_conn() as conn:
            row = await conn.fetchrow(_q(
            "SELECT mime_type, file_name FROM processed_documents "
                "WHERE id=%s AND tenant_id=%s"
            ), doc_id, tenant_id)

        if not row:
            log.warning("_retrigger_pipeline: doc %s not found", doc_id)
            return

        mime_type    = row["mime_type"]
        file_name    = row["file_name"]
        from app.api.routes_documents import _process_document_background
        succeeded = await _process_document_background(
            doc_id,
            tenant_id,
            b"",
            mime_type or "application/pdf",
            file_name or "document",
            ocr_result={"text": raw_text, "method": method, "pages_count": 0},
        )
        if not succeeded:
            return False
        log.info("action=worker_pipeline_retriggered doc=%s tenant=%s", doc_id, tenant_id)
        return True
    except Exception as e:
        log.error("_retrigger_pipeline doc=%s err=%s", doc_id, e)
        return False


async def _process_and_complete(
    tenant_id: str, doc_id: int, job_id: str, raw_text: str, method: str
):
    try:
        async with tenant_db_context(tenant_id):
            succeeded = await _retrigger_pipeline(tenant_id, doc_id, raw_text, method)
            if succeeded:
                await complete_callback(tenant_id, job_id)
    except Exception:
        log.warning("action=worker_result_processing_failed job=%s tenant=%s", job_id, tenant_id)
