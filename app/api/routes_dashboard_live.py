"""
app/api/routes_dashboard_live.py
Bridge Hub — Real-time Dashboard Data Endpoints
არსებულ routes_dashboard.py-ს არ ეხება.
"""
from fastapi import APIRouter, Request
from datetime import datetime, timedelta
import psycopg2.extras
from app.api.db import get_db
from app.api.tenant_context import resolve_tenant_id

router = APIRouter(prefix="/dashboard/live", tags=["dashboard-live"])


# ========== P&L ==========

@router.get("/pnl")
def get_pnl(request: Request, period: str = "month"):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if period == "month":
            date_filter = "DATE_TRUNC('month', NOW())"
        elif period == "quarter":
            date_filter = "DATE_TRUNC('quarter', NOW())"
        elif period == "year":
            date_filter = "DATE_TRUNC('year', NOW())"
        else:
            date_filter = "DATE_TRUNC('month', NOW())"

        cur.execute(f"""
            SELECT
                COALESCE(SUM(CASE WHEN debit_account LIKE '6%%' THEN amount ELSE 0 END), 0) as income,
                COALESCE(SUM(CASE WHEN debit_account LIKE '7%%' THEN amount ELSE 0 END), 0) as expenses,
                COUNT(*) as total_transactions,
                COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved,
                COUNT(CASE WHEN status = 'pending_approval' THEN 1 END) as pending
            FROM journal_drafts
            WHERE tenant_id = %s
              AND status IN ('approved', 'auto_approved')
              AND created_at >= {date_filter}
        """, (tenant_id,))
        row = dict(cur.fetchone())

        income = float(row["income"])
        expenses = float(row["expenses"])
        profit = income - expenses

        return {
            "ok": True,
            "period": period,
            "tenant_id": tenant_id,
            "pnl": {
                "income": round(income, 2),
                "expenses": round(expenses, 2),
                "profit": round(profit, 2),
                "profit_margin": round(profit / income * 100, 2) if income > 0 else 0,
            },
            "counts": {
                "total": row["total_transactions"],
                "approved": row["approved"],
                "pending": row["pending"],
            },
            "generated_at": datetime.now().isoformat(),
        }
    finally:
        cur.close()
        conn.close()


# ========== Cash Flow ==========

@router.get("/cashflow")
def get_cashflow(request: Request, days: int = 30):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT
                DATE_TRUNC('day', created_at) as day,
                SUM(CASE WHEN credit_account LIKE '1%%' THEN amount ELSE 0 END) as outflow,
                SUM(CASE WHEN debit_account LIKE '1%%' THEN amount ELSE 0 END) as inflow,
                COUNT(*) as count
            FROM journal_drafts
            WHERE tenant_id = %s
              AND status IN ('approved', 'auto_approved')
              AND created_at >= NOW() - INTERVAL '%s days'
            GROUP BY day
            ORDER BY day ASC
        """, (tenant_id, days))

        rows = [dict(r) for r in cur.fetchall()]
        labels = [str(r["day"])[:10] for r in rows]
        inflows = [float(r["inflow"]) for r in rows]
        outflows = [float(r["outflow"]) for r in rows]

        total_inflow = sum(inflows)
        total_outflow = sum(outflows)

        return {
            "ok": True,
            "period_days": days,
            "tenant_id": tenant_id,
            "summary": {
                "total_inflow": round(total_inflow, 2),
                "total_outflow": round(total_outflow, 2),
                "net": round(total_inflow - total_outflow, 2),
            },
            "chart": {
                "labels": labels,
                "inflow": inflows,
                "outflow": outflows,
            },
            "generated_at": datetime.now().isoformat(),
        }
    finally:
        cur.close()
        conn.close()


# ========== KPI ==========

@router.get("/kpi")
def get_kpi(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved,
                COUNT(CASE WHEN status = 'auto_approved' THEN 1 END) as auto_approved,
                COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected,
                COUNT(CASE WHEN status = 'pending_approval' THEN 1 END) as pending,
                AVG(confidence) as avg_confidence,
                COUNT(CASE WHEN created_at >= NOW() - INTERVAL '24 hours' THEN 1 END) as last_24h
            FROM journal_drafts
            WHERE tenant_id = %s
        """, (tenant_id,))
        row = dict(cur.fetchone())

        total = row["total"] or 1
        auto_rate = round((row["auto_approved"] or 0) / total * 100, 1)
        approval_rate = round(((row["approved"] or 0) + (row["auto_approved"] or 0)) / total * 100, 1)

        cur.execute("""
            SELECT COUNT(*) as active_patterns
            FROM learning_patterns
            WHERE tenant_id = %s AND status = 'active'
        """, (tenant_id,))
        patterns = cur.fetchone()["active_patterns"]

        try:
            cur.execute("""
                SELECT COUNT(*) as total_feedback
                FROM learning_feedback
                WHERE tenant_id = %s
            """, (tenant_id,))
            feedback = cur.fetchone()["total_feedback"]
        except Exception:
            feedback = 0

        return {
            "ok": True,
            "tenant_id": tenant_id,
            "kpi": {
                "total_drafts": row["total"],
                "pending": row["pending"],
                "approved": row["approved"],
                "auto_approved": row["auto_approved"],
                "rejected": row["rejected"],
                "last_24h": row["last_24h"],
                "auto_approval_rate": auto_rate,
                "approval_rate": approval_rate,
                "avg_confidence": round(float(row["avg_confidence"] or 0), 3),
                "active_patterns": patterns,
                "total_feedback": feedback,
            },
            "generated_at": datetime.now().isoformat(),
        }
    finally:
        cur.close()
        conn.close()


# ========== Recent Activity ==========

@router.get("/activity")
def get_activity(request: Request, limit: int = 10):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT
                id, date, description, amount, status,
                account_code, confidence, created_at, source_type
            FROM journal_drafts
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (tenant_id, limit))
        items = [dict(r) for r in cur.fetchall()]

        return {
            "ok": True,
            "tenant_id": tenant_id,
            "count": len(items),
            "activity": items,
            "generated_at": datetime.now().isoformat(),
        }
    finally:
        cur.close()
        conn.close()


# ========== Summary (ყველა ერთად) ==========

@router.get("/summary")
def get_summary(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    pnl = get_pnl(request, "month")
    kpi = get_kpi(request)
    activity = get_activity(request, 5)

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "pnl": pnl.get("pnl"),
        "kpi": kpi.get("kpi"),
        "recent_activity": activity.get("activity"),
        "generated_at": datetime.now().isoformat(),
    }