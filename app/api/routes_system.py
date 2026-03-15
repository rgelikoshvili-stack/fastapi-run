from fastapi import APIRouter, Path, HTTPException

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
def get_system_summary():
    return get_system_summary_service()


@router.get("/overview")
def get_system_overview():
    return get_system_overview_service()


@router.get("/bank-files")
def get_bank_files_history(limit: int = 50, offset: int = 0):
    _validate_pagination(limit, offset)
    return get_bank_files_history_service(limit, offset)


@router.get("/bank-files/{file_id}")
def get_bank_file_detail(file_id: int = Path(..., description="Processed bank file ID")):
    return get_bank_file_detail_service(file_id)


@router.get("/bank-files/{file_id}/drafts")
def get_bank_file_drafts(
    file_id: int = Path(..., description="Processed bank file ID"),
    limit: int = 100,
    offset: int = 0,
):
    _validate_pagination(limit, offset)
    return get_bank_file_drafts_service(file_id, limit, offset)