from fastapi import APIRouter, Path, Query, HTTPException, Request

from app.api.tenant_context import resolve_tenant_id
from app.api.authz import require_permission
from app.api.security import limiter

from app.api.services.posting_service import (
    get_approved_drafts_service,
    get_posting_payload_service,
    mock_posting_service,
    get_posting_logs_service,
    get_posting_log_detail_service,
    get_balance_status_service,
    post_draft_to_balance_service,
    get_onec_status_service,
    post_draft_to_onec_service,
    get_oris_status_service,
    post_draft_to_oris_service,
    apply_posting_service,
)
from app.api.services.posting_preview_service import preview_posting_service
from app.api.services.idempotency_service import idempotency_check, idempotency_store

router = APIRouter(prefix="/posting", tags=["posting"])


# ===============================
# VALIDATION
# ===============================
def _validate_pagination(limit: int, offset: int):
    if limit < 0:
        raise HTTPException(status_code=422, detail="invalid limit")
    if offset < 0:
        raise HTTPException(status_code=422, detail="invalid offset")


# ===============================
# READ ENDPOINTS
# ===============================
@router.get("/approved-drafts")
async def get_approved_drafts(
    request: Request,
    limit: int = Query(100),
    offset: int = Query(0),
):
    require_permission(request, "posting:read")

    _validate_pagination(limit, offset)
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    return await get_approved_drafts_service(limit=limit, offset=offset, tenant_id=tenant_id)


@router.get("/payload/{draft_id}")
async def get_posting_payload(
    request: Request,
    draft_id: int = Path(...),
):
    require_permission(request, "posting:read")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await get_posting_payload_service(draft_id=draft_id, tenant_id=tenant_id)


@router.get("/logs")
async def get_posting_logs(
    request: Request,
    limit: int = Query(100),
    offset: int = Query(0),
    target_system: str | None = Query(None),
    draft_id: int | None = Query(None),
):
    require_permission(request, "posting:read")

    _validate_pagination(limit, offset)
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    return await get_posting_logs_service(
        limit=limit,
        offset=offset,
        tenant_id=tenant_id,
        target_system=target_system,
        draft_id=draft_id,
    )


@router.get("/logs/{log_id}")
async def get_posting_log_detail(
    request: Request,
    log_id: int = Path(...),
):
    require_permission(request, "posting:read")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await get_posting_log_detail_service(log_id=log_id, tenant_id=tenant_id)


@router.get("/history")
async def get_posting_history(
    request: Request,
    limit: int = Query(100),
    offset: int = Query(0),
    target_system: str | None = Query(None),
    draft_id: int | None = Query(None),
):
    require_permission(request, "posting:read")

    _validate_pagination(limit, offset)
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    return await get_posting_logs_service(
        limit=limit,
        offset=offset,
        tenant_id=tenant_id,
        target_system=target_system,
        draft_id=draft_id,
    )


# ===============================
# STATUS (READ)
# ===============================
@router.get("/balance-status")
def get_balance_status(request: Request):
    require_permission(request, "posting:read")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return get_balance_status_service(tenant_id=tenant_id)


@router.get("/onec-status")
def get_onec_status(request: Request):
    require_permission(request, "posting:read")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return get_onec_status_service(tenant_id=tenant_id)


@router.get("/oris-status")
def get_oris_status(request: Request):
    require_permission(request, "posting:read")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return get_oris_status_service(tenant_id=tenant_id)


# ===============================
# SHADOW POSTING (read-only preview)
# ===============================
@router.get("/preview/{draft_id}")
def preview_posting(
    request: Request,
    draft_id: int = Path(...),
):
    require_permission(request, "posting:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return preview_posting_service(draft_id=draft_id, tenant_id=tenant_id)


# ===============================
# WRITE ENDPOINTS
# ===============================
@router.post("/mock/{draft_id}")
@limiter.limit("20/minute")
async def mock_posting(
    request: Request,
    draft_id: int = Path(...),
):
    require_permission(request, "posting:write")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await mock_posting_service(draft_id=draft_id, tenant_id=tenant_id)


@router.post("/balance/{draft_id}")
@limiter.limit("20/minute")
async def post_draft_to_balance(
    request: Request,
    draft_id: int = Path(...),
):
    require_permission(request, "posting:write")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await post_draft_to_balance_service(draft_id=draft_id, tenant_id=tenant_id)


@router.post("/onec/{draft_id}")
@limiter.limit("20/minute")
async def post_draft_to_onec(
    request: Request,
    draft_id: int = Path(...),
):
    require_permission(request, "posting:write")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await post_draft_to_onec_service(draft_id=draft_id, tenant_id=tenant_id)


@router.post("/oris/{draft_id}")
@limiter.limit("20/minute")
async def post_draft_to_oris(
    request: Request,
    draft_id: int = Path(...),
):
    require_permission(request, "posting:write")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await post_draft_to_oris_service(draft_id=draft_id, tenant_id=tenant_id)


@router.post("/apply/{draft_id}")
@limiter.limit("20/minute")
async def apply_posting(
    request: Request,
    draft_id: int = Path(...),
    target: str = Query(...),
    force: bool = Query(False),
):
    require_permission(request, "posting:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    idem_key = request.headers.get("X-Idempotent-Key")
    if idem_key:
        hit = idempotency_check(tenant_id, idem_key, f"posting:{draft_id}:{target}")
        if hit is not None:
            return hit
    result = await apply_posting_service(draft_id=draft_id, target=target, tenant_id=tenant_id, force=force)
    if idem_key:
        idempotency_store(tenant_id, idem_key, f"posting:{draft_id}:{target}", result)
    return result