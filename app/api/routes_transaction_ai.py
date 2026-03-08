from fastapi import APIRouter
from app.api.transaction_classifier import classify
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/transaction-ai", tags=["transaction-ai"])

@router.post("/analyze")
def analyze_transaction(data: dict):
    try:
        result = classify(
            description=data.get("description", ""),
            paid_in=data.get("paid_in"),
            paid_out=data.get("paid_out"),
            partner=data.get("partner", "")
        )
        return ok_response("Transaction analyzed", result)
    except Exception as e:
        return error_response("Analysis failed", "TX_AI_ERROR", str(e))
