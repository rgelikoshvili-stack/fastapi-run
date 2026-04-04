from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.response_utils import ok_response, error_response
from app.api.transaction_classifier import classify
from app.api.services.approval_service import autopilot_approve_service
from app.api.tenant_context import resolve_tenant_id

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


def _build_explanation(result: dict) -> str:
    source = result.get("source", "")
    confidence = result.get("confidence", 0)
    support_count = result.get("pattern_support_count")
    success_count = result.get("pattern_success_count")
    pattern_value = result.get("pattern_value_used")
    pattern_days = result.get("pattern_days_since_seen")
    similarity = result.get("pattern_similarity")

    if source == "expense_article":
        return f"ხარჯის სტატიის წესი: '{pattern_value}'"

    if source == "partner_memory":
        return f"პარტნიორის მეხსიერება: '{pattern_value}' — ადრე ყოველთვის ეს ანგარიში"

    if source == "transaction_memory":
        return "ტრანზაქციის ისტორია: ადრე იგივე ტრანზაქცია ამ ანგარიშზე გავიდა"

    if source == "erp_history":
        return "ERP ისტორია: Balance.ge-ში ადრე ასე გატარდა"

    if source in ("pattern_active", "pattern_active_fuzzy"):
        parts = [f"ნასწავლი pattern (აქტიური): '{pattern_value}'"]
        if support_count:
            parts.append(f"{support_count}-ჯერ გამოყენებული")
        if success_count and support_count:
            parts.append(f"{success_count}/{support_count} სწორი")
        if pattern_days is not None:
            parts.append(f"ბოლო გამოყენება {pattern_days} დღის წინ")
        if similarity:
            parts.append(f"მსგავსება: {int(similarity * 100)}%")
        return ", ".join(parts)

    if source in ("pattern_candidate", "pattern_candidate_fuzzy"):
        parts = [f"სწავლის პროცესში pattern: '{pattern_value}'"]
        if support_count:
            parts.append(f"{support_count}-ჯერ გამოყენებული")
        return ", ".join(parts)

    if source == "rules":
        return f"საკვანძო სიტყვის წესი (confidence: {int(confidence * 100)}%)"

    return f"კლასიფიკაცია: {source}"


@router.post("/analyze")
def analyze_transaction(data: TransactionAnalyzeRequest, request: Request):
    try:
        tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

        paid_in, paid_out, resolved_amount, resolved_direction = _resolve_amount_and_direction(data)

        result = classify(
            description=data.description,
            paid_in=paid_in,
            paid_out=paid_out,
            partner=data.partner or "",
            operation_code=data.operation_code or "",
            doc_type=data.doc_type or "",
            tenant_id=tenant_id,
        )

        result["input_amount"] = resolved_amount
        result["input_direction"] = resolved_direction
        result["explanation"] = _build_explanation(result)
        result["tenant_id"] = tenant_id

        try:
            autopilot_result = autopilot_approve_service(tenant_id=tenant_id)
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