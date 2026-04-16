from fastapi import APIRouter, Query
import psycopg2
import psycopg2.extras
from app.api.db import get_db

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/monthly")
def monthly_report():
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
            GROUP BY DATE_TRUNC('month', created_at)
            ORDER BY month DESC
            LIMIT 12
        """)
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


@router.get("/annual")
def annual_report():
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
        rows = [dict(r) for r in cur.fetchall()]
        return {"ok": True, "annual_reports": rows}

    finally:
        cur.close()
        conn.close()


@router.get("/audit-trail")
def audit_trail():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("""
            SELECT run_id, filename, state, created_at
            FROM pipeline_runs
            ORDER BY created_at DESC
            LIMIT 50
        """)
        rows = [dict(r) for r in cur.fetchall()]
        return {"ok": True, "pipeline_runs": rows}

    finally:
        cur.close()
        conn.close()


@router.get("/pnl")
def pnl_report(
    year: int | None = Query(None, description="Optional year filter, e.g. 2026"),
    month: int | None = Query(None, ge=1, le=12, description="Optional month filter 1-12"),
):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        conditions = ["1=1"]
        params = []

        if year is not None:
            conditions.append("EXTRACT(YEAR FROM date) = %s")
            params.append(year)

        if month is not None:
            conditions.append("EXTRACT(MONTH FROM date) = %s")
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
        profit = round(revenue - expenses, 2)

        return {
            "ok": True,
            "report": "pnl",
            "filters": {
                "year": year,
                "month": month,
            },
            "data": {
                "revenue": revenue,
                "expenses": expenses,
                "profit_before_tax": profit,
            },
            "note": "ეს არის მარტივი P&L ვერსია bank_transactions-ზე დაყრდნობით.",
        }

    finally:
        cur.close()
        conn.close()


@router.get("/cashflow")
def cashflow_report(
    year: int | None = Query(None, description="Optional year filter, e.g. 2026"),
    month: int | None = Query(None, ge=1, le=12, description="Optional month filter 1-12"),
):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        conditions = ["1=1"]
        params = []

        if year is not None:
            conditions.append("EXTRACT(YEAR FROM date) = %s")
            params.append(year)

        if month is not None:
            conditions.append("EXTRACT(MONTH FROM date) = %s")
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
        net_cashflow = round(cash_in - cash_out, 2)

        return {
            "ok": True,
            "report": "cashflow",
            "filters": {
                "year": year,
                "month": month,
            },
            "data": {
                "cash_in": cash_in,
                "cash_out": cash_out,
                "net_cashflow": net_cashflow,
            },
            "note": "ეს არის მარტივი Cash Flow ვერსია bank_transactions-ზე დაყრდნობით.",
        }

    finally:
        cur.close()
        conn.close()