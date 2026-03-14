from app.api.audit_service import log_event
from fastapi import APIRouter, UploadFile, File
from app.api.bank_statement_parser import parse_csv_bytes, parse_xlsx_bytes, parse_xml_bytes
from app.api.transaction_classifier import classify
from app.api.journal_generator import generate_draft
from app.api.response_utils import ok_response, error_response
from app.api.db import get_db

import hashlib
import psycopg2
import re


router = APIRouter(prefix="/bank-csv", tags=["bank-csv"])


def _normalize_text(value):
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _normalize_amount(value):
    if value is None:
        return 0.0
    return round(float(value), 2)


def _normalize_date(value):
    if value is None:
        return None
    return str(value)[:10]


def _build_tx_fingerprint(draft: dict):
    normalized_date = _normalize_date(draft.get("date"))
    normalized_description = _normalize_text(draft.get("description"))
    normalized_amount = _normalize_amount(draft.get("amount"))

    raw = f"{normalized_date}|{normalized_description}|{normalized_amount}"
    tx_fingerprint = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    return {
        "normalized_date": normalized_date,
        "normalized_description": normalized_description,
        "normalized_amount": normalized_amount,
        "tx_fingerprint": tx_fingerprint,
    }


def _find_existing_draft_by_fingerprint(cur, tx_fingerprint: str):
    cur.execute(
        """
        SELECT id
        FROM journal_drafts
        WHERE tx_fingerprint = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (tx_fingerprint,),
    )
    return cur.fetchone()


@router.post("/process")
async def process_bank_file(file: UploadFile = File(...)):
    conn = None
    cur = None

    try:
        content = await file.read()
        filename = (file.filename or "").lower()

        if filename.endswith(".csv"):
            transactions = parse_csv_bytes(content)
            source_type = "csv"
        elif filename.endswith(".xlsx") or filename.endswith(".xls"):
            transactions = parse_xlsx_bytes(content)
            source_type = "xlsx"
        elif filename.endswith(".xml"):
            transactions = parse_xml_bytes(content)
            source_type = "xml"
        else:
            return error_response("Unsupported format", "FORMAT_ERROR", "Use CSV, XLSX or XML")

        total = len(transactions)
        drafted = []
        review = []
        failed = []

        for tx in transactions:
            try:
                cl = classify(
                    description=tx.get("description", ""),
                    paid_in=tx.get("paid_in"),
                    paid_out=tx.get("paid_out"),
                    partner=tx.get("partner", "")
                )
                draft = generate_draft(tx, cl)
                if draft["review_required"]:
                    review.append(draft)
                else:
                    drafted.append(draft)
            except Exception as e:
                failed.append({"tx": tx, "error": str(e)})

        conn = get_db()
        cur = conn.cursor()

        file_hash = hashlib.sha256(content).hexdigest()

        cur.execute(
            """
            INSERT INTO processed_bank_files
            (filename, file_hash, source_type, total_rows, drafted_count, review_count, failed_count, inserted_count, skipped_duplicates)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                file.filename,
                file_hash,
                source_type,
                total,
                len(drafted),
                len(review),
                len(failed),
                0,
                0,
            ),
        )
        bank_file_id = cur.fetchone()[0]

        inserted_count = 0
        skipped_duplicates = 0

        for d in drafted + review:
            fp = _build_tx_fingerprint(d)

            existing = _find_existing_draft_by_fingerprint(cur, fp["tx_fingerprint"])
            if existing:
                skipped_duplicates += 1
                continue

            cur.execute(
                """
                INSERT INTO journal_drafts (
                    date,
                    description,
                    partner,
                    amount,
                    debit_account,
                    credit_account,
                    account_code,
                    reason,
                    confidence,
                    review_required,
                    status,
                    source_type,
                    created_at,
                    normalized_date,
                    normalized_description,
                    normalized_amount,
                    bank_file_id,
                    tx_fingerprint
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    NOW(), %s, %s, %s, %s, %s
                )
                """,
                (
                    d.get("date"),
                    d.get("description"),
                    d.get("partner"),
                    d.get("amount"),
                    d.get("debit_account"),
                    d.get("credit_account"),
                    d.get("account_code"),
                    d.get("reason"),
                    d.get("confidence"),
                    d.get("review_required"),
                    d.get("status"),
                    d.get("source_type") or source_type,
                    fp["normalized_date"],
                    fp["normalized_description"],
                    fp["normalized_amount"],
                    bank_file_id,
                    fp["tx_fingerprint"],
                ),
            )
            inserted_count += 1

        cur.execute(
            """
            UPDATE processed_bank_files
            SET inserted_count = %s,
                skipped_duplicates = %s
            WHERE id = %s
            """,
            (inserted_count, skipped_duplicates, bank_file_id),
        )

        conn.commit()

        log_event(
            "bank_file_uploaded",
            {
                "filename": file.filename,
                "file_hash": file_hash,
                "total_rows": total,
                "inserted_count": inserted_count,
                "processed_file_id": bank_file_id,
                "skipped_duplicates": skipped_duplicates,
            },
        )

        return ok_response("Bank file processed", {
            "filename": file.filename,
            "total_rows": total,
            "drafted_count": len(drafted),
            "review_count": len(review),
            "failed_count": len(failed),
            "inserted_count": inserted_count,
            "skipped_duplicates": skipped_duplicates,
            "processed_file_id": bank_file_id,
            "drafted": drafted,
            "review_required": review,
            "failed": failed,
        })

    except Exception as e:
        if conn:
            conn.rollback()
        return error_response("Processing failed", "PROCESS_ERROR", str(e))
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
