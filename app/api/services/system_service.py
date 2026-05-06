from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, error_response


async def get_system_summary_service(tenant_id: str = "default"):
    try:
        async with get_conn() as conn:
            bank_files_processed = await conn.fetchval(
                "SELECT COUNT(*) FROM processed_bank_files") or 0

            transactions_total = await conn.fetchval(_q(
                "SELECT COUNT(*) FROM journal_drafts WHERE tenant_id = %s"
            ), tenant_id) or 0

            rows = await conn.fetch(_q(
                "SELECT status, COUNT(*) AS count FROM journal_drafts WHERE tenant_id = %s GROUP BY status"
            ), tenant_id)
            status_counts = {"drafted": 0, "pending_approval": 0, "approved": 0, "rejected": 0}
            for r in rows:
                status_counts[r["status"]] = r["count"]

            fs = dict(await conn.fetchrow("""
                SELECT
                    COALESCE(SUM(total_rows), 0) AS total_rows_sum,
                    COALESCE(SUM(drafted_count), 0) AS drafted_sum,
                    COALESCE(SUM(review_count), 0) AS review_sum,
                    COALESCE(SUM(failed_count), 0) AS failed_sum,
                    COALESCE(SUM(inserted_count), 0) AS inserted_sum,
                    COALESCE(SUM(skipped_duplicates), 0) AS skipped_sum
                FROM processed_bank_files
            """) or {})
    except Exception as e:
        return error_response("System summary failed", "SYSTEM_SUMMARY_ERROR", str(e))

    return ok_response("System summary", {
        "tenant_id": tenant_id,
        "bank_files_processed": bank_files_processed,
        "transactions_total": transactions_total,
        "drafted": status_counts.get("drafted", 0),
        "pending_approval": status_counts.get("pending_approval", 0),
        "approved": status_counts.get("approved", 0),
        "rejected": status_counts.get("rejected", 0),
        "duplicates_skipped": fs.get("skipped_sum") or 0,
        "file_stats": {
            "total_rows_sum": fs.get("total_rows_sum") or 0,
            "drafted_sum": fs.get("drafted_sum") or 0,
            "review_sum": fs.get("review_sum") or 0,
            "failed_sum": fs.get("failed_sum") or 0,
            "inserted_sum": fs.get("inserted_sum") or 0,
            "skipped_sum": fs.get("skipped_sum") or 0,
        },
    })


async def get_system_overview_service(tenant_id: str = "default"):
    try:
        async with get_conn() as conn:
            drafts_summary = dict(await conn.fetchrow(_q("""
                SELECT
                    COUNT(*) AS total_drafts,
                    COUNT(*) FILTER (WHERE status = 'drafted') AS drafted_count,
                    COUNT(*) FILTER (WHERE status = 'approved') AS approved_count,
                    COUNT(*) FILTER (WHERE status = 'rejected') AS rejected_count,
                    COUNT(*) FILTER (WHERE review_required = TRUE) AS review_required_count
                FROM journal_drafts WHERE tenant_id = %s
            """), tenant_id) or {})

            bank_files_summary = dict(await conn.fetchrow("""
                SELECT
                    COUNT(*) AS total_bank_files,
                    COALESCE(SUM(total_rows), 0) AS total_rows_sum,
                    COALESCE(SUM(drafted_count), 0) AS drafted_sum,
                    COALESCE(SUM(review_count), 0) AS review_sum,
                    COALESCE(SUM(failed_count), 0) AS failed_sum,
                    COALESCE(SUM(inserted_count), 0) AS inserted_sum,
                    COALESCE(SUM(skipped_duplicates), 0) AS duplicates_skipped
                FROM processed_bank_files
            """) or {})

            status_breakdown = [dict(r) for r in await conn.fetch(_q("""
                SELECT status, COUNT(*) AS count FROM journal_drafts
                WHERE tenant_id = %s GROUP BY status ORDER BY status
            """), tenant_id)]

            approval_queue_count = await conn.fetchval(_q("""
                SELECT COUNT(*) FROM journal_drafts
                WHERE tenant_id = %s AND status = 'drafted' AND review_required = TRUE
            """), tenant_id) or 0

            latest_bank_files = [dict(r) for r in await conn.fetch("""
                SELECT id, filename, file_hash, source_type, total_rows,
                       drafted_count, review_count, failed_count,
                       inserted_count, skipped_duplicates, created_at
                FROM processed_bank_files
                ORDER BY created_at DESC, id DESC LIMIT 5
            """)]

            latest_drafts = [dict(r) for r in await conn.fetch(_q("""
                SELECT id, date, description, amount, account_code,
                       confidence, review_required, status, source_type, created_at
                FROM journal_drafts WHERE tenant_id = %s
                ORDER BY created_at DESC, id DESC LIMIT 10
            """), tenant_id)]

    except Exception as e:
        return error_response("System overview failed", "SYSTEM_OVERVIEW_ERROR", str(e))

    return ok_response("System overview", {
        "tenant_id": tenant_id,
        "summary": {"journal_drafts": drafts_summary, "bank_files": bank_files_summary},
        "status_breakdown": status_breakdown,
        "approval_queue_count": approval_queue_count,
        "latest_bank_files": latest_bank_files,
        "latest_drafts": latest_drafts,
    })


