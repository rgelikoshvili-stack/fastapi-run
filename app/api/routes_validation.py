from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

router = APIRouter(prefix="/validation", tags=["validation"])

class JournalEntry(BaseModel):
    account_code: str
    amount: float
    direction: str  # "debit" or "credit"
    vat: Optional[float] = 0.0
    currency: Optional[str] = "GEL"
    partner: Optional[str] = None

class ValidationRequest(BaseModel):
    entries: List[JournalEntry]
    doc_type: Optional[str] = None

@router.post("/check")
def validate_journal(req: ValidationRequest):
    errors = []
    warnings = []

    # 1) Debit/Credit balance
    total_debit = sum(e.amount for e in req.entries if e.direction == "debit")
    total_credit = sum(e.amount for e in req.entries if e.direction == "credit")
    if round(total_debit, 2) != round(total_credit, 2):
        errors.append(f"Debit/Credit imbalance: debit={total_debit}, credit={total_credit}")

    # 2) VAT consistency (18%)
    for e in req.entries:
        if e.vat and e.vat > 0:
            expected_vat = round(e.amount * 18 / 118, 2)
            if abs(e.vat - expected_vat) > 0.05:
                warnings.append(f"VAT mismatch on {e.account_code}: got {e.vat}, expected {expected_vat}")

    # 3) Account code format
    for e in req.entries:
        if not e.account_code.isdigit():
            errors.append(f"Invalid account code: {e.account_code}")

    # 4) Direction check
    for e in req.entries:
        if e.direction not in ("debit", "credit"):
            errors.append(f"Invalid direction: {e.direction}")

    # 5) Amount check
    for e in req.entries:
        if e.amount <= 0:
            errors.append(f"Invalid amount: {e.amount} on {e.account_code}")

    passed = len(errors) == 0
    return {
        "ok": True,
        "passed": passed,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "total_debit": total_debit,
            "total_credit": total_credit,
            "entry_count": len(req.entries)
        }
    }

@router.get("/health")
def health():
    return {"ok": True, "service": "validation"}