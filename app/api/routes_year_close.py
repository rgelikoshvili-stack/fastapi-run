"""app/api/routes_year_close.py — Fiscal Year-End Close."""
from __future__ import annotations

import re

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, field_validator

from app.api.authz import require_permission
from app.api.response_utils import error_response, ok_response
from app.api.services.year_close_service import (
    generate_closing_entries,
    get_year_close_status,
    lock_fiscal_year,
    run_year_checklist,
    save_year_close_signoff,
)
from app.api.tenant_context import resolve_tenant_id

router = APIRouter(prefix="/year-close", tags=["year-close"])

_YEAR_RE = re.compile(r"^\d{4}$")


class YearSignoffPayload(BaseModel):
    year: str
    role: str
    notes: str | None = None

    @field_validator("year")
    @classmethod
    def valid_year(cls, v: str) -> str:
        if not re.match(r"^\d{4}$", v):
            raise ValueError("year must be YYYY format")
        return v

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str) -> str:
        if v not in ("accountant", "cfo", "board"):
            raise ValueError("role must be accountant, cfo, or board")
        return v


class YearLockPayload(BaseModel):
    year: str

    @field_validator("year")
    @classmethod
    def valid_year(cls, v: str) -> str:
        if not re.match(r"^\d{4}$", v):
            raise ValueError("year must be YYYY format")
        return v


@router.get("/status")
async def year_close_status(
    request: Request,
    year: str = Query(..., description="Fiscal year (YYYY)"),
):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    if not _YEAR_RE.match(year):
        return error_response("year must be YYYY format", "INVALID_YEAR", year)
    result = await get_year_close_status(tenant_id, year)
    return ok_response(f"Year-end close status for {year}", result)


@router.get("/checklist")
async def year_close_checklist(
    request: Request,
    year: str = Query(..., description="Fiscal year (YYYY)"),
):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    if not _YEAR_RE.match(year):
        return error_response("year must be YYYY format", "INVALID_YEAR", year)
    items = await run_year_checklist(tenant_id, year)
    all_ok = all(i["status"] in ("ok", "warning") for i in items)
    critical_ok = all(
        i["status"] == "ok"
        for i in items
        if i["id"] in ("no_unposted_drafts", "trial_balance_balanced")
    )
    return ok_response(
        f"Year-end checklist for {year}",
        {"year": year, "items": items, "all_ok": all_ok, "critical_ok": critical_ok},
    )


@router.get("/closing-entries")
async def closing_entries_preview(
    request: Request,
    year: str = Query(..., description="Fiscal year (YYYY)"),
):
    """Preview the year-end closing journal entry (does not create it)."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    if not _YEAR_RE.match(year):
        return error_response("year must be YYYY format", "INVALID_YEAR", year)
    result = await generate_closing_entries(tenant_id, year)
    if not result.get("ok"):
        return error_response(result.get("error", "Failed to compute closing entries"), "COMPUTE_ERROR", year)
    return ok_response(f"Closing entries preview for {year}", result)


@router.post("/signoff")
async def year_close_signoff(payload: YearSignoffPayload, request: Request):
    require_permission(request, "posting:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    actor = getattr(request.state, "user_id", "unknown")
    try:
        result = await save_year_close_signoff(
            tenant_id,
            payload.year,
            payload.role,
            signed_by=actor,
            notes=payload.notes,
        )
    except ValueError as exc:
        return error_response(str(exc), "INVALID_ROLE", payload.year)
    return ok_response("Year-end sign-off recorded", result)


@router.post("/lock")
async def year_close_lock(payload: YearLockPayload, request: Request):
    """Lock the fiscal year to prevent any further postings."""
    require_permission(request, "posting:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    actor = getattr(request.state, "user_id", "unknown")
    result = await lock_fiscal_year(tenant_id, payload.year, locked_by=actor)
    if not result.get("ok"):
        return error_response(result.get("error", "Lock failed"), "LOCK_FAILED", payload.year)
    return ok_response(result.get("message", f"Fiscal year {payload.year} locked"), result)
