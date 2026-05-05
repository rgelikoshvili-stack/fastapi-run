from fastapi import APIRouter
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
def list_tenants():
    return list_tenants_service()


@router.post("/create")
def create_tenant(req: CreateTenantRequest):
    return create_tenant_service(req.tenant_id, req.name)