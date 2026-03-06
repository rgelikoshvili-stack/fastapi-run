from fastapi import APIRouter
import psycopg2, psycopg2.extras
from datetime import datetime

router = APIRouter(prefix="/reports", tags=["reports"])

def get_db():
    return psycopg2.connect(host="35.192.214.120", dbname="bridgehub", user="postgres", password="BridgeHub2026x")

@router.get("/monthly")
def monthly_report():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT DATE_TRUNC('month', created_at) as month,
               COUNT(*) as total_docs,
               SUM(CASE WHEN status='APPROVED' THEN 1 ELSE 0 END) as approved,
               SUM(CASE WHEN status='REJECTED' THEN 1 ELSE 0 END) as rejected,
               SUM(CASE WHEN status='PENDING_APPROVAL' THEN 1 ELSE 0 END) as pending
        FROM pipeline_runs
        GROUP BY DATE_TRUNC('month', created_at)
        ORDER BY month DESC LIMIT 12
    """)
    rows = cur.fetchall()
    cur.execute("""
        SELECT DATE_TRUNC('month', created_at) as month,
               SUM(CASE WHEN amount>0 THEN amount ELSE 0 END) as inflow,
               SUM(CASE WHEN amount<0 THEN ABS(amount) ELSE 0 END) as outflow
        FROM bank_transactions
        GROUP BY DATE_TRUNC('month', created_at)
        ORDER BY month DESC LIMIT 12
    """)
    tx_rows = {str(r["month"])[:7]: dict(r) for r in cur.fetchall()}
    cur.close(); conn.close()
    result = []
    for r in rows:
        m = str(r["month"])[:7]
        tx = tx_rows.get(m, {})
        result.append({
            "month": m,
            "documents": {"total": r["total_docs"], "approved": r["approved"], "rejected": r["rejected"], "pending": r["pending"]},
            "financials": {"inflow": round(float(tx.get("inflow") or 0),2), "outflow": round(float(tx.get("outflow") or 0),2)}
        })
    return {"ok": True, "monthly_reports": result}

@router.get("/annual")
def annual_report():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT EXTRACT(YEAR FROM created_at) as year,
               COUNT(*) as total_docs,
               SUM(CASE WHEN status='APPROVED' THEN 1 ELSE 0 END) as approved
        FROM pipeline_runs GROUP BY year ORDER BY year DESC
    """)
    doc_rows = [dict(r) for r in cur.fetchall()]
    cur.execute("""
        SELECT EXTRACT(YEAR FROM created_at) as year,
               SUM(CASE WHEN amount>0 THEN amount ELSE 0 END) as inflow,
               SUM(CASE WHEN amount<0 THEN ABS(amount) ELSE 0 END) as outflow
        FROM bank_transactions GROUP BY year ORDER BY year DESC
    """)
    tx_rows = {int(r["year"]): dict(r) for r in cur.fetchall()}
    cur.close(); conn.close()
    result = []
    for r in doc_rows:
        yr = int(r["year"])
        tx = tx_rows.get(yr, {})
        result.append({
            "year": yr,
            "total_docs": r["total_docs"],
            "approved": r["approved"],
            "inflow": round(float(tx.get("inflow") or 0),2),
            "outflow": round(float(tx.get("outflow") or 0),2),
            "net": round(float(tx.get("inflow") or 0) - float(tx.get("outflow") or 0),2)
        })
    return {"ok": True, "annual_reports": result}

@router.get("/audit-trail")
def audit_trail():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id, filename, status, created_at FROM pipeline_runs ORDER BY created_at DESC LIMIT 50")
    runs = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"ok": True, "pipeline_runs": runs}
