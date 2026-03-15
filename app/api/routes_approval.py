from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.api.services.approval_service import (
    get_queue_service,
    approve_draft_service,
    reject_draft_service,
    get_audit_service,
)

router = APIRouter(prefix="/approval", tags=["approval"])


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


class RejectRequest(BaseModel):
    reason: Optional[str] = ""


# --- QUEUE ---


@router.get("/queue")
def get_queue(status: str = "", limit: int = 100, offset: int = 0):
    _validate_pagination(limit, offset)
    return get_queue_service(status, limit, offset)


# --- APPROVE ---


@router.post("/approve/{draft_id}")
def approve_draft(draft_id: int):
    return approve_draft_service(draft_id)


# --- REJECT ---


@router.post("/reject/{draft_id}")
def reject_draft(draft_id: int, req: RejectRequest):
    return reject_draft_service(draft_id, req.reason)


# --- AUDIT ---


@router.get("/audit")
def get_audit_log(limit: int = 50, offset: int = 0):
    _validate_pagination(limit, offset)
    return get_audit_service(limit, offset)