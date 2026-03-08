from app.api.audit_service import log_event
from fastapi import APIRouter, UploadFile, File
from app.api.bank_statement_parser import parse_csv_bytes, parse_xlsx_bytes, parse_xml_bytes
from app.api.transaction_classifier import classify
from app.api.journal_generator import generate_draft
from app.api.response_utils import ok_response, error_response
import psycopg2
from app.api.db import get_db

router = APIRouter(prefix="/bank-csv", tags=["bank-csv"])

@router.post("/process")
async def process_bank_file(file: UploadFile = File(...)):
    try:
        content = await file.read()
        filename = file.filename.lower()

        if filename.endswith(".csv"):
            transactions = parse_csv_bytes(content)
        elif filename.endswith(".xlsx") or filename.endswith(".xls"):
            transactions = parse_xlsx_bytes(content)
        elif filename.endswith(".xml"):
            transactions = parse_xml_bytes(content)
        else:
            return error_response("Unsupported format", "FORMAT_ERROR", "Use CSV, XLSX or XML")

        total = len(transactions)
        drafted, review, failed = [], [], []

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

        # DB-ში შენახვა
        log_event("bank_file_uploaded", {"filename": file.filename, "total_rows": total})
        conn = get_db()
        cur = conn.cursor()
        for d in drafted + review:
            cur.execute("""
                INSERT INTO journal_drafts (date,description,partner,amount,debit_account,credit_account,account_code,reason,confidence,review_required,status,source_type)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (d.get("date"),d.get("description"),d.get("partner"),d.get("amount"),
                  d.get("debit_account"),d.get("credit_account"),d.get("account_code"),
                  d.get("reason"),d.get("confidence"),d.get("review_required"),d.get("status"),d.get("source_type")))
        conn.commit()
        cur.close(); conn.close()

        return ok_response("Bank file processed", {
            "filename": file.filename,
            "total_rows": total,
            "drafted_count": len(drafted),
            "review_count": len(review),
            "failed_count": len(failed),
            "drafted": drafted,
            "review_required": review,
            "failed": failed,
        })

    except Exception as e:
        return error_response("Processing failed", "PROCESS_ERROR", str(e))
