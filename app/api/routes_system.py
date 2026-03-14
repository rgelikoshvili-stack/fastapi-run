from fastapi import APIRouter, Path, HTTPException
import psycopg2.extras

from app.api.db import get_db
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/system", tags=["system"])


def _validate_pagination(limit: int, offset: int):
    if limit < 0:
        raise HTTPException(
            status_code=422,
            detail={"error": "INVALID_PAGINATION", "message": "limit უნდა იყოს 0 ან მეტი"}
        )
    if offset < 0:
        raise HTTPException(
            status_code=422,
            detail={"error": "INVALID_PAGINATION", "message": "offset უნდა იყოს 0 ან მეტი"}
        )


# ─── SUMMARY ──────────────────────────────────────────────────────────────────

@router.get("/summary")
def get_system_summary():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("SELECT COUNT(*) AS count FROM processed_bank_files")
        bank_files_processed = cur.fetchone()["count"]

        cur.execute("SELECT COUNT(*) AS count FROM journal_drafts")
        transactions_total = cur.fetchone()["count"]

        cur.execute("SELECT status, COUNT(*) AS count FROM journal_drafts GROUP BY status")
        rows = cur.fetchall()

        status_counts = {"drafted": 0, "pending_approval": 0, "approved": 0, "rejected": 0}
        for row in rows:
            status_counts[row["status"]] = row["count"]

        cur.execute(
            """
            SELECT
                COALESCE(SUM(total_rows), 0) AS total_rows_sum,
                COALESCE(SUM(drafted_count), 0) AS drafted_sum,
                COALESCE(SUM(review_count), 0) AS review_sum,
                COALESCE(SUM(failed_count), 0) AS failed_sum,
                COALESCE(SUM(inserted_count), 0) AS inserted_sum,
                COALESCE(SUM(skipped_duplicates), 0) AS skipped_sum
            FROM processed_bank_files
            """
        )
        file_stats = cur.fetchone()

    except Exception as e:
        return error_response("System summary failed", "SYSTEM_SUMMARY_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    return ok_response("System summary", {
        "bank_files_processed": bank_files_processed,
        "transactions_total": transactions_total,
        "drafted": status_counts.get("drafted", 0),
        "pending_approval": status_counts.get("pending_approval", 0),
        "approved": status_counts.get("approved", 0),
        "rejected": status_counts.get("rejected", 0),
        "duplicates_skipped": file_stats["skipped_sum"] or 0,
        "file_stats": {
            "total_rows_sum": file_stats["total_rows_sum"] or 0,
            "drafted_sum": file_stats["drafted_sum"] or 0,
            "review_sum": file_stats["review_sum"] or 0,
            "failed_sum": file_stats["failed_sum"] or 0,
            "inserted_sum": file_stats["inserted_sum"] or 0,
            "skipped_sum": file_stats["skipped_sum"] or 0,
        },
    })


# ─── OVERVIEW ─────────────────────────────────────────────────────────────────

