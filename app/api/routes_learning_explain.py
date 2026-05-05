from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services.pattern_explain_service import explain_pattern
from app.api.authz import require_permission

router = APIRouter(prefix="/learning", tags=["learning"])


@router.get("/pattern/{pattern_id}")
def get_pattern_explain(pattern_id: int):
    require_permission(request, "patterns:view")
    result = explain_pattern(pattern_id=pattern_id)

    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result["message"])

    return result