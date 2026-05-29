"""app/api/routes_opening_balances.py — Opening Balances API (Task 12A)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, field_validator

from app.api.authz import require_permission
from app.api.response_utils import error_response, ok_response
from app.api.services.opening_balances_service import (
    delete_opening_balance,
    get_opening_balance_totals,
    list_opening_balances,
    upsert_opening_balance,
)
from app.api.tenant_context import resolve_tenant_id

router = APIRouter(prefix="/opening-balances", tags=["opening-balances"])


class OpeningBalanceIn(BaseModel):
    account_code: str
    account_name: str
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    as_of_date: date

    @field_validator("debit", "credit")
    @classmethod
    def non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("debit and credit must be non-negative")
        return v

    @field_validator("account_code")
    @classmethod
    def code_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("account_code must not be blank")
        return v.strip()


@router.get("")
async def list_balances(
    request: Request,
    as_of_date: Optional[date] = Query(None, description="Filter by date, e.g. 2026-01-01"),
):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    rows = await list_opening_balances(tenant_id, as_of_date)
    return ok_response("Opening balances", {"items": rows, "count": len(rows)})


@router.get("/totals")
async def balance_totals(
    request: Request,
    as_of_date: date = Query(..., description="Date to check, e.g. 2026-01-01"),
):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    totals = await get_opening_balance_totals(tenant_id, as_of_date)
    return ok_response("Opening balance totals", totals)


@router.put("/{account_code}")
async def upsert_balance(
    account_code: str,
    payload: OpeningBalanceIn,
    request: Request,
):
    require_permission(request, "posting:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    actor = getattr(request.state, "user_id", "unknown")

    if payload.account_code != account_code:
        return error_response(
            "account_code in URL and body must match",
            "ACCOUNT_CODE_MISMATCH",
            f"url={account_code} body={payload.account_code}",
        )

    row = await upsert_opening_balance(
        tenant_id=tenant_id,
        account_code=account_code,
        account_name=payload.account_name,
        debit=payload.debit,
        credit=payload.credit,
        as_of_date=payload.as_of_date,
        created_by=actor,
    )
    return ok_response("Opening balance saved", row)


@router.delete("/{account_code}")
async def delete_balance(
    account_code: str,
    request: Request,
    as_of_date: date = Query(...),
):
    require_permission(request, "posting:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    deleted = await delete_opening_balance(tenant_id, account_code, as_of_date)
    if not deleted:
        return error_response("Opening balance not found", "NOT_FOUND", f"{account_code} {as_of_date}")
    return ok_response("Opening balance deleted", {"account_code": account_code, "as_of_date": str(as_of_date)})
