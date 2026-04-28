"""app/api/routes_cost_center.py — Cost Centers (department expense tracking)."""
import logging
from typing import Optional

import psycopg2.extras
from fastapi import APIRouter, Request, Query

from app.api.authz import require_permission
from app.api.db import get_db
from app.api.response_utils import ok_response, http_error
from app.api.tenant_context import resolve_tenant_id

log = logging.getLogger(__name__)
router = APIRouter(prefix="/cost-centers", tags=["accounting"])


def _ensure_tables(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cost_centers (
            id          SERIAL PRIMARY KEY,
            tenant_id   TEXT NOT NULL DEFAULT 'default',
            code        TEXT NOT NULL,
            name        TEXT NOT NULL,
            department  TEXT,
            description TEXT,
            active      BOOLEAN DEFAULT TRUE,
            created_at  TIMESTAMP DEFAULT NOW(),
            UNIQUE(tenant_id, code)
        )
    """)
    # Add cost_center_id to journal_drafts lazily
    cur.execute("""
        ALTER TABLE journal_drafts
            ADD COLUMN IF NOT EXISTS cost_center_id INTEGER REFERENCES cost_centers(id) ON DELETE SET NULL
    """)
    # Add cost_center_id to expenses lazily
    try:
        cur.execute("""
            ALTER TABLE expenses
                ADD COLUMN IF NOT EXISTS cost_center_id INTEGER REFERENCES cost_centers(id) ON DELETE SET NULL
        """)
    except Exception:
        pass
    conn.commit()
    cur.close()


@router.get("")
def list_cost_centers(request: Request, include_inactive: bool = Query(False)):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    conn = get_db()
    try:
        _ensure_tables(conn)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        where = "tenant_id = %s" + ("" if include_inactive else " AND active = TRUE")
        cur.execute(f"""
            SELECT id, code, name, department, description, active, created_at
            FROM cost_centers WHERE {where} ORDER BY code
        """, (tenant_id,))
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
    finally:
        conn.close()

    return ok_response("Cost centers", {"items": rows, "count": len(rows)})


@router.post("")
def create_cost_center(request: Request, payload: dict):
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    code = str(payload.get("code", "")).strip().upper()
    name = str(payload.get("name", "")).strip()
    if not code or not name:
        return http_error(400, "code and name are required", "MISSING_FIELDS")

    conn = get_db()
    try:
        _ensure_tables(conn)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            INSERT INTO cost_centers (tenant_id, code, name, department, description)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, code) DO UPDATE
              SET name=%s, department=%s, description=%s, active=TRUE
            RETURNING *
        """, (
            tenant_id, code, name,
            payload.get("department"), payload.get("description"),
            name, payload.get("department"), payload.get("description"),
        ))
        row = dict(cur.fetchone())
        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        conn.close()
        return http_error(500, str(e), "DB_ERROR")
    finally:
        conn.close()

    return ok_response("Cost center saved", row)


@router.put("/{cc_id}")
def update_cost_center(cc_id: int, request: Request, payload: dict):
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    conn = get_db()
    try:
        _ensure_tables(conn)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            UPDATE cost_centers
            SET name=%s, department=%s, description=%s, active=%s
            WHERE id=%s AND tenant_id=%s
            RETURNING *
        """, (
            payload.get("name"), payload.get("department"),
            payload.get("description"), payload.get("active", True),
            cc_id, tenant_id,
        ))
        row = cur.fetchone()
        if not row:
            return http_error(404, "Cost center not found", "NOT_FOUND")
        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        conn.close()
        return http_error(500, str(e), "DB_ERROR")
    finally:
        conn.close()

    return ok_response("Cost center updated", dict(row))


@router.delete("/{cc_id}")
def deactivate_cost_center(cc_id: int, request: Request):
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_tables(conn)
        cur.execute("""
            UPDATE cost_centers SET active=FALSE
            WHERE id=%s AND tenant_id=%s
        """, (cc_id, tenant_id))
        conn.commit()
    finally:
        cur.close()
        conn.close()

    return ok_response("Cost center deactivated", {"id": cc_id})


@router.get("/analysis")
def cost_center_analysis(
    request: Request,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """Spending breakdown by cost center."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    conn = get_db()
    try:
        _ensure_tables(conn)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        conds = ["jd.tenant_id = %s", "jd.status IN ('approved','auto_approved','posted')",
                 "jd.cost_center_id IS NOT NULL", "jd.debit_account LIKE '7%'"]
        params = [tenant_id]
        if date_from:
            conds.append("jd.date >= %s"); params.append(date_from)
        if date_to:
            conds.append("jd.date <= %s"); params.append(date_to)

        cur.execute(f"""
            SELECT
                cc.id, cc.code, cc.name, cc.department,
                COUNT(jd.id)        AS entry_count,
                ROUND(SUM(jd.amount)::numeric, 2) AS total_amount
            FROM journal_drafts jd
            JOIN cost_centers cc ON cc.id = jd.cost_center_id
            WHERE {' AND '.join(conds)}
            GROUP BY cc.id, cc.code, cc.name, cc.department
            ORDER BY total_amount DESC
        """, params)
        rows = [dict(r) for r in cur.fetchall()]

        # Uncategorised
        cur.execute(f"""
            SELECT COUNT(*) AS entry_count, ROUND(SUM(amount)::numeric,2) AS total_amount
            FROM journal_drafts jd
            WHERE jd.tenant_id=%s AND jd.status IN ('approved','auto_approved','posted')
              AND jd.cost_center_id IS NULL AND jd.debit_account LIKE '7%'
              {"AND jd.date >= %s" if date_from else ""}
              {"AND jd.date <= %s" if date_to else ""}
        """, [tenant_id] + ([date_from] if date_from else []) + ([date_to] if date_to else []))
        uncat = cur.fetchone()
        cur.close()
    finally:
        conn.close()

    grand_total = round(sum(float(r["total_amount"] or 0) for r in rows), 2)
    return ok_response("Cost center analysis", {
        "date_from": date_from,
        "date_to": date_to,
        "cost_centers": rows,
        "uncategorised": {
            "entry_count": int(uncat["entry_count"] or 0),
            "total_amount": float(uncat["total_amount"] or 0),
        },
        "grand_total": grand_total,
    })
