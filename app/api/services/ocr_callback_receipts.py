"""Tenant-scoped durable deduplication for signed OCR worker callbacks."""

import hashlib
import json
from datetime import datetime, timezone

from app.api.db import _q, get_conn, require_current_tenant_id


async def register_dispatch(*, tenant_id: str, doc_id: int, job_id: str) -> dict | None:
    """Persist one dispatch claim before network I/O; serialize per document row."""
    require_current_tenant_id(tenant_id)
    async with get_conn() as conn:
        document = await conn.fetchrow(_q("""
            SELECT id, gcs_path, status, ocr_worker_job_id
              FROM processed_documents
             WHERE id=%s AND tenant_id=%s
             FOR UPDATE
        """), doc_id, tenant_id)
        if not document or not document["gcs_path"] or document["status"] != "processing":
            return None

        active_job_id = document["ocr_worker_job_id"]
        if active_job_id:
            active = await conn.fetchrow(_q("""
                SELECT state, lease_until FROM ocr_callback_receipts
                 WHERE tenant_id=%s AND job_id=%s
            """), tenant_id, active_job_id)
            if (
                active
                and active["state"] in {"dispatched", "processing"}
                and active["lease_until"] is not None
                and active["lease_until"] > datetime.now(timezone.utc)
            ):
                return {"send": False, "job_id": active_job_id, "gcs_path": document["gcs_path"]}

        await conn.execute(_q("""
            UPDATE processed_documents SET ocr_worker_job_id=%s
             WHERE id=%s AND tenant_id=%s
        """), job_id, doc_id, tenant_id)
        await conn.execute(_q("""
            INSERT INTO ocr_callback_receipts
                (tenant_id, job_id, document_id, job_type, state, lease_until)
            VALUES (%s, %s, %s, 'ocr', 'dispatched', NOW() + INTERVAL '30 minutes')
        """), tenant_id, job_id, doc_id)
        return {"send": True, "job_id": job_id, "gcs_path": document["gcs_path"]}


async def accept_callback_result(
    *, tenant_id: str, job_id: str, doc_id: int, job_type: str,
    status: str, raw_text: str, method: str,
) -> str:
    """Return accepted/duplicate/conflict; receipt and first document write are atomic."""
    require_current_tenant_id(tenant_id)
    canonical = json.dumps(
        {
            "tenant_id": tenant_id,
            "job_id": job_id,
            "doc_id": int(doc_id),
            "job_type": job_type,
            "status": status,
            "raw_text": raw_text if status == "ok" else "",
            "method": method if status == "ok" else "",
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    result_hash = hashlib.sha256(canonical).hexdigest()

    async with get_conn() as conn:
        receipt = await conn.fetchrow(_q("""
            SELECT document_id, job_type, result_sha256, state, lease_until
              FROM ocr_callback_receipts
             WHERE tenant_id=%s AND job_id=%s
             FOR UPDATE
        """), tenant_id, job_id)
        if not receipt or receipt["document_id"] != doc_id or receipt["job_type"] != job_type:
            return "conflict"

        if receipt["state"] == "dispatched":
            if (
                receipt["lease_until"] is None
                or receipt["lease_until"] <= datetime.now(timezone.utc)
            ):
                return "conflict"
            await conn.execute(_q("""
                UPDATE ocr_callback_receipts
                   SET result_sha256=%s, state='processing',
                       lease_until=NOW() + INTERVAL '10 minutes'
                 WHERE tenant_id=%s AND job_id=%s
            """), result_hash, tenant_id, job_id)
            if status == "ok":
                document = await conn.fetchrow(_q("""
                    UPDATE processed_documents
                       SET raw_text=%s, extraction_method=%s
                     WHERE id=%s AND tenant_id=%s
                 RETURNING id
                """), raw_text, method, doc_id, tenant_id)
            else:
                document = await conn.fetchrow(_q("""
                    UPDATE processed_documents
                       SET status='ocr_failed'
                     WHERE id=%s AND tenant_id=%s
                 RETURNING id
                """), doc_id, tenant_id)
            if not document:
                raise LookupError("OCR callback document is unavailable")
            return "accepted"

        if (
            receipt["result_sha256"] is None
            or receipt["result_sha256"].strip() != result_hash
        ):
            await conn.execute(_q("""
                UPDATE ocr_callback_receipts
                   SET conflict_attempts=conflict_attempts + 1,
                       last_conflict_at=NOW()
                 WHERE tenant_id=%s AND job_id=%s
            """), tenant_id, job_id)
            return "conflict"
        if receipt["state"] == "completed":
            await conn.execute(_q("""
                UPDATE ocr_callback_receipts
                   SET duplicate_attempts=duplicate_attempts + 1,
                       last_duplicate_at=NOW()
                 WHERE tenant_id=%s AND job_id=%s
            """), tenant_id, job_id)
            return "duplicate"

        reclaimed = await conn.fetchrow(_q("""
            UPDATE ocr_callback_receipts
               SET lease_until=NOW() + INTERVAL '10 minutes',
                   duplicate_attempts=duplicate_attempts + 1,
                   last_duplicate_at=NOW()
             WHERE tenant_id=%s AND job_id=%s AND state='processing'
               AND lease_until < NOW()
         RETURNING job_id
        """), tenant_id, job_id)
        if not reclaimed:
            await conn.execute(_q("""
                UPDATE ocr_callback_receipts
                   SET duplicate_attempts=duplicate_attempts + 1,
                       last_duplicate_at=NOW()
                 WHERE tenant_id=%s AND job_id=%s
            """), tenant_id, job_id)
        return "accepted" if reclaimed else "duplicate"


async def complete_callback(tenant_id: str, job_id: str) -> None:
    require_current_tenant_id(tenant_id)
    async with get_conn() as conn:
        receipt = await conn.fetchrow(_q("""
            UPDATE ocr_callback_receipts
               SET state='completed', lease_until=NULL, completed_at=NOW()
             WHERE tenant_id=%s AND job_id=%s AND state='processing'
         RETURNING document_id
        """), tenant_id, job_id)
        if receipt:
            await conn.execute(_q("""
                UPDATE processed_documents SET ocr_worker_job_id=NULL
                 WHERE id=%s AND tenant_id=%s AND ocr_worker_job_id=%s
            """), receipt["document_id"], tenant_id, job_id)
