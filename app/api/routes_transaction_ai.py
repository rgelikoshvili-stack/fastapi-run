from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.response_utils import ok_response, error_response
from app.api.transaction_classifier import classify
from app.api.services.approval_service import autopilot_approve_service

router = APIRouter(prefix="/transaction-ai", tags=["transaction-ai"])


class TransactionAnalyzeRequest(BaseModel):
    description: str
    partner: Optional[str] = ""
    amount: Optional[float] = None
    direction: Optional[str] = None
    paid_in: Optional[float] = None
    paid_out: Optional[float] = None
    operation_code: Optional[str] = ""
    doc_type: Optional[str] = ""


def _resolve_amount_and_direction(data: TransactionAnalyzeRequest):
    paid_in = data.paid_in
    paid_out = data.paid_out
    amount = data.amount
    direction = (data.direction or "").strip().lower()

    if paid_in not in (None, 0, 0.0):
        return float(paid_in), None, float(paid_in), "in"

    if paid_out not in (None, 0, 0.0):
        return None, float(paid_out), float(paid_out), "out"

    if amount is None:
        raise ValueError("amount or paid_in/paid_out is required")

    amount = float(amount)

    if direction not in ("in", "out"):
        raise ValueError("direction must be 'in' or 'out' when amount is used")

    if direction == "in":
        return amount, None, amount, "in"

    return None, amount, amount, "out"


@router.post("/analyze")
def analyze_transaction(data: TransactionAnalyzeRequest):
    try:
        paid_in, paid_out, resolved_amount, resolved_direction = _resolve_amount_and_direction(data)

        result = classify(
            description=data.description,
            paid_in=paid_in,
            paid_out=paid_out,
            partner=data.partner or "",
            operation_code=data.operation_code or "",
            doc_type=data.doc_type or "",
        )

        result["input_amount"] = resolved_amount
        result["input_direction"] = resolved_direction

        try:
            autopilot_result = autopilot_approve_service()
            result["autopilot_run"] = True
            result["autopilot_result"] = autopilot_result.get("data", {})
        except Exception as autopilot_error:
            result["autopilot_run"] = False
            result["autopilot_error"] = str(autopilot_error)

        return ok_response("Transaction analyzed", result)

    except ValueError as e:
        return error_response("Validation failed", "VALIDATION_ERROR", str(e))
    except Exception as e:
        return error_response("Transaction analyze failed", "TRANSACTION_ANALYZE_ERROR", str(e))