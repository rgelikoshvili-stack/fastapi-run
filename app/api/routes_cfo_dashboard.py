"""app/api/routes_cfo_dashboard.py — CFO Financial Dashboard endpoint."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request, Query

from app.api.authz import require_permission
from app.api.response_utils import ok_response, error_response
from app.api.tenant_context import resolve_tenant_id

router = APIRouter(prefix="/reports/cfo-dashboard", tags=["financial-statements"])


@router.get("")
async def cfo_dashboard(
    request: Request,
    as_of:     Optional[str] = Query(None, description="Reporting date YYYY-MM-DD"),
    date_from: Optional[str] = Query(None, description="Period start YYYY-MM-DD"),
    date_to:   Optional[str] = Query(None, description="Period end YYYY-MM-DD"),
):
    """CFO Financial Dashboard — cash position, P&L, VAT, AR/AP, RS.ge, workflow."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    from app.api.services.cfo_dashboard_service import build_cfo_dashboard
    try:
        data = await build_cfo_dashboard(tenant_id, as_of, date_from, date_to)
        return ok_response("CFO dashboard built", data)
    except Exception as e:
        return error_response("CFO dashboard unavailable", "CFO_DASHBOARD_ERROR", str(e))
