"""app/api/routes_fixed_assets.py — Fixed Asset Register + Depreciation Schedule."""
from fastapi import APIRouter, Request, Query, Path
from pydantic import BaseModel
from typing import Optional
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import logging

from app.api.tenant_context import resolve_tenant_id
from app.api.authz import require_permission
from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, error_response, http_error

router = APIRouter(prefix="/fixed-assets", tags=["fixed-assets"])
log = logging.getLogger(__name__)

_METHODS = {"straight_line", "declining_balance"}

_CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS fixed_assets (
        id SERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        name TEXT NOT NULL,
        category TEXT DEFAULT 'equipment',
        acquisition_date DATE NOT NULL,
        cost NUMERIC(15,2) NOT NULL CHECK (cost > 0),
        residual_value NUMERIC(15,2) DEFAULT 0 CHECK (residual_value >= 0),
        useful_life_years INTEGER NOT NULL CHECK (useful_life_years > 0),
        depreciation_method TEXT DEFAULT 'straight_line',
        account_code TEXT DEFAULT '1510',
        accumulated_account TEXT DEFAULT '1520',
        expense_account TEXT DEFAULT '7610',
        notes TEXT,
        status TEXT DEFAULT 'active',
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
"""

_CREATE_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_fixed_assets_tenant
        ON fixed_assets(tenant_id, status)
"""


class AssetCreate(BaseModel):
    name: str
    category: str = "equipment"          # equipment | vehicle | building | intangible
    acquisition_date: str                 # YYYY-MM-DD
    cost: float
    residual_value: float = 0.0
    useful_life_years: int = 5
    depreciation_method: str = "straight_line"
    account_code: str = "1510"           # Dr account (asset)
    accumulated_account: str = "1520"    # Cr account (accumulated dep.)
    expense_account: str = "7610"        # Dr account (dep. expense)
    notes: Optional[str] = None


def _depreciation_schedule(asset: dict) -> list[dict]:
    """Compute annual depreciation schedule for the asset."""
    cost = Decimal(str(asset["cost"]))
    residual = Decimal(str(asset["residual_value"]))
    life = int(asset["useful_life_years"])
    method = asset["depreciation_method"]
    start = date.fromisoformat(str(asset["acquisition_date"])[:10])

    depreciable = cost - residual
    schedule = []
    book_value = cost

    for yr in range(1, life + 1):
        period_date = date(start.year + yr, start.month, start.day)
        if method == "straight_line":
            dep = (depreciable / life).quantize(Decimal("0.01"), ROUND_HALF_UP)
        else:  # declining_balance
            rate = Decimal("2") / Decimal(str(life))
            dep = (book_value * rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
            dep = min(dep, book_value - residual)

        if dep <= 0:
            break
        book_value = (book_value - dep).quantize(Decimal("0.01"), ROUND_HALF_UP)
        schedule.append({
            "year": yr,
            "period_date": period_date.isoformat(),
            "depreciation": float(dep),
            "accumulated": float(cost - book_value - residual),
            "book_value": float(book_value),
        })

    return schedule


@router.post("/")
async def create_asset(body: AssetCreate, request: Request):
    require_permission(request, "assets:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    if body.depreciation_method not in _METHODS:
        return error_response(f"method must be one of {_METHODS}", "VALIDATION_ERROR")
    try:
        async with get_conn() as conn:
            await conn.execute(_CREATE_TABLE)
            await conn.execute(_CREATE_INDEX)
            asset_id = await conn.fetchval(_q("""
                INSERT INTO fixed_assets
                    (tenant_id, name, category, acquisition_date, cost, residual_value,
                     useful_life_years, depreciation_method, account_code,
                     accumulated_account, expense_account, notes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """), tenant_id, body.name, body.category, body.acquisition_date,
                body.cost, body.residual_value, body.useful_life_years,
                body.depreciation_method, body.account_code,
                body.accumulated_account, body.expense_account, body.notes)
    except Exception as e:
        return error_response("Asset create failed", "DB_ERROR", str(e))
    return ok_response("Asset created", {"id": asset_id})


@router.get("/")
async def list_assets(request: Request, status: str = Query("active")):
    require_permission(request, "assets:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        await conn.execute(_CREATE_TABLE)
        await conn.execute(_CREATE_INDEX)
        rows = [dict(r) for r in await conn.fetch(_q("""
            SELECT id, name, category, acquisition_date, cost, residual_value,
                   useful_life_years, depreciation_method, account_code,
                   accumulated_account, expense_account, notes, status, created_at
            FROM fixed_assets
            WHERE tenant_id = %s AND status = %s
            ORDER BY acquisition_date DESC
        """), tenant_id, status)]

    for r in rows:
        if r.get("acquisition_date"):
            r["acquisition_date"] = str(r["acquisition_date"])[:10]
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()
    return ok_response("Assets fetched", rows)


@router.get("/{asset_id}/schedule")
async def depreciation_schedule(asset_id: int = Path(...), request: Request = None):
    require_permission(request, "assets:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        await conn.execute(_CREATE_TABLE)
        row = await conn.fetchrow(_q("""
            SELECT id, name, cost, residual_value, useful_life_years,
                   depreciation_method, acquisition_date, expense_account, accumulated_account
            FROM fixed_assets WHERE id = %s AND tenant_id = %s
        """), asset_id, tenant_id)

    if not row:
        return http_error(404, "Asset not found", "NOT_FOUND")

    asset = dict(row)
    asset["acquisition_date"] = str(asset["acquisition_date"])[:10]
    schedule = _depreciation_schedule(asset)
    total_dep = round(sum(s["depreciation"] for s in schedule), 2)

    return ok_response("Depreciation schedule", {
        "asset": asset,
        "schedule": schedule,
        "total_depreciation": total_dep,
        "journal_template": {
            "debit":  f"{asset['expense_account']} ამორტიზაციის ხარჯი",
            "credit": f"{asset['accumulated_account']} დარიცხული ამორტიზაცია",
        },
    })


@router.put("/{asset_id}")
async def update_asset(asset_id: int, body: AssetCreate, request: Request):
    require_permission(request, "assets:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    if body.depreciation_method not in _METHODS:
        return error_response(f"method must be one of {_METHODS}", "VALIDATION_ERROR")
    try:
        async with get_conn() as conn:
            await conn.execute(_CREATE_TABLE)
            row = await conn.fetchrow(_q("""
                UPDATE fixed_assets SET
                    name=%s, category=%s, acquisition_date=%s, cost=%s,
                    residual_value=%s, useful_life_years=%s, depreciation_method=%s,
                    account_code=%s, accumulated_account=%s, expense_account=%s, notes=%s
                WHERE id=%s AND tenant_id=%s
                RETURNING id
            """), body.name, body.category, body.acquisition_date, body.cost,
                body.residual_value, body.useful_life_years, body.depreciation_method,
                body.account_code, body.accumulated_account, body.expense_account,
                body.notes, asset_id, tenant_id)
    except Exception as e:
        return error_response("Asset update failed", "DB_ERROR", str(e))
    if not row:
        return http_error(404, "Asset not found", "NOT_FOUND")
    return ok_response("Asset updated", {"id": asset_id})


@router.delete("/{asset_id}")
async def retire_asset(asset_id: int, request: Request):
    require_permission(request, "assets:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        row = await conn.fetchrow(_q(
            "UPDATE fixed_assets SET status='retired' WHERE id=%s AND tenant_id=%s RETURNING id"
        ), asset_id, tenant_id)
    if not row:
        return http_error(404, "Asset not found", "NOT_FOUND")
    return ok_response("Asset retired", {"id": asset_id})
