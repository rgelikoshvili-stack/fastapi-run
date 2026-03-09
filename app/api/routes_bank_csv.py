from fastapi import APIRouter, UploadFile, File, Form
from typing import Optional
import hashlib
from app.api.response_utils import ok_response, error_response
from app.api.bank_statement_parser import parse_csv_bytes, parse_xlsx_bytes, parse_xml_bytes

router = APIRouter(prefix="/bank-csv", tags=["bank"])

@router.post("/upload")
async def upload_bank_file(file: UploadFile = File(...), bank: Optional[str] = Form(default="UNKNOWN")):
    try:
        content = await file.read()
        name = file.filename.lower()
        file_hash = hashlib.md5(content).hexdigest()
        try:
            from app.api.db import get_db
            import psycopg2.extras, uuid, json
            conn = get_db()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT batch_id, created_at FROM bank_transactions WHERE raw::text LIKE %s LIMIT 1", (f'%"hash":"{file_hash}"%',))
            existing = cur.fetchone()
            if existing:
                cur.close(); conn.close()
                return ok_response("Duplicate file detected", {"duplicate": True, "original_batch_id": str(existing["batch_id"]), "message": "ეს ფაილი უკვე ატვირთულია"})
            cur.close(); conn.close()
        except:
            pass
        if name.endswith(".csv"):
            rows = parse_csv_bytes(content)
        elif name.endswith(".xlsx"):
            rows = parse_xlsx_bytes(content)
        elif name.endswith(".xml"):
            rows = parse_xml_bytes(content)
        else:
            return error_response("Unsupported file format", "BANK_FILE_ERROR", "Use csv, xlsx or xml")
        saved = 0
        batch_id = None
        try:
            from app.api.db import get_db
            import psycopg2.extras, uuid, json
            conn = get_db()
            cur = conn.cursor()
            batch_id = str(uuid.uuid4())
            for row in rows:
                cur.execute("INSERT INTO bank_transactions (id, batch_id, bank, date, amount, description, balance, raw, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())", (str(uuid.uuid4()), batch_id, bank, str(row.get("date",""))[:10], float(row.get("paid_in") or 0) - float(row.get("paid_out") or 0), row.get("description",""), float(row.get("balance") or 0), json.dumps({**row, "hash": file_hash})))
                saved += 1
            conn.commit()
            cur.close(); conn.close()
        except Exception as db_err:
            saved = 0
        return ok_response("Bank statement parsed", {"filename": file.filename, "bank": bank, "file_hash": file_hash, "duplicate": False, "rows_count": len(rows), "saved": saved, "batch_id": batch_id, "transactions": rows[:5]})
    except Exception as e:
        return error_response("Upload failed", "UPLOAD_ERROR", str(e))

@router.get("/history")
def bank_csv_history():
    from app.api.db import get_db
    import psycopg2.extras
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT batch_id, bank, COUNT(*) as rows, MIN(date) as from_date, MAX(date) as to_date, MIN(created_at) as uploaded_at FROM bank_transactions GROUP BY batch_id, bank ORDER BY uploaded_at DESC LIMIT 20")
        rows = [dict(r) for r in cur.fetchall()]
    except:
        rows = []
    finally:
        cur.close(); conn.close()
    return ok_response("Bank CSV history", {"count": len(rows), "history": rows})