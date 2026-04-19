"""
app/api/routes_dashboard_live.py
Bridge Hub — Real-time Dashboard Data Endpoints
"""
from fastapi import APIRouter, Request
from datetime import datetime
import psycopg2.extras
from app.api.db import get_db
from app.api.response_utils import error_response
from app.api.tenant_context import resolve_tenant_id

router = APIRouter(prefix="/dashboard/live", tags=["dashboard-live"])

_EMPTY_PNL = {"income": 0, "expenses": 0, "profit": 0, "profit_margin": 0}
_EMPTY_COUNTS = {"total": 0, "approved": 0, "pending": 0}


# ========== P&L ==========

@router.get("/pnl")
def get_pnl(request: Request, period: str = "month"):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur.execute("""
                SELECT
                    COALESCE(SUM(CASE WHEN credit_account LIKE '6%%' THEN amount ELSE 0 END), 0) as income,
                    COALESCE(SUM(CASE WHEN debit_account LIKE '7%%' THEN amount ELSE 0 END), 0) as expenses,
                    COUNT(*) as total_transactions,
                    COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved,
                    COUNT(CASE WHEN status = 'auto_approved' THEN 1 END) as auto_approved,
                    COUNT(CASE WHEN status = 'pending_approval' THEN 1 END) as pending
                FROM journal_drafts
                WHERE tenant_id = %s
                  AND status IN ('approved', 'auto_approved')
            """, (tenant_id,))
            row = dict(cur.fetchone())

            income = float(row["income"])
            expenses = float(row["expenses"])

            if income == 0 and expenses > 0:
                cur.execute("""
                    SELECT COALESCE(SUM(amount), 0) as estimated_income
                    FROM journal_drafts
                    WHERE tenant_id = %s
                      AND status IN ('approved', 'auto_approved')
                      AND debit_account LIKE '1%%'
                      AND credit_account NOT LIKE '7%%'
                """, (tenant_id,))
                est = cur.fetchone()
                income = float(est["estimated_income"]) if est else 0

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
                    "approved": row["approved"] + row["auto_approved"],
                    "pending": row["pending"],
                },
                "generated_at": datetime.now().isoformat(),
            }
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        return {
            "ok": False,
            "message": "P&L query failed",
            "error": str(e),
            "period": period,
            "tenant_id": tenant_id,
            "pnl": _EMPTY_PNL,
            "counts": _EMPTY_COUNTS,
            "generated_at": datetime.now().isoformat(),
        }


# ========== Cash Flow ==========

@router.get("/cashflow")
def get_cashflow(request: Request, days: int = 30):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
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
                  AND created_at >= NOW() - (INTERVAL '1 day' * %s)
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
    except Exception as e:
        return {
            "ok": False,
            "message": "Cashflow query failed",
            "error": str(e),
            "period_days": days,
            "tenant_id": tenant_id,
            "summary": {"total_inflow": 0, "total_outflow": 0, "net": 0},
            "chart": {"labels": [], "inflow": [], "outflow": []},
            "generated_at": datetime.now().isoformat(),
        }


# ========== KPI ==========

@router.get("/kpi")
def get_kpi(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
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
    except Exception as e:
        return error_response("KPI query failed", "KPI_ERROR", str(e))


# ========== Recent Activity ==========

@router.get("/activity")
def get_activity(request: Request, limit: int = 10):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
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
    except Exception as e:
        return error_response("Activity query failed", "ACTIVITY_ERROR", str(e))


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
