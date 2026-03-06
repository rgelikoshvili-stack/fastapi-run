from fastapi import APIRouter
import psycopg2, psycopg2.extras
from datetime import datetime, timedelta

router = APIRouter(prefix="/dashboard-full", tags=["dashboard-full"])

def get_db():
    return psycopg2.connect(host="35.192.214.120", dbname="bridgehub", user="postgres", password="BridgeHub2026x")

@router.get("/overview")
def dashboard_overview():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    cur.execute("SELECT COUNT(*) as total FROM pipeline_runs")
    total_docs = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as c FROM pipeline_runs WHERE status='APPROVED'")
    approved = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM pipeline_runs WHERE status='PENDING_APPROVAL'")
    pending = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM pipeline_runs WHERE status='REJECTED'")
    rejected = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM bank_transactions")
    bank_txs = cur.fetchone()["c"]
    cur.execute("SELECT COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) as v FROM bank_transactions")
    inflow = float(cur.fetchone()["v"])
    cur.execute("SELECT COALESCE(SUM(CASE WHEN amount<0 THEN ABS(amount) ELSE 0 END),0) as v FROM bank_transactions")
    outflow = float(cur.fetchone()["v"])
    cur.execute("SELECT COUNT(*) as c FROM journal_entries")
    journals = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM coa")
    coa_count = cur.fetchone()["c"]
    
    # Recent activity
    cur.execute("SELECT id, filename, status, created_at FROM pipeline_runs ORDER BY created_at DESC LIMIT 5")
    recent = [dict(r) for r in cur.fetchall()]
    
    cur.close(); conn.close()
    
    return {
        "ok": True,
        "overview": {
            "documents": {"total": total_docs, "approved": approved, "pending": pending, "rejected": rejected},
            "transactions": {"total": bank_txs, "inflow_gel": round(inflow,2), "outflow_gel": round(outflow,2), "net_gel": round(inflow-outflow,2)},
            "accounting": {"journal_entries": journals, "coa_accounts": coa_count},
            "health": "HEALTHY" if pending < 10 and (inflow - outflow) >= 0 else "WARNING"
        },
        "recent_activity": recent
    }

@router.get("/analytics")
def dashboard_analytics():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Documents per day (last 7 days)
    cur.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as count, status
        FROM pipeline_runs
        WHERE created_at >= NOW() - INTERVAL '7 days'
        GROUP BY DATE(created_at), status
        ORDER BY day DESC
    """)
    docs_per_day = [dict(r) for r in cur.fetchall()]
    
    # Top amounts
    cur.execute("""
        SELECT filename, status, created_at
        FROM pipeline_runs
        ORDER BY created_at DESC
        LIMIT 10
    """)
    top_docs = [dict(r) for r in cur.fetchall()]
    
    # Bank transactions by bank
    cur.execute("""
        SELECT bank, COUNT(*) as count, COALESCE(SUM(amount),0) as total
        FROM bank_transactions
        GROUP BY bank
    """)
    by_bank = [dict(r) for r in cur.fetchall()]
    
    cur.close(); conn.close()
    return {
        "ok": True,
        "docs_per_day": docs_per_day,
        "top_documents": top_docs,
        "transactions_by_bank": by_bank
    }

@router.get("/report")
def dashboard_report():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT status, COUNT(*) as count FROM pipeline_runs GROUP BY status")
    status_breakdown = {r["status"]: r["count"] for r in cur.fetchall()}
    cur.execute("SELECT COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) as v FROM bank_transactions")
    inflow = float(cur.fetchone()["v"])
    cur.execute("SELECT COALESCE(SUM(CASE WHEN amount<0 THEN ABS(amount) ELSE 0 END),0) as v FROM bank_transactions")
    outflow = float(cur.fetchone()["v"])
    cur.close(); conn.close()
    
    net = inflow - outflow
    return {
        "ok": True,
        "report": {
            "generated_at": datetime.utcnow().isoformat(),
            "document_breakdown": status_breakdown,
            "financial_summary": {
                "inflow": round(inflow, 2),
                "outflow": round(outflow, 2),
                "net": round(net, 2),
                "financial_health": "POSITIVE" if net >= 0 else "NEGATIVE"
            }
        }
    }