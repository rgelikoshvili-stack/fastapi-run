from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List
import psycopg2, psycopg2.extras

from app.api.db import get_db
from app.api.audit_service import log_event
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/ai-journal", tags=["ai-journal"])

COA = {
    "6100": "გაყიდვების შემოსავალი",
    "6200": "მომსახურების შემოსავალი",
    "7100": "შრომის ანაზღაურება",
    "7200": "ქირა და კომუნალური",
    "7300": "სატრანსპორტო ხარჯი",
    "7400": "სარეკლამო ხარჯი",
    "3310": "მოთხოვნები მომხმარებლებზე",
    "1210": "სალარო",
    "1220": "საბანკო ანგარიში",
    "7110": "იჯარის ხარჯი",
    "7130": "კომუნალური ხარჯი",
    "7150": "ლიცენზიის ხარჯი",
    "7190": "სხვა ხარჯი",
    "7210": "შრომის ანაზღაურება",
}

class JournalRequest(BaseModel):
    partner: Optional[str] = "unknown" = Field(..., min_length=1, description="პარტნიორის სახელი")
    amount: float = Field(..., gt=0, description="თანხა > 0")
    vat: float = Field(default=0, ge=0, description="დღგ >= 0")
    description: str = Field(..., min_length=3, description="ოპერაციის აღწერა")
    names: List[str] = Field(default_factory=list)
    dates: List[str] = Field(default_factory=list)

@router.post("/generate")
async def generate_journal(req: JournalRequest):
    try:
        desc = (req.description or "").lower()

        if any(x in desc for x in ["rent", "იჯარა"]):
            result = {
                "account_code": "7110",
                "account_name": "იჯარის ხარჯი",
                "confidence": 0.92,
                "reason": "rent",
            }
        elif any(x in desc for x in ["salary", "ხელფასი"]):
            result = {
                "account_code": "7210",
                "account_name": "შრომის ანაზღაურება",
                "confidence": 0.95,
                "reason": "salary",
            }
        elif any(x in desc for x in ["utility", "communal", "კომუნალური"]):
            result = {
                "account_code": "7130",
                "account_name": "კომუნალური ხარჯი",
                "confidence": 0.90,
                "reason": "utility",
            }
        elif any(x in desc for x in ["income", "revenue", "payment", "შემოსავალი"]):
            result = {
                "account_code": "6100",
                "account_name": "გაყიდვების შემოსავალი",
                "confidence": 0.88,
                "reason": "income",
            }
        elif any(x in desc for x in ["software", "license", "subscription"]):
            result = {
                "account_code": "7150",
                "account_name": "ლიცენზიის ხარჯი",
                "confidence": 0.91,
                "reason": "software",
            }
        else:
            result = {
                "account_code": "7190",
                "account_name": "სხვა ხარჯი",
                "confidence": 0.50,
                "reason": "default",
            }

        result["amount"] = req.amount
        result["vat"] = req.vat
        result["direction"] = "debit"
        result["currency"] = "GEL"
        result["partner"] = req.partner
        result["description"] = req.description

        log_event("journal_generated", {
            "partner": req.partner,
            "amount": req.amount,
            "description": req.description
        })

        return ok_response("AI journal draft generated", {"draft": result})
    except Exception as e:
        return error_response("AI journal failed", "AI_JOURNAL_ERROR", str(e))

@router.get("/coa")
def get_coa():
    try:
        return ok_response("COA loaded", {"coa": COA})
    except Exception as e:
        return error_response("COA load failed", "COA_ERROR", str(e))

@router.get("/list")
def list_journals():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM journal_entries ORDER BY created_at DESC LIMIT 50")
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return ok_response("Journal list loaded", {"count": len(rows), "journals": rows})
    except Exception as e:
        cur.close()
        conn.close()
        return error_response("Journal list failed", "JOURNAL_LIST_ERROR", str(e))