@router.get("/overview")
def get_system_overview():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            """
            SELECT
                COUNT(*) AS total_drafts,
                COUNT(*) FILTER (WHERE status = 'drafted') AS drafted_count,
                COUNT(*) FILTER (WHERE status = 'approved') AS approved_count,
                COUNT(*) FILTER (WHERE status = 'rejected') AS rejected_count,
                COUNT(*) FILTER (WHERE review_required = TRUE) AS review_required_count
            FROM journal_drafts
            """
        )
        drafts_summary = dict(cur.fetchone())

        cur.execute(
            """
            SELECT
                COUNT(*) AS total_bank_files,
                COALESCE(SUM(total_rows), 0) AS total_rows_sum,
                COALESCE(SUM(drafted_count), 0) AS drafted_sum,
                COALESCE(SUM(review_count), 0) AS review_sum,
                COALESCE(SUM(failed_count), 0) AS failed_sum,
                COALESCE(SUM(inserted_count), 0) AS inserted_sum,
                COALESCE(SUM(skipped_duplicates), 0) AS duplicates_skipped
            FROM processed_bank_files
            """
        )
        bank_files_summary = dict(cur.fetchone())

        cur.execute(
            "SELECT status, COUNT(*) AS count FROM journal_drafts GROUP BY status ORDER BY status"
        )
        status_breakdown = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT COUNT(*) AS count FROM journal_drafts
            WHERE status = 'drafted' AND review_required = TRUE
            """
        )
        approval_queue_count = cur.fetchone()["count"]

        cur.execute(
            """
            SELECT id, filename, file_hash, source_type, total_rows,
                   drafted_count, review_count, failed_count,
                   inserted_count, skipped_duplicates, created_at
            FROM processed_bank_files
            ORDER BY created_at DESC, id DESC
            LIMIT 5
            """
        )
        latest_bank_files = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT id, date, description, amount, account_code,
                   confidence, review_required, status, source_type, created_at
            FROM journal_drafts
            ORDER BY created_at DESC, id DESC
            LIMIT 10
            """
        )
        latest_drafts = [dict(r) for r in cur.fetchall()]

    except Exception as e:
        return error_response("System overview failed", "SYSTEM_OVERVIEW_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    return ok_response("System overview", {
        "summary": {
            "journal_drafts": drafts_summary,
            "bank_files": bank_files_summary,
        },
        "status_breakdown": status_breakdown,
        "approval_queue_count": approval_queue_count,
        "latest_bank_files": latest_bank_files,
        "latest_drafts": latest_drafts,
    })


# ─── BANK FILES ───────────────────────────────────────────────────────────────

@router.get("/bank-files")
def get_bank_files_history(limit: int = 50, offset: int = 0):
    _validate_pagination(limit, offset)
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("SELECT COUNT(*) AS total FROM processed_bank_files")
        total = cur.fetchone()["total"]

        cur.execute(
            """
            SELECT id, filename, file_hash, source_type, total_rows,
                   drafted_count, review_count, failed_count,
                   inserted_count, skipped_duplicates, created_at
            FROM processed_bank_files
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        items = [dict(r) for r in cur.fetchall()]

    except Exception as e:
        return error_response("Bank files history failed", "BANK_FILES_HISTORY_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    return ok_response("Bank files history", {
        "count": total,
        "limit": limit,
        "offset": offset,
        "items": items,
    })


@router.get("/bank-files/{file_id}")
def get_bank_file_detail(file_id: int = Path(..., description="Processed bank file ID")):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            """
            SELECT id, filename, file_hash, source_type, total_rows,
                   drafted_count, review_count, failed_count,
                   inserted_count, skipped_duplicates, created_at
            FROM processed_bank_files
            WHERE id = %s
            """,
            (file_id,),
        )
        row = cur.fetchone()

        if not row:
            return error_response(
                "Bank file not found",
                "BANK_FILE_NOT_FOUND",
                f"processed_bank_files id={file_id} does not exist",
            )

    except Exception as e:
        return error_response("Bank file detail failed", "BANK_FILE_DETAIL_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    return ok_response("Bank file detail", dict(row))


@router.get("/bank-files/{file_id}/drafts")
def get_bank_file_drafts(file_id: int, limit: int = 100, offset: int = 0):
    _validate_pagination(limit, offset)
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            "SELECT id, filename, source_type, created_at FROM processed_bank_files WHERE id = %s",
            (file_id,),
        )
        bank_file = cur.fetchone()

        if not bank_file:
            return error_response(
                "Bank file not found",
                "BANK_FILE_NOT_FOUND",
                f"processed_bank_files id={file_id} does not exist",
            )

        cur.execute(
            "SELECT COUNT(*) AS total FROM journal_drafts WHERE bank_file_id = %s",
            (file_id,),
        )
        total = cur.fetchone()["total"]

        cur.execute(
            """
            SELECT id, date, description, partner, amount,
                   debit_account, credit_account, account_code,
                   reason, confidence, review_required, status,
                   source_type, bank_file_id, created_at
            FROM journal_drafts
            WHERE bank_file_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            (file_id, limit, offset),
        )
        items = [dict(r) for r in cur.fetchall()]

    except Exception as e:
        return error_response("Bank file drafts failed", "BANK_FILE_DRAFTS_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    return ok_response("Bank file drafts", {
        "bank_file": dict(bank_file),
        "count": total,
        "limit": limit,
        "offset": offset,
        "items": items,
    })