async def get_bank_files_history_service(limit: int, offset: int):
    try:
        async with get_conn() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM processed_bank_files") or 0
            items = [dict(r) for r in await conn.fetch("""
                SELECT id, filename, file_hash, source_type, total_rows,
                       drafted_count, review_count, failed_count,
                       inserted_count, skipped_duplicates, created_at
                FROM processed_bank_files
                ORDER BY created_at DESC, id DESC
                LIMIT $1 OFFSET $2
            """, limit, offset)]
    except Exception as e:
        return error_response("Bank files history failed", "BANK_FILES_HISTORY_ERROR", str(e))

    return ok_response("Bank files history", {
        "count": total, "limit": limit, "offset": offset, "items": items,
    })


async def get_bank_file_detail_service(file_id: int):
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow("""
                SELECT id, filename, file_hash, source_type, total_rows,
                       drafted_count, review_count, failed_count,
                       inserted_count, skipped_duplicates, created_at
                FROM processed_bank_files WHERE id = $1
            """, file_id)
            if not row:
                return error_response(
                    "Bank file not found", "BANK_FILE_NOT_FOUND",
                    f"processed_bank_files id={file_id} does not exist",
                )
    except Exception as e:
        return error_response("Bank file detail failed", "BANK_FILE_DETAIL_ERROR", str(e))

    return ok_response("Bank file detail", dict(row))


async def get_bank_file_drafts_service(file_id: int, limit: int, offset: int, tenant_id: str = "default"):
    try:
        async with get_conn() as conn:
            bank_file = await conn.fetchrow(
                "SELECT id, filename, source_type, created_at FROM processed_bank_files WHERE id = $1",
                file_id,
            )
            if not bank_file:
                return error_response(
                    "Bank file not found", "BANK_FILE_NOT_FOUND",
                    f"processed_bank_files id={file_id} does not exist",
                )

            total = await conn.fetchval(_q("""
                SELECT COUNT(*) FROM journal_drafts WHERE bank_file_id = %s AND tenant_id = %s
            """), file_id, tenant_id) or 0

            items = [dict(r) for r in await conn.fetch(_q("""
                SELECT id, date, description, partner, amount,
                       debit_account, credit_account, account_code,
                       reason, confidence, review_required, status,
                       source_type, bank_file_id, created_at
                FROM journal_drafts
                WHERE bank_file_id = %s AND tenant_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s OFFSET %s
            """), file_id, tenant_id, limit, offset)]

    except Exception as e:
        return error_response("Bank file drafts failed", "BANK_FILE_DRAFTS_ERROR", str(e))

    return ok_response("Bank file drafts", {
        "tenant_id": tenant_id,
        "bank_file": dict(bank_file),
        "count": total, "limit": limit, "offset": offset, "items": items,
    })
