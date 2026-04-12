from fastapi import APIRouter, Path, Query, HTTPException, Request

from app.api.tenant_context import resolve_tenant_id
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

router = APIRouter(prefix="/posting", tags=["posting"])


def _validate_pagination(limit: int, offset: int):
    if limit < 0:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "INVALID_PAGINATION",
                "message": "limit უნდა იყოს 0 ან მეტი",
            },
        )
    if offset < 0:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "INVALID_PAGINATION",
                "message": "offset უნდა იყოს 0 ან მეტი",
            },
        )


@router.get("/approved-drafts")
def get_approved_drafts(
    request: Request,
    limit: int = Query(100, description="Max rows"),
    offset: int = Query(0, description="Pagination offset"),
):
    _validate_pagination(limit, offset)
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return get_approved_drafts_service(limit=limit, offset=offset, tenant_id=tenant_id)


@router.get("/payload/{draft_id}")
def get_posting_payload(
    request: Request,
    draft_id: int = Path(..., description="Approved journal draft ID"),
):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return get_posting_payload_service(draft_id=draft_id, tenant_id=tenant_id)


@router.post("/mock/{draft_id}")
def mock_posting(
    request: Request,
    draft_id: int = Path(..., description="Approved journal draft ID"),
):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return mock_posting_service(draft_id=draft_id, tenant_id=tenant_id)


@router.get("/logs")
def get_posting_logs(
    request: Request,
    limit: int = Query(100, description="Max rows"),
    offset: int = Query(0, description="Pagination offset"),
    target_system: str | None = Query(None, description="mock | balance | onec | oris"),
    draft_id: int | None = Query(None, description="Filter by draft id"),
):
    _validate_pagination(limit, offset)
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return get_posting_logs_service(
        limit=limit,
        offset=offset,
        tenant_id=tenant_id,
        target_system=target_system,
        draft_id=draft_id,
    )


@router.get("/logs/{log_id}")
def get_posting_log_detail(
    request: Request,
    log_id: int = Path(..., description="Posting log ID"),
):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return get_posting_log_detail_service(log_id=log_id, tenant_id=tenant_id)


@router.get("/balance-status")
def get_balance_status(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return get_balance_status_service(tenant_id=tenant_id)


@router.post("/balance/{draft_id}")
def post_draft_to_balance(
    request: Request,
    draft_id: int = Path(..., description="Approved journal draft ID"),
):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return post_draft_to_balance_service(draft_id=draft_id, tenant_id=tenant_id)


@router.get("/onec-status")
def get_onec_status(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return get_onec_status_service(tenant_id=tenant_id)


@router.post("/onec/{draft_id}")
def post_draft_to_onec(
    request: Request,
    draft_id: int = Path(..., description="Approved journal draft ID"),
):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return post_draft_to_onec_service(draft_id=draft_id, tenant_id=tenant_id)


@router.get("/oris-status")
def get_oris_status(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return get_oris_status_service(tenant_id=tenant_id)


@router.post("/oris/{draft_id}")
def post_draft_to_oris(
    request: Request,
    draft_id: int = Path(..., description="Approved journal draft ID"),
):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return post_draft_to_oris_service(draft_id=draft_id, tenant_id=tenant_id)


@router.post("/apply/{draft_id}")
def apply_posting(
    request: Request,
    draft_id: int = Path(..., description="Approved journal draft ID"),
    target: str = Query(
        ...,
        description="Target system: mock, balance, onec, oris (1c alias accepted in service)",
    ),
):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return apply_posting_service(draft_id=draft_id, target=target, tenant_id=tenant_id)