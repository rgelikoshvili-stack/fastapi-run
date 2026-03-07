from app.api.db import get_db
import psycopg2, psycopg2.extras
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional, List

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
    partner: Optional[str] = None
    amount: float = Field(..., gt=0)
    vat: float = Field(default=0, ge=0)
    description: Optional[str] = None
    names: List[str] = Field(default_factory=list)
    dates: List[str] = Field(default_factory=list)


@router.post("/generate")
async def generate_journal(req: JournalRequest):
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

    return {
        "ok": True,
        "message": "AI journal draft generated",
        "data": {
            "draft": result
        },
        "error": None,
    }


@router.get("/coa")
def get_coa():
    return {
        "ok": True,
        "message": "COA loaded",
        "data": {
            "coa": COA
        },
        "error": None,
    }

@router.get("/list")
def list_journals():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM journal_entries ORDER BY created_at DESC LIMIT 50")
        rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
    except Exception as e:
        conn.rollback()
        rows = []
    cur.close(); conn.close()
    return {"ok": True, "count": len(rows), "journals": rows}
