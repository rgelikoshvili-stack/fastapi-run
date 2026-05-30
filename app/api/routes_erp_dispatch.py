"""app/api/routes_erp_dispatch.py — Multi-ERP Dispatch Layer (Phase 7)."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, field_validator

from app.api.authz import require_permission
from app.api.response_utils import error_response, ok_response
from app.api.services.erp_dispatch_service import (
    KNOWN_CONNECTORS,
    TRANSACTION_TYPES,
    connector_health_matrix,
    get_dispatch_log_summary,
    get_routing_rules,
    route_transaction,
    set_routing_rule,
)
from app.api.tenant_context import resolve_tenant_id

router = APIRouter(prefix="/erp-dispatch", tags=["erp-dispatch"])


class RoutingRulePayload(BaseModel):
    txn_type: str
    connector: str

    @field_validator("connector")
    @classmethod
    def valid_connector(cls, v: str) -> str:
        if v not in KNOWN_CONNECTORS:
            raise ValueError(f"connector must be one of {KNOWN_CONNECTORS}")
        return v


@router.get("/health")
async def health_matrix(request: Request):
    require_permission(request, "posting:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = connector_health_matrix(tenant_id)
    return ok_response("Connector health matrix", result)


@router.get("/routing")
async def get_routing(request: Request):
    require_permission(request, "posting:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    rules = await get_routing_rules(tenant_id)
    return ok_response("Routing rules", {
        "rules": rules,
        "known_connectors": KNOWN_CONNECTORS,
        "transaction_types": list(TRANSACTION_TYPES.keys()),
    })


@router.put("/routing")
async def update_routing(payload: RoutingRulePayload, request: Request):
    require_permission(request, "posting:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        rules = await set_routing_rule(tenant_id, payload.txn_type, payload.connector)
    except ValueError as exc:
        return error_response(str(exc), str(exc).split(":")[0], payload.txn_type)
    return ok_response("Routing rule updated", {"rules": rules})


@router.get("/route")
async def resolve_route(
    request: Request,
    account_code: str = Query(..., description="Account code to route"),
):
    require_permission(request, "posting:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = await route_transaction(tenant_id, account_code)
    return ok_response("Routing resolved", result)


@router.get("/log")
async def dispatch_log(request: Request, limit: int = Query(10, ge=1, le=100)):
    require_permission(request, "posting:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = await get_dispatch_log_summary(tenant_id, limit=limit)
    return ok_response("Dispatch log summary", result)
