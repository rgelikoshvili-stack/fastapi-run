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

from fastapi import APIRouter, Request

from app.api.db import get_db
from app.api.response_utils import ok_response, error_response
from app.api.services.worker_client import verify_worker_signature

router = APIRouter(prefix="/worker", tags=["worker"])
log = logging.getLogger(__name__)


@router.post("/result")
async def worker_result(request: Request):
    """
    Called by Hetzner worker when a job completes.
    Body (JSON):
      {
        "job_type":   "ocr",
        "tenant_id":  "default",
        "doc_id":     123,
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

    tenant_id = data.get("tenant_id", "default")
    doc_id    = data.get("doc_id")
    status    = data.get("status", "failed")
    job_type  = data.get("job_type", "ocr")

    log.info("action=worker_result type=%s doc=%s tenant=%s status=%s",
             job_type, doc_id, tenant_id, status)

    if not doc_id:
        return error_response("doc_id required", "BAD_REQUEST")

    if status == "ok" and job_type == "ocr":
        raw_text = (data.get("raw_text") or "")[:10000]
        method   = data.get("method", "hetzner_ocr")
        _update_doc_text(tenant_id, doc_id, raw_text, method)
        # Re-trigger the document pipeline with the new text
        _retrigger_pipeline(tenant_id, doc_id)

    elif status == "failed":
        _mark_doc_status(tenant_id, doc_id, "ocr_failed")

    return ok_response("result received", {"doc_id": doc_id, "status": status})


def _update_doc_text(tenant_id: str, doc_id: int, raw_text: str, method: str):
    try:
        conn = get_db(tenant_id)
        cur  = conn.cursor()
        try:
            cur.execute(
                "UPDATE processed_documents SET raw_text=%s, extraction_method=%s WHERE id=%s AND tenant_id=%s",
                (raw_text, method, doc_id, tenant_id),
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        log.error("_update_doc_text doc=%s err=%s", doc_id, e)


def _mark_doc_status(tenant_id: str, doc_id: int, status: str):
    try:
        conn = get_db(tenant_id)
        cur  = conn.cursor()
        try:
            cur.execute(
                "UPDATE processed_documents SET status=%s WHERE id=%s AND tenant_id=%s",
                (status, doc_id, tenant_id),
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        log.error("_mark_doc_status doc=%s err=%s", doc_id, e)


def _retrigger_pipeline(tenant_id: str, doc_id: int):
    """After OCR completes on Hetzner, run the extract→classify→draft pipeline."""
    try:
        import asyncio
        from app.api.db import get_db as _get_db

        conn = _get_db(tenant_id)
        cur  = conn.cursor()
        try:
            cur.execute(
                "SELECT file_content, mime_type, file_name, gcs_path FROM processed_documents "
                "WHERE id=%s AND tenant_id=%s",
                (doc_id, tenant_id),
            )
            row = cur.fetchone()
        finally:
            cur.close()
            conn.close()

        if not row:
            log.warning("_retrigger_pipeline: doc %s not found", doc_id)
            return

        file_content, mime_type, file_name, gcs_path = row

        # Get file bytes
        if gcs_path:
            from app.api.services.storage_service import safe_download
            file_bytes = safe_download(gcs_path, file_content)
        else:
            file_bytes = bytes(file_content) if file_content else None

        if not file_bytes:
            log.warning("_retrigger_pipeline: no bytes for doc %s", doc_id)
            return

        from app.api.routes_documents import _process_document_background
        asyncio.create_task(
            _process_document_background(doc_id, tenant_id, file_bytes, mime_type or "application/pdf", file_name or "document")
        )
        log.info("action=worker_pipeline_retriggered doc=%s tenant=%s", doc_id, tenant_id)
    except Exception as e:
        log.error("_retrigger_pipeline doc=%s err=%s", doc_id, e)
