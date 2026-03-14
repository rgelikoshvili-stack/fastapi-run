from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.api.transaction_classifier import classify
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/transaction-ai", tags=["transaction-ai"])


class TransactionAnalyzeRequest(BaseModel):
    description: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0)
    partner: str = ""

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("description must not be empty")
        return value

    @field_validator("partner")
    @classmethod
    def validate_partner(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else ""


@router.post("/analyze")
def analyze_transaction(data: TransactionAnalyzeRequest):
    try:
        result = classify(
            description=data.description,
            paid_in=data.amount,
            paid_out=None,
            partner=data.partner,
        )
        return ok_response("Transaction analyzed", result)
    except Exception as e:
        return error_response("Analysis failed", "TX_AI_ERROR", str(e))