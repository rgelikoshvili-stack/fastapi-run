from fastapi import APIRouter
import psycopg2, psycopg2.extras, os
from datetime import datetime
from openai import OpenAI
from app.api.db import get_db

router = APIRouter(prefix="/fpa", tags=["fpa"])



def get_snapshot():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) as inflow FROM bank_transactions")
    inflow = float(cur.fetchone()["inflow"])
    cur.execute("SELECT COALESCE(SUM(CASE WHEN amount<0 THEN ABS(amount) ELSE 0 END),0) as outflow FROM bank_transactions")
    outflow = float(cur.fetchone()["outflow"])
    cur.execute("SELECT COUNT(*) as total FROM pipeline_runs")
    docs = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as c FROM pipeline_runs WHERE state='APPROVED'")
    approved = cur.fetchone()["c"]
    cur.close(); conn.close()
    return {"inflow": inflow, "outflow": outflow, "net": inflow-outflow, "docs": docs, "approved": approved}

@router.get("/budget-vs-actual")
def budget_vs_actual():
    snap = get_snapshot()
    budget_inflow = snap["inflow"] * 1.1
    budget_outflow = snap["outflow"] * 0.9
    return {
        "ok": True,
        "budget_vs_actual": {
            "inflow": {"budget": round(budget_inflow,2), "actual": round(snap["inflow"],2), "variance": round(snap["inflow"]-budget_inflow,2), "variance_pct": round((snap["inflow"]-budget_inflow)/budget_inflow*100,1) if budget_inflow else 0},
            "outflow": {"budget": round(budget_outflow,2), "actual": round(snap["outflow"],2), "variance": round(snap["outflow"]-budget_outflow,2), "variance_pct": round((snap["outflow"]-budget_outflow)/budget_outflow*100,1) if budget_outflow else 0},
            "net": {"budget": round(budget_inflow-budget_outflow,2), "actual": round(snap["net"],2)}
        }
    }

@router.get("/forecast")
def forecast():
    snap = get_snapshot()
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT DATE_TRUNC('month', created_at::timestamp) as month,
               SUM(CASE WHEN amount>0 THEN amount ELSE 0 END) as inflow,
               SUM(CASE WHEN amount<0 THEN ABS(amount) ELSE 0 END) as outflow
        FROM bank_transactions
        GROUP BY DATE_TRUNC('month', created_at::timestamp)
        ORDER BY month DESC LIMIT 3
    """)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    
    avg_inflow = sum(float(r["inflow"]) for r in rows) / len(rows) if rows else snap["inflow"]
    avg_outflow = sum(float(r["outflow"]) for r in rows) / len(rows) if rows else snap["outflow"]
    
    return {
        "ok": True,
        "forecast_next_3_months": [
            {"month": f"Month+{i+1}", "projected_inflow": round(avg_inflow*(1+0.02*i),2), "projected_outflow": round(avg_outflow*(1+0.01*i),2), "projected_net": round(avg_inflow*(1+0.02*i)-avg_outflow*(1+0.01*i),2)}
            for i in range(3)
        ]
    }

@router.get("/ai-analysis")
def ai_analysis():
    snap = get_snapshot()
    return {"ok": True, "snapshot": snap, "fpa_analysis": f"Inflow: {round(snap["inflow"],2)} GEL, Outflow: {round(snap["outflow"],2)} GEL, Net: {round(snap["net"],2)} GEL"}

@router.get("/kpi-trends")
def kpi_trends():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT DATE_TRUNC('month', created_at::timestamp) as month,
               COUNT(*) as doc_count,
               SUM(CASE WHEN state='APPROVED' THEN 1 ELSE 0 END) as approved_count
        FROM pipeline_runs
        GROUP BY DATE_TRUNC('month', created_at::timestamp)
        ORDER BY month DESC LIMIT 6
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return {
        "ok": True,
        "kpi_trends": [
            {"month": str(r["month"])[:7], "total_docs": r["doc_count"], "approved": r["approved_count"],
             "approval_rate": round(r["approved_count"]/r["doc_count"]*100,1) if r["doc_count"] else 0}
            for r in rows
        ]
    }