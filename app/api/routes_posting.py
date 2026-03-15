from fastapi import APIRouter, Path, Query, HTTPException

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
            detail={"error": "INVALID_PAGINATION", "message": "limit უნდა იყოს 0 ან მეტი"},
        )
    if offset < 0:
        raise HTTPException(
            status_code=422,
            detail={"error": "INVALID_PAGINATION", "message": "offset უნდა იყოს 0 ან მეტი"},
        )


@router.get("/approved-drafts")
def get_approved_drafts(limit: int = 100, offset: int = 0):
    _validate_pagination(limit, offset)
    return get_approved_drafts_service(limit, offset)


@router.get("/payload/{draft_id}")
def get_posting_payload(draft_id: int = Path(..., description="Approved journal draft ID")):
    return get_posting_payload_service(draft_id)


@router.post("/mock/{draft_id}")
def mock_posting(draft_id: int = Path(..., description="Approved journal draft ID")):
    return mock_posting_service(draft_id)


@router.get("/logs")
def get_posting_logs(
    limit: int = 100,
    offset: int = 0,
    target_system: str | None = None,
    draft_id: int | None = None,
):
    _validate_pagination(limit, offset)
    return get_posting_logs_service(limit, offset, target_system, draft_id)


@router.get("/logs/{log_id}")
def get_posting_log_detail(log_id: int = Path(..., description="Posting log ID")):
    return get_posting_log_detail_service(log_id)


@router.get("/balance-status")
def get_balance_status():
    return get_balance_status_service()


@router.post("/balance/{draft_id}")
def post_draft_to_balance(draft_id: int = Path(..., description="Approved journal draft ID")):
    return post_draft_to_balance_service(draft_id)


@router.get("/onec-status")
def get_onec_status():
    return get_onec_status_service()


@router.post("/onec/{draft_id}")
def post_draft_to_onec(draft_id: int = Path(..., description="Approved journal draft ID")):
    return post_draft_to_onec_service(draft_id)


@router.get("/oris-status")
def get_oris_status():
    return get_oris_status_service()


@router.post("/oris/{draft_id}")
def post_draft_to_oris(draft_id: int = Path(..., description="Approved journal draft ID")):
    return post_draft_to_oris_service(draft_id)


@router.post("/apply/{draft_id}")
def apply_posting(
    draft_id: int = Path(..., description="Approved journal draft ID"),
    target: str = Query(
        ...,
        pattern="^(mock|balance|1c|oris)$",
        description="Target system: mock, balance, 1c, oris",
    ),
):
    return apply_posting_service(draft_id, target)