from fastapi import APIRouter, Request

from app.api.authz import require_permission
from app.api.services.insights_service import get_dashboard_insights
from app.api.tenant_context import resolve_tenant_id

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/insights")
async def dashboard_insights(request: Request):
    require_permission(request, "dashboard:view")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await get_dashboard_insights(tenant_id)
