from typing import Literal
from pydantic import BaseModel, Field, field_validator
from fastapi import APIRouter

from app.api.transaction_classifier import classify
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/transaction-ai", tags=["transaction-ai"])


class AnalyzeTransactionRequest(BaseModel):
    description: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0)
    direction: Literal["in", "out"]
    partner: str = ""

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("description must not be empty")
        return value.strip()

    @field_validator("partner")
    @classmethod
    def normalize_partner(cls, value: str) -> str:
        return (value or "").strip()


@router.post("/analyze")
def analyze_transaction(data: AnalyzeTransactionRequest):
    try:
        paid_in = data.amount if data.direction == "in" else None
        paid_out = data.amount if data.direction == "out" else None

        result = classify(
            description=data.description,
            paid_in=paid_in,
            paid_out=paid_out,
            partner=data.partner,
        )
        return ok_response("Transaction analyzed", result)
    except Exception as e:
        return error_response("Analysis failed", "TX_AI_ERROR", str(e))