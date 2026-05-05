"""app/api/routes_cost_center.py — Cost Centers (department expense tracking)."""
import logging
from typing import Optional

from fastapi import APIRouter, Request, Query

from app.api.authz import require_permission
from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, http_error
from app.api.tenant_context import resolve_tenant_id

log = logging.getLogger(__name__)
router = APIRouter(prefix="/cost-centers", tags=["accounting"])

_CREATE_COST_CENTERS = """
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
"""


async def _ensure_tables(conn):
    await conn.execute(_CREATE_COST_CENTERS)
    await conn.execute("""
        ALTER TABLE journal_drafts
            ADD COLUMN IF NOT EXISTS cost_center_id INTEGER REFERENCES cost_centers(id) ON DELETE SET NULL
    """)
    try:
        await conn.execute("""
            ALTER TABLE expenses
                ADD COLUMN IF NOT EXISTS cost_center_id INTEGER REFERENCES cost_centers(id) ON DELETE SET NULL
        """)
    except Exception:
        pass


@router.get("")
async def list_cost_centers(request: Request, include_inactive: bool = Query(False)):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    async with get_conn() as conn:
        await _ensure_tables(conn)
        where = "tenant_id = %s" + ("" if include_inactive else " AND active = TRUE")
        rows = [dict(r) for r in await conn.fetch(_q(f"""
            SELECT id, code, name, department, description, active, created_at
            FROM cost_centers WHERE {where} ORDER BY code
        """), tenant_id)]

    return ok_response("Cost centers", {"items": rows, "count": len(rows)})


@router.post("")
async def create_cost_center(request: Request, payload: dict):
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    code = str(payload.get("code", "")).strip().upper()
    name = str(payload.get("name", "")).strip()
    if not code or not name:
        return http_error(400, "code and name are required", "MISSING_FIELDS")

    try:
        async with get_conn() as conn:
            await _ensure_tables(conn)
            row = await conn.fetchrow(_q("""
                INSERT INTO cost_centers (tenant_id, code, name, department, description)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, code) DO UPDATE
                  SET name=%s, department=%s, description=%s, active=TRUE
                RETURNING *
            """), tenant_id, code, name,
                payload.get("department"), payload.get("description"),
                name, payload.get("department"), payload.get("description"))
    except Exception as e:
        return http_error(500, str(e), "DB_ERROR")

    return ok_response("Cost center saved", dict(row))


@router.put("/{cc_id}")
async def update_cost_center(cc_id: int, request: Request, payload: dict):
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    try:
        async with get_conn() as conn:
            await _ensure_tables(conn)
            row = await conn.fetchrow(_q("""
                UPDATE cost_centers
                SET name=%s, department=%s, description=%s, active=%s
                WHERE id=%s AND tenant_id=%s
                RETURNING *
            """), payload.get("name"), payload.get("department"),
                payload.get("description"), payload.get("active", True),
                cc_id, tenant_id)
    except Exception as e:
        return http_error(500, str(e), "DB_ERROR")

    if not row:
        return http_error(404, "Cost center not found", "NOT_FOUND")
    return ok_response("Cost center updated", dict(row))


@router.delete("/{cc_id}")
async def deactivate_cost_center(cc_id: int, request: Request):
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    async with get_conn() as conn:
        await _ensure_tables(conn)
        await conn.execute(_q(
            "UPDATE cost_centers SET active=FALSE WHERE id=%s AND tenant_id=%s"
        ), cc_id, tenant_id)

    return ok_response("Cost center deactivated", {"id": cc_id})


@router.get("/analysis")
async def cost_center_analysis(
    request: Request,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """Spending breakdown by cost center."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    conds = ["jd.tenant_id = %s", "jd.status = 'posted'",
             "jd.cost_center_id IS NOT NULL", "jd.debit_account LIKE '7%%'"]
    params: list = [tenant_id]
    if date_from:
        conds.append("jd.date >= %s"); params.append(date_from)
    if date_to:
        conds.append("jd.date <= %s"); params.append(date_to)

    uncat_conds = ["jd.tenant_id = %s", "jd.status = 'posted'",
                   "jd.cost_center_id IS NULL", "jd.debit_account LIKE '7%%'"]
    uncat_params: list = [tenant_id]
    if date_from:
        uncat_conds.append("jd.date >= %s"); uncat_params.append(date_from)
    if date_to:
        uncat_conds.append("jd.date <= %s"); uncat_params.append(date_to)

    async with get_conn() as conn:
        await _ensure_tables(conn)
        rows = [dict(r) for r in await conn.fetch(_q(f"""
            SELECT
                cc.id, cc.code, cc.name, cc.department,
                COUNT(jd.id)        AS entry_count,
                ROUND(SUM(jd.amount)::numeric, 2) AS total_amount
            FROM journal_drafts jd
            JOIN cost_centers cc ON cc.id = jd.cost_center_id
            WHERE {' AND '.join(conds)}
            GROUP BY cc.id, cc.code, cc.name, cc.department
            ORDER BY total_amount DESC
        """), *params)]

        uncat = await conn.fetchrow(_q(f"""
            SELECT COUNT(*) AS entry_count, ROUND(SUM(amount)::numeric,2) AS total_amount
            FROM journal_drafts jd
            WHERE {' AND '.join(uncat_conds)}
        """), *uncat_params)

    grand_total = round(sum(float(r["total_amount"] or 0) for r in rows), 2)
    return ok_response("Cost center analysis", {
        "date_from": date_from,
        "date_to": date_to,
        "cost_centers": rows,
        "uncategorised": {
            "entry_count": int((uncat or {}).get("entry_count") or 0),
            "total_amount": float((uncat or {}).get("total_amount") or 0),
        },
        "grand_total": grand_total,
    })
