from fastapi import APIRouter, Path, Request, HTTPException

from app.api.authz import require_permission
from app.api.tenant_context import resolve_tenant_id
from app.api.services.system_service import (
    get_system_summary_service,
    get_system_overview_service,
    get_bank_files_history_service,
    get_bank_file_detail_service,
    get_bank_file_drafts_service,
)

router = APIRouter(prefix="/system", tags=["system"])


def _validate_pagination(limit: int, offset: int):
    if limit < 0:
        raise HTTPException(
            status_code=422,
            detail={"error": "INVALID_PAGINATION", "message": "limit უნდა იყოს 0 ან მეტი"},
        )
    if offset < 0:
        raise HTTPException(
            status_code=422,
            detail={"error": "INVALID_PAGINATION", "message": "offset უნდა იყოს 0 ან მეტი"},
        )


@router.get("/summary")
async def get_system_summary(request: Request):
    require_permission(request, "dashboard:admin")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await get_system_summary_service(tenant_id)


@router.get("/overview")
async def get_system_overview(request: Request):
    require_permission(request, "dashboard:admin")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await get_system_overview_service(tenant_id)


@router.get("/bank-files")
async def get_bank_files_history(request: Request, limit: int = 50, offset: int = 0):
    require_permission(request, "dashboard:admin")
    _validate_pagination(limit, offset)
    return await get_bank_files_history_service(limit, offset)


@router.get("/bank-files/{file_id}")
async def get_bank_file_detail(request: Request, file_id: int = Path(..., description="Processed bank file ID")):
    require_permission(request, "dashboard:admin")
    return await get_bank_file_detail_service(file_id)


@router.get("/bank-files/{file_id}/drafts")
async def get_bank_file_drafts(
    request: Request,
    file_id: int = Path(..., description="Processed bank file ID"),
    limit: int = 100,
    offset: int = 0,
):
    require_permission(request, "dashboard:admin")
    _validate_pagination(limit, offset)
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await get_bank_file_drafts_service(file_id, limit, offset, tenant_id)
