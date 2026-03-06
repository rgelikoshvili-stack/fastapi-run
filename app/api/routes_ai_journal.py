from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List
import httpx, os

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
}

class JournalRequest(BaseModel):
    partner: Optional[str] = None
    amount: float
    vat: float
    description: Optional[str] = None
    names: Optional[List[str]] = []
    dates: Optional[List[str]] = []

@router.post("/generate")
async def generate_journal(req: JournalRequest):
    coa_text = "\n".join([f"{k}: {v}" for k, v in COA.items()])
    
    prompt = f"""შენ ხარ საბუღალტრო ექსპერტი. დოკუმენტის მონაცემებით განსაზღვრე სწორი საბუღალტრო ანგარიში.

ანგარიშთა გეგმა (COA):
{coa_text}

დოკუმენტის მონაცემები:
- პარტნიორი: {req.partner or "უცნობი"}
- თანხა: {req.amount} GEL
- დღგ: {req.vat} GEL
- აღწერა: {req.description or "არ არის"}

უპასუხე მხოლოდ JSON ფორმატით:
{{"account_code": "XXXX", "account_name": "სახელი", "confidence": 0.0-1.0, "reason": "მიზეზი"}}"""

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '')}",
                "content-type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",
                "max_tokens": 256,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
    
    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    
    import json, re
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        result = json.loads(match.group())
    else:
        result = {"account_code": "6100", "account_name": "გაყიდვების შემოსავალი", "confidence": 0.5, "reason": "default"}
    
    result["amount"] = req.amount
    result["vat"] = req.vat
    result["direction"] = "debit"
    result["currency"] = "GEL"
    result["partner"] = req.partner
    
    return {"ok": True, "draft": result}

@router.get("/coa")
def get_coa():
    return {"ok": True, "coa": COA}
