content = '''from fastapi import APIRouter, UploadFile, File, HTTPException
import psycopg2, psycopg2.extras, json, uuid
from datetime import datetime, timezone
from app.api.doc_analyzer import analyze, to_dict

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

DB_URL = "postgresql://postgres:BridgeHub2026x@35.192.214.120/bridgehub"

def get_db():
    return psycopg2.connect(DB_URL)

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            run_id TEXT PRIMARY KEY,
            filename TEXT,
            state TEXT,
            extraction TEXT,
            ai_draft TEXT,
            validation TEXT,
            approval_id TEXT,
            error TEXT,
            created_at TEXT,
            updated_at TEXT
        );
    """)
    conn.commit()
    cur.close(); conn.close()

init_db()

def _generate_ai_draft(extraction):
    amounts = extraction.get("amounts", [])
    amount = amounts[0]["value"] if amounts else 0.0
    vat = round(amount * 18 / 118, 2)
    net = round(amount - vat, 2)
    return {
        "account_code": "6100",
        "amount": net,
        "vat": vat,
        "direction": "debit",
        "currency": "GEL",
        "partner": extraction.get("names", [None])[0]
    }

def _validate(entries):
    errors, warnings = [], []
    total_debit = sum(e["amount"] for e in entries if e["direction"] == "debit")
    total_credit = sum(e["amount"] for e in entries if e["direction"] == "credit")
    if round(total_debit, 2) != round(total_credit, 2):
        errors.append(f"Debit/Credit imbalance: {total_debit} vs {total_credit}")
    for e in entries:
        if e.get("vat", 0) > 0:
            expected = round(e["amount"] * 18 / 118, 2)
            if abs(e["vat"] - expected) > 0.05:
                warnings.append(f"VAT mismatch: got {e[\'vat\']}, expected {expected}")
    return {"passed": len(errors) == 0, "errors": errors, "warnings": warnings}

@router.post("/run")
async def run_pipeline(file: UploadFile = File(...)):
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    cur = conn.cursor()
    try:
        data = await file.read()
        result = to_dict(analyze(file.filename or "uploaded", data))
        ai_draft = _generate_ai_draft(result)
        debit_entry = {**ai_draft}
        credit_entry = {"account_code": "3310", "amount": ai_draft["amount"], "vat": 0, "direction": "credit", "currency": "GEL"}
        entries = [debit_entry, credit_entry]
        validation = _validate(entries)
        approval_id = str(uuid.uuid4())
        cur.execute("INSERT INTO approvals VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", (
            approval_id, run_id, "PENDING_APPROVAL", json.dumps(entries), "pipeline", None, None, now, now))
        cur.execute("INSERT INTO pipeline_runs VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (
            run_id, file.filename, "PENDING_APPROVAL", json.dumps(result), json.dumps(ai_draft),
            json.dumps(validation), approval_id, None, now, now))
        conn.commit()
        return {"ok": True, "run_id": run_id, "filename": file.filename,
                "extraction": {"amounts": result.get("amounts"), "dates": result.get("dates"),
                               "names": result.get("names"), "ibans": result.get("ibans"), "ocr_used": result.get("ocr_used")},
                "ai_draft": ai_draft, "validation": validation, "approval_id": approval_id,
                "state": "PENDING_APPROVAL", "next_step": f"POST /approval/approve/{approval_id}"}
    except Exception as e:
        cur.execute("INSERT INTO pipeline_runs VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (
            run_id, file.filename, "ERROR", None, None, None, None, str(e), now, now))
        conn.commit()
        raise HTTPException(500, str(e))
    finally:
        cur.close(); conn.close()

@router.get("/status/{run_id}")
def pipeline_status(run_id: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM pipeline_runs WHERE run_id=%s", (run_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        raise HTTPException(404, f"Run not found: {run_id}")
    return {"ok": True, "run": dict(row)}

@router.get("/history")
def pipeline_history():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT run_id, filename, state, created_at FROM pipeline_runs ORDER BY created_at DESC LIMIT 20")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return {"ok": True, "runs": [dict(r) for r in rows]}

@router.get("/health")
def health():
    return {"ok": True, "service": "pipeline", "db": "postgresql"}
'''

with open('app/api/routes_pipeline.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done! routes_pipeline.py written successfully!")
