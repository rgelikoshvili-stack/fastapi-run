"""app/api/routes_financial_statements.py — P&L and Balance Sheet endpoints."""
from fastapi import APIRouter, Request, Query
from typing import Optional
import calendar
from datetime import date

from app.api.tenant_context import resolve_tenant_id
from app.api.authz import require_permission
from app.api.services.financial_statements_service import (
    build_profit_and_loss,
    build_balance_sheet,
)
from app.api.services.gl_reconciliation_service import reconcile_gl_bank

router = APIRouter(prefix="/reports", tags=["financial-statements"])


@router.get("/pnl")
async def profit_and_loss(
    request: Request,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to:   Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """IAS 1 — Statement of Profit or Loss."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await build_profit_and_loss(tenant_id, date_from, date_to)


@router.get("/balance-sheet")
async def balance_sheet(
    request: Request,
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """IAS 1 — Statement of Financial Position."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await build_balance_sheet(tenant_id, as_of)


@router.get("/pl")
async def profit_and_loss_by_month(
    request: Request,
    year:  int = Query(..., description="e.g. 2026"),
    month: int = Query(..., ge=1, le=12, description="1-12"),
):
    """IAS 1 P&L for a single calendar month: ?year=2026&month=4"""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    last_day = calendar.monthrange(year, month)[1]
    date_from = date(year, month, 1).isoformat()
    date_to   = date(year, month, last_day).isoformat()
    return await build_profit_and_loss(tenant_id, date_from, date_to)


@router.get("/gl-reconciliation")
def gl_reconciliation(
    request: Request,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to:   Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """GL ↔ Bank reconciliation — matches journal entries against bank transactions."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return reconcile_gl_bank(tenant_id, date_from, date_to)
