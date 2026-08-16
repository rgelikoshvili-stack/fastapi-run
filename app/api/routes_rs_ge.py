"""app/api/routes_rs_ge.py

RS.ge Sync — waybill and invoice synchronisation between RS.ge portal
and Bridge Hub accounting.

All reads come from the local Bridge Hub DB (populated via XML import or
prior syncs). Live RS.ge SOAP calls are stubs — activate by setting
RSGE_LIVE_ACTIONS_ENABLED=true and wiring a SOAP client.

Endpoints:
  GET  /rs-ge/waybills                    list waybills (local DB)
  GET  /rs-ge/waybills/by-number          fetch waybill by number (local DB)
  GET  /rs-ge/waybills/goods-by-number    goods by waybill number
  POST /rs-ge/waybills/sync-by-number     store received waybill to DB
  POST /rs-ge/waybills/sync-selected      store waybills by rsge_id list
  GET  /rs-ge/waybills/{id}/goods         goods for a local waybill
  GET  /rs-ge/waybills/{id}/linked-invoice  linked RS.ge tax invoice
  PATCH /rs-ge/waybills/{id}/edit-meta    update date/goods/amount
  POST /rs-ge/waybills/{id}/create-draft  create journal draft from waybill
  GET  /rs-ge/documents                   list RS.ge tax invoices (local DB)
  POST /rs-ge/documents/sync-selected     sync invoice(s) to local DB
  POST /rs-ge/documents/{id}/create-evidence  create evidence record
  POST /rs-ge/documents/{id}/create-draft create draft from invoice
  POST /rs-ge/suggest-draft               suggest Dr/Cr via partner/item map
  GET  /rs-ge/own-tin                     get company own TIN
  POST /rs-ge/own-tin                     save company own TIN
  GET  /rs-ge/partner-map                 list TIN → Cr-account mappings
  POST /rs-ge/partner-map                 create partner mapping
  DELETE /rs-ge/partner-map/{id}          delete partner mapping
  GET  /rs-ge/item-map                    list item-code → Dr-account mappings
  DELETE /rs-ge/item-map/{id}             delete item mapping
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Request, Query
from pydantic import BaseModel

from app.api.authz import require_permission
from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, error_response
from app.api.tenant_context import resolve_tenant_id

log = logging.getLogger(__name__)

router = APIRouter(prefix="/rs-ge", tags=["rs-ge"])

# ── Self-migrating DDL (idempotent) ─────────────────────────────────────────

_DDL_OWN_TIN = """
    CREATE TABLE IF NOT EXISTS rsge_own_tin (
        id         SERIAL PRIMARY KEY,
        tenant_id  TEXT NOT NULL UNIQUE,
        own_tin    TEXT NOT NULL,
        updated_at TIMESTAMPTZ DEFAULT NOW()
    )
"""

_DDL_PARTNER_MAP = """
    CREATE TABLE IF NOT EXISTS rsge_partner_map (
        id           SERIAL PRIMARY KEY,
        tenant_id    TEXT NOT NULL,
        tin          TEXT NOT NULL,
        partner_name TEXT,
        account_code TEXT NOT NULL,
        created_at   TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE (tenant_id, tin)
    )
"""

_DDL_ITEM_MAP = """
    CREATE TABLE IF NOT EXISTS rsge_item_map (
        id           SERIAL PRIMARY KEY,
        tenant_id    TEXT NOT NULL,
        item_code    TEXT NOT NULL,
        item_name    TEXT,
        account_code TEXT NOT NULL,
        vat_exempt   BOOLEAN DEFAULT FALSE,
        created_at   TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE (tenant_id, item_code)
    )
