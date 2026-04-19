from fastapi import APIRouter
import psycopg2, psycopg2.extras, json
from datetime import datetime
from app.api.db import get_db

router = APIRouter(prefix="/supervisor", tags=["supervisor"])



@router.get("/status")
def supervisor_status():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT state, COUNT(*) as count FROM pipeline_runs GROUP BY state")
    breakdown = {r["state"]: r["count"] for r in cur.fetchall()}
    cur.execute("SELECT COUNT(*) as total FROM pipeline_runs")
    total = cur.fetchone()["total"]
    cur.close(); conn.close()
    agents = [
        {"name": "ParseAgent", "status": "active", "role": "Document parsing"},
        {"name": "AccountingAgent", "status": "active", "role": "Journal drafting"},
        {"name": "ValidationAgent", "status": "active", "role": "Quality gates"},
        {"name": "ApprovalAgent", "status": "active", "role": "Human approval"},
        {"name": "AuditAgent", "status": "active", "role": "Compliance check"},
    ]
    return {"ok": True, "supervisor": "active", "total_runs": total, "breakdown": breakdown, "agents": agents}

@router.post("/route")
def supervisor_route(payload: dict):
    doc_type = payload.get("doc_type", "unknown")
    amount = payload.get("amount", 0)
    routing = {
        "invoice": ["ParseAgent", "AccountingAgent", "ValidationAgent", "ApprovalAgent"],
        "bank_statement": ["ParseAgent", "ReconcileAgent", "AuditAgent"],
        "receipt": ["ParseAgent", "AccountingAgent", "ValidationAgent"],
    }
    route = routing.get(doc_type, ["ParseAgent", "AccountingAgent", "ValidationAgent"])
    risk = "HIGH" if amount > 10000 else "MEDIUM" if amount > 1000 else "LOW"
    if risk == "HIGH":
        route.append("ApprovalAgent")
    return {"ok": True, "doc_type": doc_type, "risk_level": risk, "agent_route": route, "requires_human": risk in ["HIGH", "MEDIUM"]}

@router.get("/queue")
def supervisor_queue():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT run_id, filename, state, created_at FROM pipeline_runs WHERE state='PENDING_APPROVAL' ORDER BY created_at DESC LIMIT 20")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return {"ok": True, "queue_size": len(rows), "items": [dict(r) for r in rows]}