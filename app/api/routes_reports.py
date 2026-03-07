from fastapi import APIRouter
import psycopg2, psycopg2.extras
from app.api.db import get_db

router = APIRouter(prefix="/reports", tags=["reports"])



@router.get("/monthly")
def monthly_report():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT DATE_TRUNC('month', created_at::timestamp) as month,
               COUNT(*) as total_docs,
               SUM(CASE WHEN state='APPROVED' THEN 1 ELSE 0 END) as approved,
               SUM(CASE WHEN state='REJECTED' THEN 1 ELSE 0 END) as rejected
        FROM pipeline_runs
        GROUP BY DATE_TRUNC('month', created_at::timestamp)
        ORDER BY month DESC LIMIT 12
    """)
    rows = cur.fetchall()
    cur.execute("""
        SELECT DATE_TRUNC('month', created_at::timestamp) as month,
               SUM(CASE WHEN amount>0 THEN amount ELSE 0 END) as inflow,
               SUM(CASE WHEN amount<0 THEN ABS(amount) ELSE 0 END) as outflow
        FROM bank_transactions
        GROUP BY DATE_TRUNC('month', created_at::timestamp)
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
            "documents": {"total": r["total_docs"], "approved": r["approved"], "rejected": r["rejected"]},
            "financials": {"inflow": round(float(tx.get("inflow") or 0),2), "outflow": round(float(tx.get("outflow") or 0),2)}
        })
    return {"ok": True, "monthly_reports": result}

@router.get("/annual")
def annual_report():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT EXTRACT(YEAR FROM created_at::timestamp) as year, COUNT(*) as total FROM pipeline_runs GROUP BY year ORDER BY year DESC")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"ok": True, "annual_reports": rows}

@router.get("/audit-trail")
def audit_trail():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT run_id, filename, state, created_at FROM pipeline_runs ORDER BY created_at DESC LIMIT 50")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"ok": True, "pipeline_runs": rows}
