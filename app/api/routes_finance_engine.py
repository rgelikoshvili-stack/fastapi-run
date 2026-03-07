from fastapi import APIRouter
import psycopg2, psycopg2.extras
from datetime import datetime, timedelta
from app.api.db import get_db

router = APIRouter(prefix="/finance", tags=["finance"])



@router.get("/kpi")
def get_kpi():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    cur.execute("SELECT COUNT(*) as total FROM pipeline_runs")
    total_docs = cur.fetchone()["total"]
    
    cur.execute("SELECT COUNT(*) as approved FROM pipeline_runs WHERE state='APPROVED'")
    approved = cur.fetchone()["approved"]
    
    cur.execute("SELECT COUNT(*) as pending FROM pipeline_runs WHERE state='PENDING_APPROVAL'")
    pending = cur.fetchone()["pending"]
    
    cur.execute("SELECT COUNT(*) as total FROM bank_transactions")
    total_txs = cur.fetchone()["total"]
    
    cur.execute("SELECT COALESCE(SUM(amount),0) as total_amount FROM bank_transactions")
    total_amount = float(cur.fetchone()["total_amount"])
    
    cur.execute("SELECT COALESCE(SUM(amount),0) as total FROM bank_transactions WHERE amount > 0")
    total_inflow = float(cur.fetchone()["total"])
    
    cur.execute("SELECT COALESCE(SUM(ABS(amount)),0) as total FROM bank_transactions WHERE amount < 0")
    total_outflow = float(cur.fetchone()["total"])
    
    cur.close(); conn.close()
    
    approval_rate = round(approved / total_docs * 100, 1) if total_docs > 0 else 0
    
    return {
        "ok": True,
        "kpi": {
            "total_documents": total_docs,
            "approved_documents": approved,
            "pending_documents": pending,
            "approval_rate_percent": approval_rate,
            "total_transactions": total_txs,
            "total_inflow_gel": round(total_inflow, 2),
            "total_outflow_gel": round(total_outflow, 2),
            "net_cashflow_gel": round(total_inflow - total_outflow, 2)
        }
    }

@router.get("/cashflow")
def get_cashflow():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT 
            DATE_TRUNC('month', created_at) as month,
            SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as inflow,
            SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as outflow,
            SUM(amount) as net
        FROM bank_transactions
        GROUP BY DATE_TRUNC('month', created_at)
        ORDER BY month DESC
        LIMIT 12
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return {
        "ok": True,
        "cashflow_by_month": [
            {
                "month": str(r["month"])[:7],
                "inflow": round(float(r["inflow"]), 2),
                "outflow": round(float(r["outflow"]), 2),
                "net": round(float(r["net"]), 2)
            } for r in rows
        ]
    }

@router.get("/summary")
def finance_summary():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT COUNT(*) as total FROM pipeline_runs")
    docs = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as total FROM bank_transactions")
    txs = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as total FROM journal_entries")
    journals = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as total FROM coa")
    coa = cur.fetchone()["total"]
    cur.close(); conn.close()
    return {
        "ok": True,
        "system_summary": {
            "pipeline_runs": docs,
            "bank_transactions": txs,
            "journal_entries": journals,
            "coa_accounts": coa,
            "status": "operational"
        }
    }