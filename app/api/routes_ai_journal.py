from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from typing import Optional, List

from app.api.db import get_conn, _q
from app.api.audit_service import log_event
from app.api.response_utils import ok_response, error_response
from app.api.authz import require_permission

router = APIRouter(prefix="/ai-journal", tags=["ai-journal"])

# COA aligned to chart_of_accounts.py
COA = {
    "6110": "გ-ვ. შემოსავალი",
    "6120": "მომსახ. შემოსავალი",
    "7110": "COGS",
    "7210": "ხელფასი",
    "7220": "დამს. საპ. ხ.",
    "7310": "ქირა",
    "7410": "კომუნალური",
    "7510": "საბ. საკომ.",
    "7610": "ამორტ.",
    "7710": "მარკეტინგი",
    "7720": "წარმ. ხ.",
    "7730": "ტრანსპ.",
    "7810": "Software/Cloud",
    "7910": "სხვა ხარჯი",
    "1110": "სალარო",
    "1120": "საბანკო ანგ.",
    "1210": "AR / მოთხ. კლ.",
    "3110": "AP / კრ. დავ.",
    "3310": "VAT output",
    "3311": "VAT input",
    "3320": "PIT / საშ.",
    "3330": "PAYG / საპ.",
    "3340": "CIT / მოგ.",
    "4210": "გ.მ. (RE)",
}


class JournalRequest(BaseModel):
    partner: Optional[str] = "unknown"
    amount: float = Field(..., gt=0, description="თანხა > 0")
    vat: float = Field(default=0, ge=0, description="დღგ >= 0")
    description: str = Field(..., min_length=3, description="ოპერაციის აღწერა")
    names: List[str] = Field(default_factory=list)
    dates: List[str] = Field(default_factory=list)


@router.post("/generate")
async def generate_journal(req: JournalRequest, request: Request):
    require_permission(request, "approval:write")
    try:
        desc = (req.description or "").lower()

        if any(x in desc for x in ["rent", "იჯარა", "ქირა"]):
            result = {"account_code": "7310", "account_name": "ქირა", "confidence": 0.92, "reason": "rent"}
        elif any(x in desc for x in ["salary", "ხელფასი", "payroll"]):
            result = {"account_code": "7210", "account_name": "ხელფასი", "confidence": 0.95, "reason": "salary"}
        elif any(x in desc for x in ["utility", "communal", "კომუნალ", "electricity", "water"]):
            result = {"account_code": "7410", "account_name": "კომუნალური", "confidence": 0.90, "reason": "utility"}
        elif any(x in desc for x in ["income", "revenue", "payment", "შემოსავალი"]):
            result = {"account_code": "6110", "account_name": "გ-ვ. შემოსავალი", "confidence": 0.88, "reason": "income"}
        elif any(x in desc for x in ["software", "license", "subscription", "hosting"]):
            result = {"account_code": "7810", "account_name": "Software/Cloud", "confidence": 0.91, "reason": "software"}
        elif any(x in desc for x in ["transport", "taxi", "courier", "delivery"]):
            result = {"account_code": "7730", "account_name": "ტრანსპ.", "confidence": 0.88, "reason": "transport"}
        elif any(x in desc for x in ["marketing", "advertising", "ads", "facebook"]):
            result = {"account_code": "7710", "account_name": "მარკეტინგი", "confidence": 0.88, "reason": "marketing"}
        elif any(x in desc for x in ["commission", "bank fee", "საკომ"]):
            result = {"account_code": "7510", "account_name": "საბ. საკომ.", "confidence": 0.90, "reason": "bank_fee"}
        else:
            result = {"account_code": "7910", "account_name": "სხვა ხარჯი", "confidence": 0.50, "reason": "default"}

        result["amount"] = req.amount
        result["vat"] = req.vat
        result["direction"] = "debit"
        result["currency"] = "GEL"
        result["partner"] = req.partner
        result["description"] = req.description

        log_event("journal_generated", {"partner": req.partner, "amount": req.amount, "description": req.description})
        return ok_response("AI journal draft generated", {"draft": result})
    except Exception as e:
        return error_response("AI journal failed", "AI_JOURNAL_ERROR", str(e))


@router.get("/coa")
def get_coa(request: Request):
    require_permission(request, "approval:write")
    try:
        return ok_response("COA loaded", {"coa": COA})
    except Exception as e:
        return error_response("COA load failed", "COA_ERROR", str(e))


@router.get("/list")
async def list_journals(request: Request):
    require_permission(request, "approval:write")
    try:
        async with get_conn() as conn:
            rows = [dict(r) for r in await conn.fetch(
                "SELECT * FROM journal_entries ORDER BY created_at DESC LIMIT 50"
            )]
        return ok_response("Journal list loaded", {"count": len(rows), "journals": rows})
    except Exception as e:
        return error_response("Journal list failed", "JOURNAL_LIST_ERROR", str(e))
