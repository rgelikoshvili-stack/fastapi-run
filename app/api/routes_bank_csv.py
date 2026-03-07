from fastapi import APIRouter, UploadFile, File
import psycopg2, psycopg2.extras, csv, io, json, uuid
from datetime import datetime
from app.api.db import get_db

router = APIRouter(prefix="/bank-csv", tags=["bank-csv"])



def detect_bank(headers):
    h = [x.lower().strip() for x in headers]
    if "თარიღი" in h or "თანხა" in h: return "TBC"
    if "date" in h and "amount" in h: return "BOG"
    if "дата" in h: return "RUS"
    return "UNKNOWN"

def parse_amount(val):
    try: return float(str(val).replace(",","").replace(" ","").strip())
    except: return 0.0

@router.post("/upload")
async def upload_csv(file: UploadFile = File(...)):
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except:
        text = content.decode("cp1252", errors="ignore")
    
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    headers = reader.fieldnames or []
    bank = detect_bank(headers)
    
    transactions = []
    for row in rows:
        tx = {"raw": dict(row), "bank": bank}
        for k, v in row.items():
            kl = k.lower().strip()
            if any(x in kl for x in ["date", "თარიღი", "дата"]):
                tx["date"] = v.strip()
            elif any(x in kl for x in ["amount", "თანხა", "сумма", "credit", "debit"]):
                tx["amount"] = parse_amount(v)
            elif any(x in kl for x in ["description", "დანიშნულება", "назначение", "details"]):
                tx["description"] = v.strip()
            elif any(x in kl for x in ["balance", "ნაშთი", "остаток"]):
                tx["balance"] = parse_amount(v)
        transactions.append(tx)
    
    conn = get_db()
    cur = conn.cursor()
    batch_id = str(uuid.uuid4())
    saved = 0
    for tx in transactions:
        try:
            cur.execute("""
                INSERT INTO bank_transactions (id, batch_id, bank, date, amount, description, balance, raw, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
            """, (str(uuid.uuid4()), batch_id, tx.get("bank"), tx.get("date"),
                  tx.get("amount",0), tx.get("description",""), tx.get("balance",0),
                  json.dumps(tx.get("raw",{})), datetime.utcnow()))
            saved += 1
        except: pass
    conn.commit()
    cur.close(); conn.close()
    return {"ok": True, "bank": bank, "total_rows": len(rows), "saved": saved, "batch_id": batch_id}

@router.get("/transactions")
def list_transactions(limit: int = 50):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM bank_transactions ORDER BY created_at DESC LIMIT %s", (limit,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return {"ok": True, "count": len(rows), "transactions": [dict(r) for r in rows]}

@router.get("/batches")
def list_batches():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT batch_id, bank, COUNT(*) as count, SUM(amount) as total, MIN(created_at) as uploaded_at FROM bank_transactions GROUP BY batch_id, bank ORDER BY uploaded_at DESC")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return {"ok": True, "batches": [dict(r) for r in rows]}