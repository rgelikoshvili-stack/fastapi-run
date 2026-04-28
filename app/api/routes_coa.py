from fastapi import APIRouter, HTTPException
import psycopg2

import psycopg2.extras
from app.api.db import get_db

router = APIRouter(prefix="/coa", tags=["coa"])

@router.get("/list")
def coa_list(category: str = None):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if category:
        cur.execute("SELECT * FROM coa WHERE category=%s AND is_active=TRUE ORDER BY code", (category,))
    else:
        cur.execute("SELECT * FROM coa WHERE is_active=TRUE ORDER BY code")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return {"ok": True, "count": len(rows), "accounts": [dict(r) for r in rows]}

@router.get("/get/{code}")
def coa_get(code: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM coa WHERE code=%s", (code,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        raise HTTPException(404, f"Account {code} not found")
    return {"ok": True, "account": dict(row)}

@router.get("/search")
def coa_search(q: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM coa WHERE (name_ka ILIKE %s OR name_en ILIKE %s OR code ILIKE %s) AND is_active=TRUE ORDER BY code",
                (f"%{q}%", f"%{q}%", f"%{q}%"))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return {"ok": True, "count": len(rows), "accounts": [dict(r) for r in rows]}

@router.get("/categories")
def coa_categories():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT DISTINCT category, COUNT(*) as count FROM coa WHERE is_active=TRUE GROUP BY category ORDER BY category")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return {"ok": True, "categories": [dict(r) for r in rows]}


@router.get("/summary")
def coa_summary():
    """Breakdown of chart of accounts by account type range."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT COUNT(*) as total FROM coa WHERE is_active=TRUE")
        total = (cur.fetchone() or {}).get("total", 0)

        cur.execute("""
            SELECT
                CASE
                    WHEN code LIKE '1%%' THEN 'assets'
                    WHEN code LIKE '2%%' THEN 'assets'
                    WHEN code LIKE '3%%' THEN 'liabilities'
                    WHEN code LIKE '4%%' THEN 'equity'
                    WHEN code LIKE '6%%' THEN 'revenue'
                    WHEN code LIKE '7%%' THEN 'expenses'
                    WHEN code LIKE '8%%' THEN 'other'
                    ELSE 'other'
                END AS type,
                COUNT(*) AS count
            FROM coa
            WHERE is_active=TRUE
            GROUP BY 1
            ORDER BY 1
        """)
        breakdown = {r["type"]: int(r["count"]) for r in cur.fetchall()}
    finally:
        cur.close()
        conn.close()

    return {
        "ok": True,
        "total_accounts": int(total),
        "breakdown": breakdown,
    }
