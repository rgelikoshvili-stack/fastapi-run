from fastapi import APIRouter
from app.api.services.qa_engine import evaluate_decision

router = APIRouter(prefix="/qa", tags=["qa"])


@router.post("/evaluate")
def evaluate(payload: dict):
    return {
        "ok": True,
        "message": "QA evaluation complete",
        "data": evaluate_decision(payload),
        "error": None,
    }