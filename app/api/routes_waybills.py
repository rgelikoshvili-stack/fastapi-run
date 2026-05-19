"""app/api/routes_waybills.py — Waybill (ზედნადები) CRUD and stats endpoints."""
import logging
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel
from typing import Optional

from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, error_response
from app.api.authz import require_permission
from app.api.tenant_context import resolve_tenant_id

log = logging.getLogger(__name__)

router = APIRouter(prefix="/waybills", tags=["waybills"])

VALID_STATUSES = ("imported", "matched", "corrected", "cancelled")


class WaybillCreate(BaseModel):
    waybill_number: str
    waybill_date: Optional[str] = None
    seller_inn: Optional[str] = None
    seller_name: Optional[str] = None
    buyer_inn: Optional[str] = None
    buyer_name: Optional[str] = None
    transport_from: Optional[str] = None
    transport_to: Optional[str] = None
    vehicle_number: Optional[str] = None
    driver_name: Optional[str] = None
    subtotal: Optional[float] = None
    vat_amount: Optional[float] = None
    total_amount: Optional[float] = None
    notes: Optional[str] = None


class WaybillStatusUpdate(BaseModel):
    status: str


@router.get("/stats")
async def waybill_stats(request: Request):
    """Return waybill counts by status. All values are integers, never null."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            rows = await conn.fetch(_q("""
                SELECT status, COUNT(*) AS cnt
                FROM waybills
                WHERE tenant_id = %s
                GROUP BY status
            """), tenant_id)
            total = await conn.fetchval(_q(
                "SELECT COUNT(*) FROM waybills WHERE tenant_id = %s"
            ), tenant_id) or 0
            matched = await conn.fetchval(_q(
                "SELECT COUNT(*) FROM waybills WHERE tenant_id = %s AND status = 'matched'"
            ), tenant_id) or 0
            unconfirmed = await conn.fetchval(_q(
                "SELECT COUNT(*) FROM waybills WHERE tenant_id = %s AND status = 'imported'"
            ), tenant_id) or 0
            discrepancy = await conn.fetchval(_q("""
                SELECT COUNT(DISTINCT w.id)
                FROM waybills w
                JOIN triangle_matches tm ON tm.waybill_id = w.id AND tm.tenant_id = w.tenant_id
                WHERE w.tenant_id = %s AND tm.match_status = 'discrepancy'
            """), tenant_id) or 0

        by_status = {r["status"]: int(r["cnt"]) for r in rows}
        return ok_response("Waybill stats", {
            "total": int(total),
            "matched": int(matched),
            "unconfirmed": int(unconfirmed),
            "discrepancy": int(discrepancy),
            "cancelled": int(by_status.get("cancelled", 0)),
            "corrected": int(by_status.get("corrected", 0)),
            "by_status": by_status,
            "tenant_id": tenant_id,
        })
    except Exception as e:
        log.warning("waybill_stats error: %s", e)
        return ok_response("Waybill stats (empty)", {
            "total": 0, "matched": 0, "unconfirmed": 0,
            "discrepancy": 0, "cancelled": 0, "corrected": 0,
            "by_status": {}, "tenant_id": tenant_id,
        })


@router.get("/list")
async def list_waybills(
    request: Request,
    q: str = Query(None),
    status: str = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List waybills with triangle-match status. Never returns 500 for empty table."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        conditions = ["w.tenant_id = %s"]
        params: list = [tenant_id]
        if status:
            conditions.append("w.status = %s")
            params.append(status)
        if q:
            conditions.append(
                "(w.waybill_number ILIKE %s OR w.seller_inn ILIKE %s"
                " OR w.buyer_inn ILIKE %s OR w.seller_name ILIKE %s OR w.buyer_name ILIKE %s)"
            )
            like = f"%{q}%"
            params += [like, like, like, like, like]
        where = "WHERE " + " AND ".join(conditions)

        async with get_conn() as conn:
            rows = [dict(r) for r in await conn.fetch(_q(f"""
                SELECT w.id, w.waybill_number, w.seller_inn, w.seller_name,
                       w.buyer_inn, w.buyer_name, w.waybill_date,
                       w.subtotal, w.vat_amount, w.total_amount,
                       w.transport_from, w.transport_to, w.vehicle_number,
                       w.status, w.version, w.notes, w.created_at,
                       tm.match_status, tm.match_score,
                       tm.tax_invoice_id, tm.commercial_invoice_id, tm.id AS match_id
                FROM waybills w
                LEFT JOIN triangle_matches tm
                  ON tm.waybill_id = w.id AND tm.tenant_id = w.tenant_id
                {where}
                ORDER BY w.created_at DESC
                LIMIT %s OFFSET %s
            """), *params, limit, offset)]
            total = await conn.fetchval(_q(
                f"SELECT COUNT(*) FROM waybills w {where}"
            ), *params) or 0

        return ok_response("Waybills", {
            "total": int(total), "limit": limit, "offset": offset,
            "items": rows, "tenant_id": tenant_id,
        })
    except Exception as e:
        log.warning("list_waybills error: %s", e)
        return ok_response("Waybills (empty)", {
            "total": 0, "limit": limit, "offset": offset,
            "items": [], "tenant_id": tenant_id,
        })


@router.post("/create")
async def create_waybill(data: WaybillCreate, request: Request):
    """Create a waybill record manually (no file upload required)."""
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            wid = await conn.fetchval(_q("""
                INSERT INTO waybills
                    (tenant_id, waybill_number, waybill_date, seller_inn, seller_name,
                     buyer_inn, buyer_name, transport_from, transport_to,
                     vehicle_number, driver_name, subtotal, vat_amount, total_amount, notes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """), tenant_id, data.waybill_number, data.waybill_date,
                data.seller_inn, data.seller_name, data.buyer_inn, data.buyer_name,
                data.transport_from, data.transport_to, data.vehicle_number, data.driver_name,
                data.subtotal, data.vat_amount, data.total_amount, data.notes)
    except Exception as e:
        return error_response("Create failed", "CREATE_ERROR", str(e))
    return ok_response("Waybill created", {
        "id": wid, "waybill_number": data.waybill_number,
        "status": "imported", "tenant_id": tenant_id,
    })


@router.get("/{waybill_id}")
async def get_waybill(waybill_id: int, request: Request):
    """Get a single waybill with its triangle match info."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(_q("""
                SELECT w.*, tm.match_status, tm.match_score, tm.id AS match_id,
                       tm.tax_invoice_id, tm.commercial_invoice_id
                FROM waybills w
                LEFT JOIN triangle_matches tm
                  ON tm.waybill_id = w.id AND tm.tenant_id = w.tenant_id
                WHERE w.id = %s AND w.tenant_id = %s
            """), waybill_id, tenant_id)
    except Exception as e:
        return error_response("DB error", "DB_ERROR", str(e))
    if not row:
        return error_response("Waybill not found", "NOT_FOUND", f"id={waybill_id}")
    return ok_response("Waybill", dict(row))


@router.post("/{waybill_id}/status")
async def update_waybill_status(
    waybill_id: int,
    data: WaybillStatusUpdate,
    request: Request,
):
    """Update waybill status."""
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    if data.status not in VALID_STATUSES:
        return error_response(
            "Invalid status", "VALIDATION_ERROR",
            f"Valid values: {list(VALID_STATUSES)}",
        )
    try:
        async with get_conn() as conn:
            tag = await conn.execute(_q("""
                UPDATE waybills SET status = %s, updated_at = NOW()
                WHERE id = %s AND tenant_id = %s
            """), data.status, waybill_id, tenant_id)
    except Exception as e:
        return error_response("Update failed", "UPDATE_ERROR", str(e))
    if int(tag.split()[-1]) == 0:
        return error_response("Waybill not found", "NOT_FOUND", f"id={waybill_id}")
    return ok_response("Status updated", {
        "id": waybill_id, "status": data.status, "tenant_id": tenant_id,
    })
