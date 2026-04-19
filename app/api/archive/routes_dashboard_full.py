from fastapi import APIRouter, Request
import psycopg2, psycopg2.extras
from datetime import datetime, timedelta
from app.api.db import get_db

router = APIRouter(prefix="/dashboard-full", tags=["dashboard-full"])


@router.get("/overview")
def dashboard_overview(request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # pipeline_runs and coa are global tables (no tenant_id column)
    cur.execute("SELECT COUNT(*) as total FROM pipeline_runs")
    total_docs = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as c FROM pipeline_runs WHERE state='APPROVED'")
    approved = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM pipeline_runs WHERE state='PENDING_APPROVAL'")
    pending = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM pipeline_runs WHERE state='REJECTED'")
    rejected = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) as c FROM bank_transactions WHERE tenant_id = %s", (tenant_id,))
    bank_txs = cur.fetchone()["c"]
    cur.execute(
        "SELECT COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) as v FROM bank_transactions WHERE tenant_id = %s",
        (tenant_id,),
    )
    inflow = float(cur.fetchone()["v"])
    cur.execute(
        "SELECT COALESCE(SUM(CASE WHEN amount<0 THEN ABS(amount) ELSE 0 END),0) as v FROM bank_transactions WHERE tenant_id = %s",
        (tenant_id,),
    )
    outflow = float(cur.fetchone()["v"])

    try:
        cur.execute("SELECT COUNT(*) as c FROM journal_entries")
        journals = cur.fetchone()["c"]
    except Exception:
        journals = 0
    cur.execute("SELECT COUNT(*) as c FROM coa")
    coa_count = cur.fetchone()["c"]

    cur.execute("SELECT run_id, filename, state, created_at FROM pipeline_runs ORDER BY created_at DESC LIMIT 5")
    recent = [dict(r) for r in cur.fetchall()]

    cur.close(); conn.close()

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "overview": {
            "documents": {"total": total_docs, "approved": approved, "pending": pending, "rejected": rejected},
            "transactions": {"total": bank_txs, "inflow_gel": round(inflow, 2), "outflow_gel": round(outflow, 2), "net_gel": round(inflow - outflow, 2)},
            "accounting": {"journal_entries": journals, "coa_accounts": coa_count},
            "health": "HEALTHY" if pending < 10 and (inflow - outflow) >= 0 else "WARNING",
        },
        "recent_activity": recent,
    }


@router.get("/analytics")
def dashboard_analytics(request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as count, state
        FROM pipeline_runs
        WHERE created_at >= NOW() - INTERVAL '7 days'
        GROUP BY DATE(created_at), state
        ORDER BY day DESC
    """)
    docs_per_day = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT run_id, filename, state, created_at
        FROM pipeline_runs
        ORDER BY created_at DESC
        LIMIT 10
    """)
    top_docs = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT bank, COUNT(*) as count, COALESCE(SUM(amount),0) as total
        FROM bank_transactions
        WHERE tenant_id = %s
        GROUP BY bank
    """, (tenant_id,))
    by_bank = [dict(r) for r in cur.fetchall()]

    cur.close(); conn.close()
    return {
        "ok": True,
        "tenant_id": tenant_id,
        "docs_per_day": docs_per_day,
        "top_documents": top_docs,
        "transactions_by_bank": by_bank,
    }


@router.get("/report")
def dashboard_report(request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT state, COUNT(*) as count FROM pipeline_runs GROUP BY state")
    status_breakdown = {r["state"]: r["count"] for r in cur.fetchall()}

    cur.execute(
        "SELECT COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) as v FROM bank_transactions WHERE tenant_id = %s",
        (tenant_id,),
    )
    inflow = float(cur.fetchone()["v"])
    cur.execute(
        "SELECT COALESCE(SUM(CASE WHEN amount<0 THEN ABS(amount) ELSE 0 END),0) as v FROM bank_transactions WHERE tenant_id = %s",
        (tenant_id,),
    )
    outflow = float(cur.fetchone()["v"])
    cur.close(); conn.close()

    net = inflow - outflow
    return {
        "ok": True,
        "tenant_id": tenant_id,
        "report": {
            "generated_at": datetime.utcnow().isoformat(),
            "document_breakdown": status_breakdown,
            "financial_summary": {
                "inflow": round(inflow, 2),
                "outflow": round(outflow, 2),
                "net": round(net, 2),
                "financial_health": "POSITIVE" if net >= 0 else "NEGATIVE",
            },
        },
    }
