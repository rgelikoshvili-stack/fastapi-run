from fastapi import APIRouter, Request
from pydantic import BaseModel
from app.api.authz import require_permission

from app.api.services.tenant_service import (
    list_tenants_service,
    create_tenant_service,
)

router = APIRouter(prefix="/tenants", tags=["tenants"])


class CreateTenantRequest(BaseModel):
    tenant_id: str
    name: str


@router.get("")
async def list_tenants(request: Request):
    require_permission(request, "tenant:admin")
    return await list_tenants_service()


@router.post("/create")
async def create_tenant(req: CreateTenantRequest, request: Request):
    require_permission(request, "tenant:admin")
    return await create_tenant_service(req.tenant_id, req.name)