"""

# Extra columns on existing waybills table — all idempotent IF NOT EXISTS
_DDL_WAYBILL_EXTRAS = [
    "ALTER TABLE waybills ADD COLUMN IF NOT EXISTS direction     TEXT",
    "ALTER TABLE waybills ADD COLUMN IF NOT EXISTS rsge_id       TEXT",
    "ALTER TABLE waybills ADD COLUMN IF NOT EXISTS rsge_status   TEXT",
    "ALTER TABLE waybills ADD COLUMN IF NOT EXISTS begin_date    TIMESTAMPTZ",
    "ALTER TABLE waybills ADD COLUMN IF NOT EXISTS seller_tin    TEXT",
    "ALTER TABLE waybills ADD COLUMN IF NOT EXISTS buyer_tin     TEXT",
    "ALTER TABLE waybills ADD COLUMN IF NOT EXISTS car_number    TEXT",
    "ALTER TABLE waybills ADD COLUMN IF NOT EXISTS start_address TEXT",
    "ALTER TABLE waybills ADD COLUMN IF NOT EXISTS end_address   TEXT",
    "ALTER TABLE waybills ADD COLUMN IF NOT EXISTS full_amount   NUMERIC(15,2)",
    "ALTER TABLE waybills ADD COLUMN IF NOT EXISTS comment       TEXT",
    "ALTER TABLE waybills ADD COLUMN IF NOT EXISTS draft_id      INTEGER",
    "ALTER TABLE waybills ADD COLUMN IF NOT EXISTS draft_status  TEXT",
    "ALTER TABLE waybills ADD COLUMN IF NOT EXISTS seller_name   TEXT",
    "ALTER TABLE waybills ADD COLUMN IF NOT EXISTS buyer_name    TEXT",
    "ALTER TABLE waybills ADD COLUMN IF NOT EXISTS driver_name   TEXT",
    "ALTER TABLE waybills ADD COLUMN IF NOT EXISTS driver_tin    TEXT",
    # unique constraint for rsge_id upsert
    "CREATE UNIQUE INDEX IF NOT EXISTS waybills_tenant_rsge_id ON waybills(tenant_id, rsge_id) WHERE rsge_id IS NOT NULL",
]


async def _ensure_schemas(conn) -> None:
    for ddl in (_DDL_OWN_TIN, _DDL_PARTNER_MAP, _DDL_ITEM_MAP):
        try:
            await conn.execute(ddl.strip())
        except Exception as exc:
            log.debug("rs_ge schema create skipped: %s", exc)
    for stmt in _DDL_WAYBILL_EXTRAS:
        try:
            await conn.execute(stmt)
        except Exception as exc:
            log.debug("waybill extras skipped: %s", exc)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_line_items(raw) -> list:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    if isinstance(raw, list):
        return raw
    return []


def _normalise_goods(items: list) -> list:
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        result.append({
            "bar_code":    item.get("bar_code") or item.get("code") or "",
            "product_code": item.get("product_code") or item.get("code") or "",
            "name":        item.get("name") or item.get("description") or "",
            "unit_name":   item.get("unit_name") or item.get("unit") or "",
            "quantity":    item.get("quantity") or item.get("qty") or "",
            "price":       item.get("price") or "",
            "amount":      item.get("amount") or item.get("subtotal") or "",
            "vat_type":    str(item.get("vat_type", "1")),
        })
    return result


def _wb_to_frontend(row: dict, own_tin: str = "") -> dict:
    """Map a `waybills` DB row to the rsge-sync.html wire format."""
    seller_inn = row.get("seller_tin") or row.get("seller_inn") or ""
    buyer_inn  = row.get("buyer_tin")  or row.get("buyer_inn")  or ""

    direction = row.get("direction") or ""
    if not direction:
        if own_tin and buyer_inn == own_tin:
            direction = "received"
        elif own_tin and seller_inn == own_tin:
            direction = "sent"
        else:
            direction = "received"

    goods_list = _normalise_goods(_parse_line_items(row.get("line_items")))

    begin_date = row.get("begin_date") or row.get("waybill_date")
    if begin_date is not None:
        begin_date = str(begin_date)

    return {
        "local_id":     row.get("id"),
        "rsge_id":      row.get("rsge_id") or str(row.get("id", "")),
        "waybill_number": row.get("waybill_number") or "",
        "direction":    direction,
        "seller_name":  row.get("seller_name") or "",
        "seller_tin":   seller_inn,
        "buyer_name":   row.get("buyer_name") or "",
        "buyer_tin":    buyer_inn,
        "begin_date":   begin_date or "",
        "transport_date": str(row.get("waybill_date") or ""),
        "full_amount":  float(row.get("full_amount") or row.get("total_amount") or 0),
        "status":       row.get("rsge_status") or row.get("status") or "",
        "comment":      row.get("comment") or "",
        "driver_name":  row.get("driver_name") or "",
        "car_number":   row.get("car_number") or row.get("vehicle_number") or "",
        "start_address": row.get("start_address") or row.get("transport_from") or "",
        "end_address":  row.get("end_address")   or row.get("transport_to")   or "",
        "goods_list":   goods_list,
        "draft_id":     row.get("draft_id"),
        "draft_status": row.get("draft_status"),
        "synced":       True,
    }


async def _get_own_tin(conn, tenant_id: str) -> str:
    try:
        row = await conn.fetchrow(
            "SELECT own_tin FROM rsge_own_tin WHERE tenant_id=$1", tenant_id
        )
        return row["own_tin"] if row else ""
    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# OWN TIN
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/own-tin")
async def get_own_tin(request: Request):
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            await _ensure_schemas(conn)
            own_tin = await _get_own_tin(conn, tenant_id)
        return ok_response("ok", {"own_tin": own_tin})
    except Exception as exc:
        log.error("get_own_tin error: %s", exc)
        return ok_response("ok", {"own_tin": ""})


class OwnTinPayload(BaseModel):
    tin: str


@router.post("/own-tin")
async def save_own_tin(body: OwnTinPayload, request: Request):
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    tin = (body.tin or "").strip()
    if not tin:
        return error_response("tin is required", "VALIDATION_ERROR", "")
    try:
        async with get_conn() as conn:
            await _ensure_schemas(conn)
            await conn.execute(
                """
                INSERT INTO rsge_own_tin (tenant_id, own_tin, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (tenant_id) DO UPDATE SET own_tin=$2, updated_at=NOW()
                """,
                tenant_id, tin,
            )
        return ok_response("Own TIN saved", {"own_tin": tin})
    except Exception as exc:
        log.error("save_own_tin error: %s", exc)
        return error_response(f"Failed to save TIN: {exc}", "DB_ERROR", str(exc))


# ══════════════════════════════════════════════════════════════════════════════
# PARTNER MAP  (TIN → Cr account)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/partner-map")
async def list_partner_map(request: Request):
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            await _ensure_schemas(conn)
            rows = await conn.fetch(
                "SELECT id, tin, partner_name, account_code FROM rsge_partner_map "
                "WHERE tenant_id=$1 ORDER BY id",
                tenant_id,
            )
        return ok_response("ok", [dict(r) for r in rows])
    except Exception as exc:
        log.error("list_partner_map error: %s", exc)
        return ok_response("ok", [])


class PartnerMapPayload(BaseModel):
    tin: str
    partner_name: Optional[str] = ""
    account_code: str


@router.post("/partner-map")
async def create_partner_map(body: PartnerMapPayload, request: Request):
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    tin = (body.tin or "").strip()
    if not tin or not body.account_code:
        return error_response("tin and account_code required", "VALIDATION_ERROR", "")
    try:
        async with get_conn() as conn:
            await _ensure_schemas(conn)
            row = await conn.fetchrow(
                """
                INSERT INTO rsge_partner_map (tenant_id, tin, partner_name, account_code)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (tenant_id, tin) DO UPDATE
                    SET partner_name=EXCLUDED.partner_name,
                        account_code=EXCLUDED.account_code
                RETURNING id
                """,
                tenant_id, tin, body.partner_name or "", body.account_code,
            )
        return ok_response("Partner map saved", {"id": row["id"]})
    except Exception as exc:
        log.error("create_partner_map error: %s", exc)
        return error_response(str(exc)[:200], "DB_ERROR", str(exc))


@router.delete("/partner-map/{mapping_id}")
async def delete_partner_map(mapping_id: int, request: Request):
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            await conn.execute(
                "DELETE FROM rsge_partner_map WHERE id=$1 AND tenant_id=$2",
                mapping_id, tenant_id,
            )
        return ok_response("Deleted", {})
    except Exception as exc:
        return error_response(str(exc)[:200], "DB_ERROR", str(exc))


# ══════════════════════════════════════════════════════════════════════════════
# ITEM MAP  (barcode/product-code → Dr account)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/item-map")
async def list_item_map(request: Request):
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            await _ensure_schemas(conn)
            rows = await conn.fetch(
                "SELECT id, item_code, item_name, account_code, vat_exempt "
                "FROM rsge_item_map WHERE tenant_id=$1 ORDER BY id",
                tenant_id,
            )
        return ok_response("ok", [dict(r) for r in rows])
    except Exception as exc:
        log.error("list_item_map error: %s", exc)
        return ok_response("ok", [])


@router.delete("/item-map/{mapping_id}")
async def delete_item_map(mapping_id: int, request: Request):
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            await conn.execute(
                "DELETE FROM rsge_item_map WHERE id=$1 AND tenant_id=$2",
                mapping_id, tenant_id,
            )
        return ok_response("Deleted", {})
    except Exception as exc:
        return error_response(str(exc)[:200], "DB_ERROR", str(exc))


# ══════════════════════════════════════════════════════════════════════════════
# SUGGEST DRAFT  (partner/item mapping lookup)
# ══════════════════════════════════════════════════════════════════════════════

class SuggestDraftPayload(BaseModel):
    seller_tin: Optional[str] = ""
    goods_list: Optional[list] = []


@router.post("/suggest-draft")
async def suggest_draft(body: SuggestDraftPayload, request: Request):
    require_permission(request, "documents:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            await _ensure_schemas(conn)

            cr_account = None
            if (body.seller_tin or "").strip():
                pm = await conn.fetchrow(
                    "SELECT account_code FROM rsge_partner_map WHERE tenant_id=$1 AND tin=$2",
                    tenant_id, body.seller_tin.strip(),
                )
                if pm:
                    cr_account = pm["account_code"]

            dr_account = None
            for item in (body.goods_list or []):
                code = (item.get("bar_code") or item.get("product_code") or "").strip()
                if not code:
                    continue
                im = await conn.fetchrow(
                    "SELECT account_code FROM rsge_item_map WHERE tenant_id=$1 AND item_code=$2",
                    tenant_id, code,
                )
                if im:
                    dr_account = im["account_code"]
                    break

        if cr_account or dr_account:
            return ok_response("ok", {
                "credit_account": cr_account,
                "debit_account":  dr_account,
                "source": "mapping",
            })
        return ok_response("ok", {"credit_account": None, "debit_account": None, "source": "default"})
    except Exception as exc:
        log.error("suggest_draft error: %s", exc)
        return ok_response("ok", {"source": "default"})


# ══════════════════════════════════════════════════════════════════════════════
# WAYBILLS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/waybills")
async def list_waybills(
    request: Request,
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=500),
):
    """List waybills from local DB.  date_from/date_to filter on waybill_date."""
    require_permission(request, "documents:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            await _ensure_schemas(conn)
            own_tin = await _get_own_tin(conn, tenant_id)

            # Build WHERE clause
            conditions = ["w.tenant_id=$1", "w.source='rsge_import'"]
            args: list = [tenant_id]
            idx = 2
            if date_from:
                conditions.append(
                    f"(w.waybill_date >= ${idx}::timestamptz OR w.begin_date >= ${idx}::timestamptz)"
                )
                args.append(date_from); idx += 1
            if date_to:
                conditions.append(
                    f"(w.waybill_date <= ${idx}::timestamptz OR w.begin_date <= ${idx}::timestamptz)"
                )
                args.append(date_to); idx += 1

            where = " AND ".join(conditions)
            rows = await conn.fetch(
                f"""
                SELECT w.*
                FROM waybills w
                WHERE {where}
                ORDER BY COALESCE(w.begin_date, w.waybill_date, w.created_at) DESC
                LIMIT ${idx}
                """,
                *args, limit,
            )

        waybills = [_wb_to_frontend(dict(r), own_tin) for r in rows]
        return ok_response("ok", {"waybills": waybills})
    except Exception as exc:
        log.error("list_waybills error: %s", exc)
        return ok_response("ok", {"waybills": [], "soap_error": str(exc)[:300]})


@router.get("/waybills/by-number")
async def get_waybill_by_number(
    request: Request,
    number: str = Query(...),
):
    """Fetch a single waybill by number from local DB.

    The frontend calls this when the accountant types a number in the
    'Download by number' field.  We look in the local DB only — RS.ge
    SOAP calls are not active.
    """
    require_permission(request, "documents:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            await _ensure_schemas(conn)
            own_tin = await _get_own_tin(conn, tenant_id)
            row = await conn.fetchrow(
                "SELECT * FROM waybills WHERE tenant_id=$1 AND waybill_number=$2 LIMIT 1",
                tenant_id, number.strip(),
            )
        if not row:
            return error_response(
                f"Waybill #{number} not found in local database. "
                "Import the RS.ge XML export first via Settings → RS.ge Documents.",
                "NOT_FOUND",
                f"waybill_number={number}",
            )
        return ok_response("ok", _wb_to_frontend(dict(row), own_tin))
    except Exception as exc:
        log.error("get_waybill_by_number error: %s", exc)
        return error_response(str(exc)[:200], "DB_ERROR", str(exc))


@router.get("/waybills/goods-by-number")
async def get_goods_by_number(
    request: Request,
    waybill_number: str = Query(...),
):
    """Return goods lines for a waybill looked up by number."""
    require_permission(request, "documents:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM waybills WHERE tenant_id=$1 AND waybill_number=$2 LIMIT 1",
                tenant_id, waybill_number.strip(),
            )
        if not row:
            return error_response("Waybill not found", "NOT_FOUND", "")
        d = dict(row)
        goods = _normalise_goods(_parse_line_items(d.get("line_items")))
        return ok_response("ok", {
            "goods": goods,
            "local_id": d.get("id"),
            "seller_name": d.get("seller_name") or "",
            "seller_tin":  d.get("seller_tin") or d.get("seller_inn") or "",
            "full_amount": float(d.get("full_amount") or d.get("total_amount") or 0),
        })
    except Exception as exc:
        log.error("get_goods_by_number error: %s", exc)
        return error_response(str(exc)[:200], "DB_ERROR", str(exc))


class SyncByNumberPayload(BaseModel):
    waybill_number: str


@router.post("/waybills/sync-by-number")
async def sync_waybill_by_number(body: SyncByNumberPayload, request: Request):
    """'Sync' a received waybill by number — finds it in local DB and returns
    its local_id.  If not found, returns an error with import instructions.

    Full RS.ge SOAP integration can be added here when RSGE_LIVE_ACTIONS_ENABLED=true.
    """
    require_permission(request, "documents:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    num = (body.waybill_number or "").strip()
    if not num:
        return error_response("waybill_number is required", "VALIDATION_ERROR", "")
    try:
        async with get_conn() as conn:
            await _ensure_schemas(conn)
            row = await conn.fetchrow(
                "SELECT id, waybill_number FROM waybills WHERE tenant_id=$1 AND waybill_number=$2 LIMIT 1",
                tenant_id, num,
            )
        if row:
            return ok_response("Waybill synced (from local DB)", {
                "local_id": row["id"],
                "waybill_number": row["waybill_number"],
            })
        return error_response(
            f"Waybill #{num} not in local database. "
            "Export it from RS.ge portal as XML and import via RS.ge Documents → Import Waybill.",
            "NOT_FOUND",
            f"waybill_number={num}",
        )
    except Exception as exc:
        log.error("sync_waybill_by_number error: %s", exc)
        return error_response(str(exc)[:200], "DB_ERROR", str(exc))


class SyncSelectedPayload(BaseModel):
    waybill_ids: list


@router.post("/waybills/sync-selected")
async def sync_waybills_selected(body: SyncSelectedPayload, request: Request):
    """Sync a list of waybills by rsge_id / waybill_number."""
    require_permission(request, "documents:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    if not body.waybill_ids:
        return error_response("waybill_ids required", "VALIDATION_ERROR", "")
    try:
        synced = []
        async with get_conn() as conn:
            await _ensure_schemas(conn)
            for wid in body.waybill_ids:
                wid_str = str(wid).strip()
                # Try by waybill_number first, then by rsge_id
                row = await conn.fetchrow(
                    "SELECT id, waybill_number FROM waybills WHERE tenant_id=$1 "
                    "AND (waybill_number=$2 OR rsge_id=$2) LIMIT 1",
                    tenant_id, wid_str,
                )
                if row:
                    synced.append({"local_id": row["id"], "waybill_number": row["waybill_number"]})
        return ok_response(f"Synced {len(synced)} waybill(s) from local DB", {"synced": synced})
    except Exception as exc:
        log.error("sync_waybills_selected error: %s", exc)
        return error_response(str(exc)[:200], "DB_ERROR", str(exc))


@router.get("/waybills/{waybill_id}/goods")
async def get_waybill_goods(waybill_id: int, request: Request):
    """Return goods lines for a locally stored waybill by local DB id."""
    require_permission(request, "documents:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM waybills WHERE id=$1 AND tenant_id=$2",
                waybill_id, tenant_id,
            )
        if not row:
            return error_response("Waybill not found", "NOT_FOUND", "")
        d = dict(row)
        goods = _normalise_goods(_parse_line_items(d.get("line_items")))
        return ok_response("ok", {
            "goods": goods,
            "local_id": d.get("id"),
            "seller_name": d.get("seller_name") or "",
            "seller_tin":  d.get("seller_tin") or d.get("seller_inn") or "",
            "buyer_name":  d.get("buyer_name") or "",
            "full_amount": float(d.get("full_amount") or d.get("total_amount") or 0),
        })
    except Exception as exc:
        log.error("get_waybill_goods error: %s", exc)
        return error_response(str(exc)[:200], "DB_ERROR", str(exc))


@router.get("/waybills/{waybill_id}/linked-invoice")
async def get_linked_invoice(waybill_id: int, request: Request):
    """Find RS.ge tax invoice(s) linked to this waybill by waybill_number."""
    require_permission(request, "documents:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            wb = await conn.fetchrow(
                "SELECT id, waybill_number, total_amount, full_amount FROM waybills "
                "WHERE id=$1 AND tenant_id=$2",
                waybill_id, tenant_id,
            )
            if not wb:
                return error_response("Waybill not found", "NOT_FOUND", "")

            # Find linked tax invoices by waybill_number or waybill_id
            inv_rows = await conn.fetch(
                """
                SELECT id, invoice_number, invoice_series, invoice_date,
                       seller_name, seller_inn, buyer_name, buyer_inn,
                       line_items, subtotal, vat_amount, total_amount, status
                FROM tax_invoices
                WHERE tenant_id=$1
                  AND (related_waybill_number=$2 OR related_waybill_id=$3)
                ORDER BY created_at DESC
                LIMIT 10
                """,
                tenant_id,
                wb["waybill_number"] or "",
                wb["id"],
            )

        waybill_total = float(wb.get("full_amount") or wb.get("total_amount") or 0)
        rsge_invoices = []
        invoice_total = 0.0

        for inv in inv_rows:
            inv_d = dict(inv)
            lines = _normalise_goods(_parse_line_items(inv_d.get("line_items")))
            inv_total = float(inv_d.get("total_amount") or 0)
            invoice_total += inv_total
            rsge_invoices.append({
                "invoice_number": inv_d.get("invoice_number") or "",
                "invoice_series": inv_d.get("invoice_series") or "",
                "doc_date": str(inv_d.get("invoice_date") or ""),
                "seller_name": inv_d.get("seller_name") or "",
                "seller_inn":  inv_d.get("seller_inn") or "",
                "buyer_name":  inv_d.get("buyer_name") or "",
                "total": inv_total,
                "status": inv_d.get("status") or "",
                "lines": lines,
            })

        has_invoice = len(rsge_invoices) > 0
        combined_total = max(waybill_total, invoice_total) if has_invoice else waybill_total

        return ok_response("ok", {
            "rsge_invoices": rsge_invoices,
            "diff_lines": [],
            "summary": {
                "has_invoice": has_invoice,
                "waybill_total": waybill_total,
                "invoice_total": invoice_total,
                "extra_services_total": max(0.0, invoice_total - waybill_total),
                "combined_total": combined_total,
            },
        })
    except Exception as exc:
        log.error("get_linked_invoice error: %s", exc)
        return error_response(str(exc)[:200], "DB_ERROR", str(exc))


class EditMetaPayload(BaseModel):
    begin_date:  Optional[str] = None
    full_amount: Optional[float] = None
    goods_list:  Optional[list] = None


@router.patch("/waybills/{waybill_id}/edit-meta")
async def edit_waybill_meta(waybill_id: int, body: EditMetaPayload, request: Request):
    """Update waybill date, amount and/or goods lines in local DB."""
    require_permission(request, "documents:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            await _ensure_schemas(conn)
            # Verify ownership
            exists = await conn.fetchval(
                "SELECT id FROM waybills WHERE id=$1 AND tenant_id=$2",
                waybill_id, tenant_id,
            )
            if not exists:
                return error_response("Waybill not found", "NOT_FOUND", "")

            updates: list[str] = []
            args: list = []
            idx = 1

            if body.begin_date is not None:
                updates.append(f"begin_date=${idx}::timestamptz")
                args.append(body.begin_date); idx += 1
                updates.append(f"waybill_date=${idx}::date")
                args.append(body.begin_date[:10]); idx += 1

            if body.full_amount is not None:
                updates.append(f"full_amount=${idx}")
                args.append(body.full_amount); idx += 1
                updates.append(f"total_amount=${idx}")
                args.append(body.full_amount); idx += 1

            if body.goods_list is not None:
                updates.append(f"line_items=${idx}::jsonb")
                args.append(json.dumps(body.goods_list)); idx += 1

            if not updates:
                return ok_response("Nothing to update", {})

            updates.append(f"updated_at=NOW()")
            set_clause = ", ".join(updates)
            args.extend([waybill_id, tenant_id])
            await conn.execute(
                f"UPDATE waybills SET {set_clause} WHERE id=${idx} AND tenant_id=${idx+1}",
                *args,
            )

        return ok_response("Waybill updated", {"id": waybill_id})
    except Exception as exc:
        log.error("edit_waybill_meta error: %s", exc)
        return error_response(str(exc)[:200], "DB_ERROR", str(exc))


class CreateWbDraftPayload(BaseModel):
    debit_account:  Optional[str] = "1310"
    credit_account: Optional[str] = "3110"
    description:    Optional[str] = ""
    amount_override: Optional[float] = None
    lines:          Optional[list] = None
    vat_split:      Optional[bool] = False
    vat_rate:       Optional[float] = 18.0
    vat_account:    Optional[str] = "3311"


@router.post("/waybills/{waybill_id}/create-draft")
async def create_waybill_draft(waybill_id: int, body: CreateWbDraftPayload, request: Request):
    """Create a journal draft from a locally synced waybill."""
    require_permission(request, "documents:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            await _ensure_schemas(conn)
            wb = await conn.fetchrow(
                "SELECT * FROM waybills WHERE id=$1 AND tenant_id=$2",
                waybill_id, tenant_id,
            )
            if not wb:
                return error_response("Waybill not found", "NOT_FOUND", "")

            wb_d = dict(wb)

            # Amount: override → goods lines sum → waybill total
            if body.amount_override and body.amount_override > 0:
                amount = body.amount_override
            elif body.lines:
                amount = sum(float(l.get("amt") or l.get("amount") or 0) for l in body.lines)
            else:
                amount = float(wb_d.get("full_amount") or wb_d.get("total_amount") or 0)

            partner = wb_d.get("seller_name") or wb_d.get("buyer_name") or ""
            description = body.description or (
                f"RS.ge ζεδ. #{wb_d.get('waybill_number') or waybill_id} — {partner}"
            )
            wb_date = wb_d.get("begin_date") or wb_d.get("waybill_date")
            draft_date = str(wb_date)[:10] if wb_date else "NOW()"

            dr_account = (body.debit_account or "1310").strip()
            cr_account = (body.credit_account or "3110").strip()

            # Insert draft
            draft_id = await conn.fetchval(
                _q("""
                INSERT INTO journal_drafts
                    (tenant_id, date, description, partner, amount,
                     debit_account, credit_account, account_code,
                     reason, confidence, status, source_type)
                VALUES (%s, %s::date, %s, %s, %s, %s, %s, %s,
                        'rsge_waybill', 0.95, 'pending_approval', 'rsge_waybill')
                RETURNING id
                """),
                tenant_id,
                draft_date if draft_date != "NOW()" else None,
                description,
                partner,
                amount,
                dr_account,
                cr_account,
                dr_account,
            )

            # Link back to waybill row
            await conn.execute(
                "UPDATE waybills SET draft_id=$1, draft_status='drafted' WHERE id=$2 AND tenant_id=$3",
                draft_id, waybill_id, tenant_id,
            )

        log.info("rsge_waybill draft created: draft_id=%s waybill_id=%s tenant=%s",
                 draft_id, waybill_id, tenant_id)
        return ok_response("Draft created", {"draft_id": draft_id})
    except Exception as exc:
        log.error("create_waybill_draft error: %s", exc)
        return error_response(str(exc)[:200], "DB_ERROR", str(exc))


# ══════════════════════════════════════════════════════════════════════════════
# DOCUMENTS (Tax Invoices)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/documents")
async def list_documents(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List RS.ge tax invoices from local DB."""
    require_permission(request, "documents:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            rows = await conn.fetch(_q("""
                SELECT id, invoice_number AS reg_no, invoice_date AS doc_date,
                       seller_name, seller_inn, buyer_name, buyer_inn,
                       total_amount AS amount, status, source,
                       related_waybill_number, created_at
                FROM tax_invoices
                WHERE tenant_id=%s AND source='rsge_import'
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """), tenant_id, limit, offset)

        documents = []
        for r in rows:
            d = dict(r)
            documents.append({
                "rsge_id":      str(d.get("id")),
                "local_id":     d.get("id"),
                "reg_no":       d.get("reg_no") or "",
                "doc_date":     str(d.get("doc_date") or ""),
                "seller_name":  d.get("seller_name") or "",
                "seller_inn":   d.get("seller_inn") or "",
                "buyer_name":   d.get("buyer_name") or "",
                "buyer_inn":    d.get("buyer_inn") or "",
                "amount":       float(d.get("amount") or 0),
                "status":       d.get("status") or "",
                "direction":    "incoming",
                "draft_id":     None,
                "draft_status": None,
            })

        return ok_response("ok", {"documents": documents})
    except Exception as exc:
        log.error("list_documents error: %s", exc)
        return ok_response("ok", {"documents": []})


class DocSyncSelectedPayload(BaseModel):
    rsge_ids: list
    own_inn: Optional[str] = ""


@router.post("/documents/sync-selected")
async def sync_documents_selected(body: DocSyncSelectedPayload, request: Request):
    """Sync selected invoice(s) — looks them up in local DB by id."""
    require_permission(request, "documents:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    synced = []
    try:
        async with get_conn() as conn:
            for rsge_id in body.rsge_ids:
                try:
                    row = await conn.fetchrow(
                        "SELECT id, invoice_number FROM tax_invoices WHERE id=$1 AND tenant_id=$2",
                        int(str(rsge_id).strip()), tenant_id,
                    )
                    if row:
                        synced.append({"local_id": row["id"], "invoice_number": row["invoice_number"]})
                except Exception:
                    pass
        return ok_response(f"Synced {len(synced)} document(s)", {"synced": synced})
    except Exception as exc:
        log.error("sync_documents_selected error: %s", exc)
        return error_response(str(exc)[:200], "DB_ERROR", str(exc))


@router.post("/documents/{doc_id}/create-evidence")
async def create_document_evidence(doc_id: int, request: Request):
    """Stub: mark invoice as evidence-ready (no-op placeholder)."""
    require_permission(request, "documents:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            exists = await conn.fetchval(
                "SELECT id FROM tax_invoices WHERE id=$1 AND tenant_id=$2",
                doc_id, tenant_id,
            )
        if not exists:
            return error_response("Invoice not found", "NOT_FOUND", "")
        return ok_response("Evidence recorded", {"doc_id": doc_id})
    except Exception as exc:
        return error_response(str(exc)[:200], "DB_ERROR", str(exc))


class CreateDocDraftPayload(BaseModel):
    own_inn: Optional[str] = ""
    debit_account:  Optional[str] = "1310"
    credit_account: Optional[str] = "3110"
    description: Optional[str] = ""


@router.post("/documents/{doc_id}/create-draft")
async def create_document_draft(doc_id: int, body: CreateDocDraftPayload, request: Request):
    """Create a journal draft from a locally stored RS.ge tax invoice."""
    require_permission(request, "documents:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            inv = await conn.fetchrow(
                "SELECT * FROM tax_invoices WHERE id=$1 AND tenant_id=$2",
                doc_id, tenant_id,
            )
            if not inv:
                return error_response("Invoice not found", "NOT_FOUND", "")

            inv_d = dict(inv)
            amount = float(inv_d.get("total_amount") or 0)
            partner = inv_d.get("seller_name") or inv_d.get("buyer_name") or ""
            description = body.description or (
                f"RS.ge ფ. #{inv_d.get('invoice_number') or doc_id} — {partner}"
            )
            inv_date = inv_d.get("invoice_date")
            draft_date = str(inv_date)[:10] if inv_date else None

            dr_account = (body.debit_account or "1310").strip()
            cr_account = (body.credit_account or "3110").strip()

            draft_id = await conn.fetchval(
                _q("""
                INSERT INTO journal_drafts
                    (tenant_id, date, description, partner, amount,
                     debit_account, credit_account, account_code,
                     reason, confidence, status, source_type)
                VALUES (%s, %s::date, %s, %s, %s, %s, %s, %s,
                        'rsge_invoice', 0.92, 'pending_approval', 'rsge_invoice')
                RETURNING id
                """),
                tenant_id, draft_date, description, partner, amount,
                dr_account, cr_account, dr_account,
            )

        return ok_response("Draft created", {"draft_id": draft_id})
    except Exception as exc:
        log.error("create_document_draft error: %s", exc)
        return error_response(str(exc)[:200], "DB_ERROR", str(exc))


# ──────────────────────────────────────────────────────────────────────────────
# Live RS.ge SOAP sync
# ──────────────────────────────────────────────────────────────────────────────

class SyncPayload(BaseModel):
    date_from: Optional[str] = None  # ISO date "2024-01-01"
    date_to: Optional[str] = None    # ISO date "2024-01-31"
    mode: str = "v1"                 # "v1" (by update date) | "seller" | "buyer" | "both"


async def _get_service_creds(conn, tenant_id: str):
    """Return (su, sp) for SOAP service user, reading from credential vault."""
    from app.api.services.credential_vault_service import CredentialVaultService
    vault = CredentialVaultService()

    # Try service_password first (dedicated service user)
    try:
        sp = await vault.get_for_connector(
            conn,
            tenant_id=tenant_id,
            provider="rsge",
            credential_type="service_password",
            actor="sync",
            purpose="waybill_sync",
        )
        # service_username is stored in vault metadata, but we also have it in the table
        row = await conn.fetchrow(_q(
            "SELECT service_username, username FROM tenant_rsge_credentials WHERE tenant_id=%s"
        ), tenant_id)
        if row and row["service_username"]:
            return row["service_username"], sp
        if row:
            return row["username"], sp
        return None, None
    except RuntimeError as e:
        if "CREDENTIAL_NOT_FOUND" not in str(e):
            raise
        # Fall back to portal credentials
        pass

    try:
        sp = await vault.get_for_connector(
            conn,
            tenant_id=tenant_id,
            provider="rsge",
            credential_type="portal_password",
            actor="sync",
            purpose="waybill_sync",
        )
        row = await conn.fetchrow(_q(
            "SELECT username FROM tenant_rsge_credentials WHERE tenant_id=%s"
        ), tenant_id)
        if row:
            return row["username"], sp
    except RuntimeError:
        pass

    return None, None


async def _upsert_waybills(conn, tenant_id: str, waybills: list[dict], own_tin: str) -> int:
    """Upsert waybills from RS.ge into local DB. Returns count inserted/updated."""
    count = 0
    for wb in waybills:
        rsge_id = wb.get("rsge_id") or ""
        if not rsge_id:
            continue

        # Determine direction from own_tin
        direction = "unknown"
        if own_tin:
            if wb.get("seller_tin") == own_tin:
                direction = "out"
            elif wb.get("buyer_tin") == own_tin:
                direction = "in"

        # Parse begin_date
        bd_raw = wb.get("begin_date") or wb.get("create_date") or ""
        bd = bd_raw[:10] if bd_raw else None

        goods_json = json.dumps(wb.get("goods_list") or [], ensure_ascii=False)

        await conn.execute(_q("""
            INSERT INTO waybills
                (tenant_id, rsge_id, waybill_number, direction, rsge_status,
                 begin_date, seller_tin, buyer_tin, car_number,
                 start_address, end_address, full_amount, comment,
                 line_items, source, updated_at,
                 seller_name, buyer_name, driver_name, driver_tin)
            VALUES (%s, %s, %s, %s, %s,
                    %s::date, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s::jsonb, 'rsge_soap', NOW(),
                    %s, %s, %s, %s)
            ON CONFLICT (tenant_id, rsge_id) DO UPDATE
            SET waybill_number = EXCLUDED.waybill_number,
                direction      = EXCLUDED.direction,
                rsge_status    = EXCLUDED.rsge_status,
                begin_date     = EXCLUDED.begin_date,
                seller_tin     = EXCLUDED.seller_tin,
                buyer_tin      = EXCLUDED.buyer_tin,
                car_number     = EXCLUDED.car_number,
                start_address  = EXCLUDED.start_address,
                end_address    = EXCLUDED.end_address,
                full_amount    = EXCLUDED.full_amount,
                comment        = EXCLUDED.comment,
                line_items     = EXCLUDED.line_items,
                source         = EXCLUDED.source,
                seller_name    = EXCLUDED.seller_name,
                buyer_name     = EXCLUDED.buyer_name,
                driver_name    = EXCLUDED.driver_name,
                driver_tin     = EXCLUDED.driver_tin,
                updated_at     = NOW()
        """),
            tenant_id, rsge_id, wb.get("waybill_number"), direction,
            wb.get("status"), bd, wb.get("seller_tin"), wb.get("buyer_tin"),
            wb.get("car_number"), wb.get("start_address"), wb.get("end_address"),
            wb.get("full_amount"), wb.get("comment"), goods_json,
            wb.get("seller_name"), wb.get("buyer_name"),
            wb.get("driver_name"), wb.get("driver_tin"),
        )
        count += 1
    return count


@router.post("/sync")
async def sync_waybills_from_rsge(body: SyncPayload, request: Request):
    """Fetch waybills from RS.ge SOAP API and store them in the local DB.

    Requires service user credentials (su/sp) saved via POST /rsge-credentials/save.
    Service users are created in the RS.ge portal under: Settings → Service Users.

    mode=v1   : get_waybills_v1 — both seller+buyer, by last-update date (max 3-day window)
    mode=both : get_waybills (seller) + get_buyer_waybills (buyer) in one call
    mode=seller: get_waybills only
    mode=buyer : get_buyer_waybills only
    """
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    from datetime import datetime, timedelta
    from app.api.services import rsge_waybill_soap as soap

    try:
        # Parse date range
        date_to_dt = datetime.now()
        if body.date_to:
            date_to_dt = datetime.fromisoformat(body.date_to.replace("Z", ""))
            if date_to_dt.hour == 0 and date_to_dt.minute == 0:
                date_to_dt = date_to_dt.replace(hour=23, minute=59, second=59)

        if body.date_from:
            date_from_dt = datetime.fromisoformat(body.date_from.replace("Z", ""))
        else:
            date_from_dt = date_to_dt - timedelta(days=30)

        async with get_conn() as conn:
            await _ensure_schemas(conn)

            su, sp = await _get_service_creds(conn, tenant_id)
            if not su or not sp:
                return error_response(
                    "RS.ge სერვისის მომხმარებელი (su/sp) არ არის შენახული. "
                    "შეინახეთ Settings → RS.ge-ში.",
                    "NO_SERVICE_CREDENTIALS",
                    "Save service_username + service_password via /rsge-credentials/save",
                )

            own_tin = await _get_own_tin(conn, tenant_id)

            # Collect waybills; chunk v1 into 3-day windows
            all_waybills: list[dict] = []
            errors: list[str] = []

            if body.mode == "v1":
                # get_waybills_v1 has a 3-day max window
                cursor = date_from_dt
                while cursor < date_to_dt:
                    window_end = min(cursor + timedelta(days=3), date_to_dt)
                    try:
                        chunk = soap.get_waybills_v1(su, sp, cursor, window_end)
                        all_waybills.extend(chunk)
                    except Exception as e:
                        errors.append(f"{cursor.date()}–{window_end.date()}: {e}")
                        log.warning("rsge sync v1 chunk error: %s", e)
                    cursor = window_end

            elif body.mode in ("seller", "both"):
                try:
                    seller_wbs = soap.get_waybills(su, sp, date_from_dt, date_to_dt)
                    all_waybills.extend(seller_wbs)
                except Exception as e:
                    errors.append(f"seller: {e}")
                    log.warning("rsge sync seller error: %s", e)

            if body.mode in ("buyer", "both"):
                try:
                    buyer_wbs = soap.get_buyer_waybills(su, sp, date_from_dt, date_to_dt)
                    # avoid duplicates by rsge_id
                    seen = {w.get("rsge_id") for w in all_waybills}
                    all_waybills.extend(w for w in buyer_wbs if w.get("rsge_id") not in seen)
                except Exception as e:
                    errors.append(f"buyer: {e}")
                    log.warning("rsge sync buyer error: %s", e)

            # Upsert into waybills table
            count = await _upsert_waybills(conn, tenant_id, all_waybills, own_tin or "")

        return ok_response(
            f"სინქი დასრულდა: {count} ზედნადები შემოვიდა RS.ge-დან",
            {
                "synced": count,
                "fetched": len(all_waybills),
                "date_from": date_from_dt.isoformat(),
                "date_to": date_to_dt.isoformat(),
                "errors": errors,
                "soap_endpoint": soap.WAYBILL_SOAP_URL,
            },
        )

    except Exception as exc:
        log.error("rsge sync error: %s", exc)
        return error_response(str(exc)[:300], "SYNC_ERROR", str(exc))


@router.get("/sync/status")
async def sync_status(request: Request):
    """Return last sync stats and credential readiness for rsge-sync.html."""
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    try:
        async with get_conn() as conn:
            await _ensure_schemas(conn)

            creds_row = await conn.fetchrow(_q(
                "SELECT username, service_username, credential_status "
                "FROM tenant_rsge_credentials WHERE tenant_id=%s"
            ), tenant_id)

            waybill_count = await conn.fetchval(_q(
                "SELECT COUNT(*) FROM waybills WHERE tenant_id=%s AND source='rsge_soap'"
            ), tenant_id) or 0

            latest = await conn.fetchrow(_q(
                "SELECT MAX(updated_at) AS last_sync FROM waybills WHERE tenant_id=%s AND source='rsge_soap'"
            ), tenant_id)

        configured = bool(creds_row and creds_row["credential_status"] == "active")
        has_service_user = bool(creds_row and creds_row.get("service_username"))

        return ok_response("ok", {
            "configured": configured,
            "has_service_user": has_service_user,
            "service_username": creds_row["service_username"] if creds_row else None,
            "portal_username": creds_row["username"] if creds_row else None,
            "synced_waybill_count": int(waybill_count),
            "last_sync": latest["last_sync"].isoformat() if latest and latest["last_sync"] else None,
            "soap_endpoint": "https://services.rs.ge/WayBillService/WayBillService.asmx",
        })
    except Exception as exc:
        log.error("sync_status error: %s", exc)
        return error_response(str(exc)[:200], "DB_ERROR", str(exc))
