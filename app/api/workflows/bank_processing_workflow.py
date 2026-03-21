import hashlib
import psycopg2.extras

from app.api.audit_service import log_event
from app.api.bank_statement_parser import parse_csv_bytes, parse_xlsx_bytes, parse_xml_bytes
from app.api.transaction_classifier import classify
from app.api.journal_generator import generate_draft
from app.api.response_utils import ok_response, error_response
from app.api.db import get_db


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _normalize_text(value):
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _normalize_amount(value):
    try:
        return round(float(value), 2)
    except Exception:
        return None


def _normalize_date(value):
    if value is None:
        return ""
    return str(value).strip()


def _build_tx_fingerprint(normalized_date: str, normalized_description: str, normalized_amount):
    raw = f"{normalized_date}|{normalized_description}|{normalized_amount}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _find_existing_processed_file(cur, file_hash: str):
    cur.execute(
        """
        SELECT
            id, filename, file_hash, source_type, total_rows,
            drafted_count, review_count, failed_count,
            inserted_count, skipped_duplicates, created_at
        FROM processed_bank_files
        WHERE file_hash = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (file_hash,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _find_existing_draft_by_fingerprint(cur, tx_fingerprint: str):
    cur.execute(
        """
        SELECT id, status
        FROM journal_drafts
        WHERE tx_fingerprint = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (tx_fingerprint,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def process_bank_file_workflow(filename: str, content: bytes):
    conn = None
    cur = None

    try:
        lowered = (filename or "").lower()
        file_hash = _sha256_bytes(content)

        if lowered.endswith(".csv"):
            transactions = parse_csv_bytes(content)
            source_type = "csv"
        elif lowered.endswith(".xlsx") or lowered.endswith(".xls"):
            transactions = parse_xlsx_bytes(content)
            source_type = "xlsx"
        elif lowered.endswith(".xml"):
            transactions = parse_xml_bytes(content)
            source_type = "xml"
        else:
            return error_response("Unsupported format", "FORMAT_ERROR", "Use CSV, XLSX or XML")

        total = len(transactions)
        drafted = []
        review = []
        failed = []
        inserted_count = 0
        skipped_duplicates = 0

        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        existing_file = _find_existing_processed_file(cur, file_hash)
        if existing_file:
            log_event(
                "bank_file_duplicate_skipped",
                {
                    "filename": filename,
                    "file_hash": file_hash,
                    "existing_processed_file_id": existing_file["id"],
                },
            )
            return ok_response(
                "Duplicate bank file skipped",
                {
                    "duplicate": True,
                    "filename": filename,
                    "file_hash": file_hash,
                    "original_id": str(existing_file["id"]),
                    "message": "ეს ფაილი უკვე დამუშავებულია",
                },
            )

        cur.execute(
            """
            INSERT INTO processed_bank_files
            (
                filename, file_hash, source_type, total_rows,
                drafted_count, review_count, failed_count,
                inserted_count, skipped_duplicates
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (filename, file_hash, source_type, total, 0, 0, 0, 0, 0),
        )
        bank_file_id = cur.fetchone()["id"]

        for tx in transactions:
            try:
                tx["source_type"] = source_type

                amount = tx.get("amount")
                if amount is None:
                    paid_in = tx.get("paid_in")
                    paid_out = tx.get("paid_out")
                    if paid_in not in (None, "", 0, 0.0):
                        amount = paid_in
                    elif paid_out not in (None, "", 0, 0.0):
                        amount = paid_out

                tx["amount"] = amount

                normalized_date = _normalize_date(tx.get("date"))
                normalized_description = _normalize_text(tx.get("description"))
                normalized_amount = _normalize_amount(tx.get("amount"))

                tx_fingerprint = _build_tx_fingerprint(
                    normalized_date,
                    normalized_description,
                    normalized_amount,
                )

                existing_draft = _find_existing_draft_by_fingerprint(cur, tx_fingerprint)
                if existing_draft:
                    skipped_duplicates += 1
                    continue

                cl = classify(
                    description=tx.get("description", ""),
                    paid_in=tx.get("paid_in"),
                    paid_out=tx.get("paid_out"),
                    partner=tx.get("partner", ""),
                )

                draft = generate_draft(tx, cl)
                draft["bank_file_id"] = bank_file_id
                draft["tx_fingerprint"] = tx_fingerprint
                draft["normalized_date"] = normalized_date
                draft["normalized_description"] = normalized_description
                draft["normalized_amount"] = normalized_amount

                draft["classification_source"] = cl.get("source")
                draft["pattern_matched_on"] = cl.get("pattern_matched_on")
                draft["pattern_support_count"] = cl.get("pattern_support_count")
                draft["pattern_similarity"] = cl.get("pattern_similarity")
                draft["pattern_value_used"] = cl.get("pattern_value_used")

                draft["autopilot_decision"] = cl.get("autopilot_eligible")
                draft["autopilot_reason"] = cl.get("autopilot_reason")
                draft["approved_by_mode"] = "autopilot" if cl.get("autopilot_eligible") else "manual_review"

                cur.execute(
                    """
                    INSERT INTO journal_drafts
                    (
                        date, description, partner, amount,
                        debit_account, credit_account, account_code,
                        reason, confidence, review_required, status,
                        source_type, bank_file_id, tx_fingerprint,
                        normalized_date, normalized_description, normalized_amount,
                        classification_source, pattern_matched_on,
                        pattern_support_count, pattern_similarity, pattern_value_used,
                        autopilot_decision, autopilot_reason, approved_by_mode
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s
                    )
                    RETURNING id
                    """,
                    (
                        draft.get("date"),
                        draft.get("description"),
                        draft.get("partner"),
                        draft.get("amount"),
                        draft.get("debit_account"),
                        draft.get("credit_account"),
                        draft.get("account_code"),
                        draft.get("reason"),
                        draft.get("confidence"),
                        draft.get("review_required"),
                        draft.get("status"),
                        draft.get("source_type"),
                        draft.get("bank_file_id"),
                        draft.get("tx_fingerprint"),
                        draft.get("normalized_date"),
                        draft.get("normalized_description"),
                        draft.get("normalized_amount"),
                        draft.get("classification_source"),
                        draft.get("pattern_matched_on"),
                        draft.get("pattern_support_count"),
                        draft.get("pattern_similarity"),
                        draft.get("pattern_value_used"),
                        draft.get("autopilot_decision"),
                        draft.get("autopilot_reason"),
                        draft.get("approved_by_mode"),
                    ),
                )
                draft["id"] = cur.fetchone()["id"]

                inserted_count += 1
                if draft["review_required"]:
                    review.append(draft)
                else:
                    drafted.append(draft)

            except Exception as e:
                failed.append({"tx": tx, "error": str(e)})

        cur.execute(
            """
            UPDATE processed_bank_files
            SET
                drafted_count = %s,
                review_count = %s,
                failed_count = %s,
                inserted_count = %s,
                skipped_duplicates = %s
            WHERE id = %s
            """,
            (
                len(drafted),
                len(review),
                len(failed),
                inserted_count,
                skipped_duplicates,
                bank_file_id,
            ),
        )

        conn.commit()

        log_event(
            "bank_file_uploaded",
            {
                "filename": filename,
                "file_hash": file_hash,
                "total_rows": total,
                "inserted_count": inserted_count,
                "processed_file_id": bank_file_id,
                "skipped_duplicates": skipped_duplicates,
            },
        )

        return ok_response(
            "Bank file processed",
            {
                "filename": filename,
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
            },
        )

    except Exception as e:
        if conn:
            conn.rollback()
        return error_response("Processing failed", "PROCESS_ERROR", str(e))
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()