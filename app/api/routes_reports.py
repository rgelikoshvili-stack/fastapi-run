from fastapi import APIRouter, Query, Request
import psycopg2
import psycopg2.extras
from app.api.db import get_db
from app.api.authz import require_permission

router = APIRouter(prefix="/reports", tags=["reports"])


# ===============================
# MONTHLY REPORT
# ===============================
@router.get("/monthly")
def monthly_report(request: Request):
    require_permission(request, "reports:read")
    tenant_id = getattr(request.state, "tenant_id", "default")

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("""
            SELECT DATE_TRUNC('month', created_at) as month,
                   COUNT(*) as total_docs,
                   SUM(CASE WHEN state='APPROVED' THEN 1 ELSE 0 END) as approved,
                   SUM(CASE WHEN state='REJECTED' THEN 1 ELSE 0 END) as rejected
            FROM pipeline_runs
            GROUP BY DATE_TRUNC('month', created_at)
            ORDER BY month DESC
            LIMIT 12
        """)
        rows = cur.fetchall()

        cur.execute("""
            SELECT DATE_TRUNC('month', created_at) as month,
                   SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as inflow,
                   SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as outflow
            FROM bank_transactions
            WHERE tenant_id = %s
            GROUP BY DATE_TRUNC('month', created_at)
            ORDER BY month DESC
            LIMIT 12
        """, (tenant_id,))
        tx_rows = {str(r["month"])[:7]: dict(r) for r in cur.fetchall()}

        result = []
        for r in rows:
            m = str(r["month"])[:7]
            tx = tx_rows.get(m, {})
            result.append({
                "month": m,
                "documents": {
                    "total": r["total_docs"],
                    "approved": r["approved"],
                    "rejected": r["rejected"],
                },
                "financials": {
                    "inflow": round(float(tx.get("inflow") or 0), 2),
                    "outflow": round(float(tx.get("outflow") or 0), 2),
                },
            })

        return {"ok": True, "monthly_reports": result}

    finally:
        cur.close()
        conn.close()


# ===============================
# ANNUAL REPORT
# ===============================
@router.get("/annual")
def annual_report(request: Request):
    require_permission(request, "reports:read")

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("""
            SELECT EXTRACT(YEAR FROM created_at) as year,
                   COUNT(*) as total
            FROM pipeline_runs
            GROUP BY year
            ORDER BY year DESC
        """)
        return {"ok": True, "annual_reports": [dict(r) for r in cur.fetchall()]}

    finally:
        cur.close()
        conn.close()


# ===============================
# AUDIT TRAIL
# ===============================
@router.get("/audit-trail")
def audit_trail(request: Request):
    require_permission(request, "reports:read")

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("""
            SELECT run_id, filename, state, created_at
            FROM pipeline_runs
            ORDER BY created_at DESC
            LIMIT 50
        """)
        return {"ok": True, "pipeline_runs": [dict(r) for r in cur.fetchall()]}

    finally:
        cur.close()
        conn.close()


# ===============================
# P&L
# ===============================
@router.get("/pnl")
def pnl_report(
    request: Request,
    year: int | None = Query(None),
    month: int | None = Query(None, ge=1, le=12),
):
    require_permission(request, "reports:read")
    tenant_id = getattr(request.state, "tenant_id", "default")

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        conditions = ["tenant_id = %s"]
        params = [tenant_id]

        conditions.append("date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'")

        if year:
            conditions.append("EXTRACT(YEAR FROM date::date) = %s")
            params.append(year)

        if month:
            conditions.append("EXTRACT(MONTH FROM date::date) = %s")
            params.append(month)

        where_clause = " AND ".join(conditions)

        cur.execute(f"""
            SELECT
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as revenue,
                COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as expenses
            FROM bank_transactions
            WHERE {where_clause}
        """, params)

        row = cur.fetchone() or {}

        revenue = round(float(row.get("revenue") or 0), 2)
        expenses = round(float(row.get("expenses") or 0), 2)

        return {
            "ok": True,
            "report": "pnl",
            "data": {
                "revenue": revenue,
                "expenses": expenses,
                "profit_before_tax": round(revenue - expenses, 2),
            },
            "note": "ეს არის მარტივი P&L ვერსია bank_transactions-ზე დაყრდნობით.",
        }

    finally:
        cur.close()
        conn.close()


# ===============================
# CASH FLOW
# ===============================
@router.get("/cashflow")
def cashflow_report(
    request: Request,
    year: int | None = Query(None),
    month: int | None = Query(None, ge=1, le=12),
):
    require_permission(request, "reports:read")
    tenant_id = getattr(request.state, "tenant_id", "default")

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        conditions = ["tenant_id = %s"]
        params = [tenant_id]

        conditions.append("date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'")

        if year:
            conditions.append("EXTRACT(YEAR FROM date::date) = %s")
            params.append(year)

        if month:
            conditions.append("EXTRACT(MONTH FROM date::date) = %s")
            params.append(month)

        where_clause = " AND ".join(conditions)

        cur.execute(f"""
            SELECT
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as cash_in,
                COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as cash_out
            FROM bank_transactions
            WHERE {where_clause}
        """, params)

        row = cur.fetchone() or {}

        cash_in = round(float(row.get("cash_in") or 0), 2)
        cash_out = round(float(row.get("cash_out") or 0), 2)

        return {
            "ok": True,
            "report": "cashflow",
            "data": {
                "cash_in": cash_in,
                "cash_out": cash_out,
                "net_cashflow": round(cash_in - cash_out, 2),
            },
            "note": "ეს არის მარტივი Cash Flow ვერსია bank_transactions-ზე დაყრდნობით.",
        }

    finally:
        cur.close()
        conn.close()