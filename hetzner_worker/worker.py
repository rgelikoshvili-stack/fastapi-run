"""hetzner_worker/worker.py
Bridge Hub — Hetzner OCR Worker

Runs on Hetzner as a small FastAPI server (uvicorn).
Accepts jobs from Cloud Run, processes them (OCR), posts results back.

Setup on Hetzner:
  pip install fastapi uvicorn[standard] pytesseract pdf2image pymupdf google-cloud-storage httpx
  CLOUD_RUN_URL=https://fastapi-run-oobzrmikna-ew.a.run.app \
  WORKER_TOKEN=<same-secret-as-cloud-run> \
  GCS_BUCKET_NAME=<bucket> \
  uvicorn worker:app --host 0.0.0.0 --port 8080

Firewall: allow only Cloud Run egress IP range → port 8080
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import tempfile
import time
from typing import Optional

import httpx
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")

CLOUD_RUN_URL = os.environ["CLOUD_RUN_URL"].rstrip("/")
WORKER_TOKEN  = os.environ["WORKER_TOKEN"]
GCS_BUCKET    = os.environ.get("GCS_BUCKET_NAME", "")

app = FastAPI(title="BridgeHub Hetzner Worker", docs_url=None, redoc_url=None)


# ── Signature helpers ────────────────────────────────────────────────────────

def _sign(body: bytes) -> str:
    return hmac.new(WORKER_TOKEN.encode(), body, hashlib.sha256).hexdigest()


def _verify(body: bytes, sig: str) -> bool:
    return hmac.compare_digest(_sign(body), sig or "")


# ── GCS helpers ──────────────────────────────────────────────────────────────

def _download_from_gcs(gcs_path: str) -> bytes:
    from google.cloud import storage
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)
    return bucket.blob(gcs_path).download_as_bytes()


# ── OCR ───────────────────────────────────────────────────────────────────────

def _ocr_pdf(file_bytes: bytes) -> tuple[str, str]:
    """Returns (text, method). Tries PyMuPDF native first, then Tesseract."""
    # 1. Native PDF text
    try:
        import fitz
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages = [doc[i].get_text() for i in range(len(doc))]
        text = "\n\n".join(pages).strip()
        if len(text) >= 100:
            return text, "native_pdf"
    except Exception as e:
        log.warning("native_pdf failed: %s", e)

    # 2. Tesseract OCR (Georgian + English + Russian)
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
        images = convert_from_bytes(file_bytes, dpi=200)
        pages = []
        for img in images[:10]:
            t = pytesseract.image_to_string(img, lang="kat+eng+rus", config="--oem 1 --psm 3")
            pages.append(t)
        text = "\n\n".join(pages).strip()
        return text, "tesseract_pdf"
    except Exception as e:
        log.error("tesseract failed: %s", e)
        return "", "failed"


def _ocr_image(file_bytes: bytes, mime_type: str = "image/png") -> tuple[str, str]:
    try:
        import pytesseract
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(file_bytes))
        text = pytesseract.image_to_string(img, lang="kat+eng+rus")
        return text.strip(), "tesseract_image"
    except Exception as e:
        log.error("image ocr failed: %s", e)
        return "", "failed"


# ── Callback to Cloud Run ─────────────────────────────────────────────────────

async def _post_result(result: dict):
    body = json.dumps(result, ensure_ascii=False).encode()
    sig  = _sign(body)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{CLOUD_RUN_URL}/worker/result",
                content=body,
                headers={"Content-Type": "application/json", "X-Worker-Signature": sig},
            )
        log.info("callback status=%d doc=%s", resp.status_code, result.get("doc_id"))
    except Exception as e:
        log.error("callback failed doc=%s err=%s", result.get("doc_id"), e)


# ── Job processor ─────────────────────────────────────────────────────────────

async def _process_job(job: dict):
    job_type  = job.get("job_type", "ocr")
    tenant_id = job.get("tenant_id", "default")
    doc_id    = job.get("doc_id")
    gcs_path  = job.get("gcs_path", "")

    log.info("processing job_type=%s doc=%s tenant=%s", job_type, doc_id, tenant_id)

    try:
        file_bytes = _download_from_gcs(gcs_path)
    except Exception as e:
        await _post_result({"job_type": job_type, "tenant_id": tenant_id,
                            "doc_id": doc_id, "status": "failed", "error": str(e)})
        return

    if job_type in ("ocr", "ocr_pdf"):
        text, method = _ocr_pdf(file_bytes)
    elif job_type == "ocr_image":
        text, method = _ocr_image(file_bytes)
    else:
        text, method = _ocr_pdf(file_bytes)

    await _post_result({
        "job_type":  job_type,
        "tenant_id": tenant_id,
        "doc_id":    doc_id,
        "status":    "ok" if text else "failed",
        "raw_text":  text[:10000],
        "method":    method,
    })


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"ok": True, "worker": "hetzner", "ts": int(time.time())}


@app.post("/worker/job", status_code=202)
async def receive_job(request: Request, background_tasks: BackgroundTasks):
    """Receive a job from Cloud Run."""
    body = await request.body()
    sig  = request.headers.get("X-Worker-Signature", "")

    if not _verify(body, sig):
        return JSONResponse(status_code=401, content={"ok": False, "error": "bad signature"})

    try:
        job = json.loads(body)
    except Exception:
        return JSONResponse(status_code=400, content={"ok": False, "error": "invalid JSON"})

    job_id = f"{job.get('doc_id')}_{int(time.time())}"
    background_tasks.add_task(_process_job, job)
    log.info("job accepted job_id=%s type=%s doc=%s", job_id, job.get("job_type"), job.get("doc_id"))
    return {"ok": True, "job_id": job_id, "status": "queued"}
