from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import psycopg2, psycopg2.extras, io, csv, json
from datetime import datetime

router = APIRouter(prefix="/export", tags=["export"])

def get_db():
    return psycopg2.connect(host="35.192.214.120", dbname="bridgehub", user="postgres", password="BridgeHub2026x")

@router.get("/documents/csv")
def export_documents_csv():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id, filename, status, created_at FROM pipeline_runs ORDER BY created_at DESC")
    rows = cur.fetchall()
    cur.close(); conn.close()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id","filename","status","created_at"])
    writer.writeheader()
    for r in rows:
        writer.writerow({"id":r["id"],"filename":r["filename"],"status":r["status"],"created_at":str(r["created_at"])})
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=documents_{datetime.now().strftime('%Y%m%d')}.csv"})

@router.get("/transactions/csv")
def export_transactions_csv():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id, bank, date, amount, description, balance FROM bank_transactions ORDER BY created_at DESC")
    rows = cur.fetchall()
    cur.close(); conn.close()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id","bank","date","amount","description","balance"])
    writer.writeheader()
    for r in rows:
        writer.writerow(dict(r))
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=transactions_{datetime.now().strftime('%Y%m%d')}.csv"})

@router.get("/coa/csv")
def export_coa_csv():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT code, name_ka, name_en, category, direction FROM coa ORDER BY code")
    rows = cur.fetchall()
    cur.close(); conn.close()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["code","name_ka","name_en","category","direction"])
    writer.writeheader()
    for r in rows:
        writer.writerow(dict(r))
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=coa_{datetime.now().strftime('%Y%m%d')}.csv"})

@router.get("/report/json")
def export_full_report_json():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT COUNT(*) as total FROM pipeline_runs")
    total_docs = cur.fetchone()["total"]
    cur.execute("SELECT status, COUNT(*) as count FROM pipeline_runs GROUP BY status")
    status_breakdown = {r["status"]: r["count"] for r in cur.fetchall()}
    cur.execute("SELECT COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) as v FROM bank_transactions")
    inflow = float(cur.fetchone()["v"])
    cur.execute("SELECT COALESCE(SUM(CASE WHEN amount<0 THEN ABS(amount) ELSE 0 END),0) as v FROM bank_transactions")
    outflow = float(cur.fetchone()["v"])
    cur.execute("SELECT COUNT(*) as total FROM bank_transactions")
    total_txs = cur.fetchone()["total"]
    cur.execute("""SELECT DATE_TRUNC('month', created_at) as month,
        SUM(CASE WHEN amount>0 THEN amount ELSE 0 END) as inflow,
        SUM(CASE WHEN amount<0 THEN ABS(amount) ELSE 0 END) as outflow
        FROM bank_transactions GROUP BY month ORDER BY month DESC LIMIT 12""")
    monthly = [{"month": str(r["month"])[:7], "inflow": round(float(r["inflow"]),2), "outflow": round(float(r["outflow"]),2)} for r in cur.fetchall()]
    cur.close(); conn.close()
    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "summary": {
            "total_documents": total_docs,
            "status_breakdown": status_breakdown,
            "total_transactions": total_txs,
            "total_inflow_gel": round(inflow, 2),
            "total_outflow_gel": round(outflow, 2),
            "net_cashflow_gel": round(inflow - outflow, 2)
        },
        "monthly_cashflow": monthly
    }
    output = io.BytesIO(json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"))
    return StreamingResponse(output,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=report_{datetime.now().strftime('%Y%m%d')}.json"})

@router.get("/available")
def available_exports():
    return {
        "ok": True,
        "exports": [
            {"name": "Documents CSV", "endpoint": "/export/documents/csv", "format": "CSV"},
            {"name": "Transactions CSV", "endpoint": "/export/transactions/csv", "format": "CSV"},
            {"name": "COA CSV", "endpoint": "/export/coa/csv", "format": "CSV"},
            {"name": "Full Report JSON", "endpoint": "/export/report/json", "format": "JSON"},
        ]
    }