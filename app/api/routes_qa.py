from fastapi import APIRouter
from app.api.services.qa_engine import evaluate_decision
from app.api.authz import require_permission

router = APIRouter(prefix="/qa", tags=["qa"])


@router.post("/evaluate")
def evaluate(payload: dict):
    require_permission(request, "reports:read")
    return {
        "ok": True,
        "message": "QA evaluation complete",
        "data": evaluate_decision(payload),
        "error": None,
    }