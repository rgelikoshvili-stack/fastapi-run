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
    build_cashflow_statement,
)
from app.api.services.gl_reconciliation_service import reconcile_gl_bank

router = APIRouter(prefix="/reports", tags=["financial-statements"])
financial_statements_alias_router = APIRouter(
    prefix="/financial-statements",
    tags=["financial-statements"],
)


async def _profit_and_loss_response(
    request: Request,
    date_from: Optional[str],
    date_to: Optional[str],
    compare_from: Optional[str],
    compare_to: Optional[str],
):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = await build_profit_and_loss(tenant_id, date_from, date_to)
    if result.get("ok") and (compare_from or compare_to):
        comparison = await build_profit_and_loss(tenant_id, compare_from, compare_to)
        if comparison.get("ok"):
            current_data = result.get("data") or {}
            comparison_data = comparison.get("data") or {}
            current_data["comparison"] = {
                "period": comparison_data.get("period"),
                "total_revenue": comparison_data.get("revenue", {}).get("total", 0.0),
                "gross_profit": comparison_data.get("gross_profit", 0.0),
                "ebit": comparison_data.get("ebit", 0.0),
                "variance": {
                    "total_revenue": round(
                        float(current_data.get("revenue", {}).get("total", 0.0))
                        - float(comparison_data.get("revenue", {}).get("total", 0.0)),
                        2,
                    ),
                    "gross_profit": round(
                        float(current_data.get("gross_profit", 0.0))
                        - float(comparison_data.get("gross_profit", 0.0)),
                        2,
                    ),
                    "ebit": round(
                        float(current_data.get("ebit", 0.0))
                        - float(comparison_data.get("ebit", 0.0)),
                        2,
                    ),
                },
            }
    return result


async def _balance_sheet_response(request: Request, as_of: Optional[str]):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await build_balance_sheet(tenant_id, as_of)


@router.get("/pnl")
async def profit_and_loss(
    request: Request,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to:   Optional[str] = Query(None, description="YYYY-MM-DD"),
    compare_from: Optional[str] = Query(None, description="YYYY-MM-DD comparison period start"),
    compare_to: Optional[str] = Query(None, description="YYYY-MM-DD comparison period end"),
):
    """IAS 1 — Statement of Profit or Loss."""
    return await _profit_and_loss_response(request, date_from, date_to, compare_from, compare_to)


@router.get("/balance-sheet")
async def balance_sheet(
    request: Request,
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """IAS 1 — Statement of Financial Position."""
    return await _balance_sheet_response(request, as_of)


@financial_statements_alias_router.get("/pnl")
async def profit_and_loss_alias(
    request: Request,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    compare_from: Optional[str] = Query(None, description="YYYY-MM-DD comparison period start"),
    compare_to: Optional[str] = Query(None, description="YYYY-MM-DD comparison period end"),
):
    return await _profit_and_loss_response(request, date_from, date_to, compare_from, compare_to)


@financial_statements_alias_router.get("/balance-sheet")
async def balance_sheet_alias(
    request: Request,
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    return await _balance_sheet_response(request, as_of)


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


@router.get("/cashflow")
async def cashflow_statement(
    request: Request,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to:   Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """IAS 7 — Statement of Cash Flows (direct method, operating/investing/financing)."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await build_cashflow_statement(tenant_id, date_from, date_to)


@financial_statements_alias_router.get("/cashflow")
async def cashflow_statement_alias(
    request: Request,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to:   Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """IAS 7 — Statement of Cash Flows (alias path)."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await build_cashflow_statement(tenant_id, date_from, date_to)


@router.get("/gl-reconciliation")
async def gl_reconciliation(
    request: Request,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to:   Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """GL ↔ Bank reconciliation — matches journal entries against bank transactions."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await reconcile_gl_bank(tenant_id, date_from, date_to)
