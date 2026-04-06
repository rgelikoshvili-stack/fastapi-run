"""
Bridge Hub — AI Chat Route (OpenRouter)
→ app/api/routes_ai_chat.py
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import os
import re

try:
    from bridge_hub_knowledge import (
        calculate_vat, calculate_payroll, classify_transaction,
        search_knowledge, get_context_for_llm, get_stats,
    )
    KB_LOADED = True
except ImportError:
    KB_LOADED = False

try:
    from openai import OpenAI
    _client = OpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1"
    )
    LLM_AVAILABLE = bool(os.getenv("OPENROUTER_API_KEY"))
except Exception:
    _client = None
    LLM_AVAILABLE = False

router = APIRouter(prefix="/api/ai", tags=["AI Chat"])

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    answer: str
    sources: list = []
    confidence: float = 0.0
    session_id: Optional[str] = None

class VATRequest(BaseModel):
    amount: float
    inclusive: bool = True

class PayrollRequest(BaseModel):
    gross: float

class ClassifyRequest(BaseModel):
    description: str

SYSTEM_PROMPT = """შენ ხარ Bridge Hub-ის AI ბუღალტერი.
საქართველოს გადასახადები: VAT 18%, PIT 20%, PAYG 2%, CIT 15%.
ყოველთვის ქართულად პასუხობ. გატარებებს (Dr/Cr) მიუთითებ."""

def _local_answer(message: str) -> Optional[str]:
    msg = message.lower()
    
    vat_match = re.search(r'(\d+[\.,]?\d*)\s*(?:ლარი|₾|lari)', msg)
    if vat_match and any(w in msg for w in ["vat", "დღგ", "ამოიღე", "გამოყავი"]):
        amount = float(vat_match.group(1).replace(",", "."))
        inclusive = any(w in msg for w in ["ჩათვლილი", "ჩათვლით"])
        r = calculate_vat(amount, inclusive=inclusive)
        return f"💰 VAT: ნეტო={r['net']}₾, VAT={r['vat']}₾\n{r['journal']}"

    pay_match = re.search(r'(\d+[\.,]?\d*)\s*(?:ლარი|₾|lari)', msg)
    if pay_match and any(w in msg for w in ["ხელფასი", "salary", "pit", "payg"]):
        amount = float(pay_match.group(1).replace(",", "."))
        r = calculate_payroll(amount)
        return f"👤 ხელფასი: PIT={r['pit']}₾, PAYG={r['payg']}₾, ნეტო={r['net']}₾\n{r['journal']}"

    if any(w in msg for w in ["vat", "დღგ"]) and any(w in msg for w in ["რამდენია", "განაკვეთი", "%"]):
        return "📊 დღგ (VAT) = 18%\nნეტო = ბრუტო ÷ 1.18\nდეკლარაცია: კვარტლის 15-მდე"

    if any(w in msg for w in ["pit", "საშემოსავლო"]) and any(w in msg for w in ["რამდენია", "%"]):
        return "📊 PIT = 20%, PAYG = 2%\nგადახდა: ყოველი თვის 15-მდე, ფორმა N4"

    if any(w in msg for w in ["cit", "დივიდენდი", "მოგება"]):
        return "📊 CIT = 15% (ესტონური მოდელი)\nდივიდენდიდან 15 დღეში, ფორმა N101"

    return None

@router.get("/stats")
async def ai_stats():
    if KB_LOADED:
        s = get_stats()
        s["status"] = "loaded"
        s["llm_available"] = LLM_AVAILABLE
        return s
    return {"status": "not_loaded"}

@router.post("/chat", response_model=ChatResponse)
async def ai_chat(request: ChatRequest):
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="შეტყობინება ცარიელია")

    if KB_LOADED:
        local = _local_answer(message)
        if local:
            return ChatResponse(answer=local, sources=["kb"], confidence=0.98)

    results = []
    context = ""
    if KB_LOADED:
        results = search_knowledge(message, top_k=3)
        context = get_context_for_llm(message)

    if LLM_AVAILABLE and _client:
        try:
            content = f"კონტექსტი:\n{context}\n\nკითხვა: {message}" if context else message
            resp = _client.chat.completions.create(
                model="openai/gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": content}
                ],
                temperature=0.3,
                max_tokens=800
            )
            return ChatResponse(
                answer=resp.choices[0].message.content,
                sources=[f"{r['category']}: {r['source']}" for r in results],
                confidence=0.92,
                session_id=request.session_id
            )
        except Exception as e:
            return ChatResponse(answer=f"⚠️ შეცდომა: {str(e)}", confidence=0.3)

    if results:
        answer = "\n".join([f"• {r['text']}" for r in results[:3]])
    else:
        answer = "სცადეთ: '5900 ლარი დღგ' ან '3000 ლარი ხელფასი'"

    return ChatResponse(answer=answer, sources=[], confidence=0.7)

@router.post("/vat")
async def vat_calc(request: VATRequest):
    if not KB_LOADED:
        raise HTTPException(status_code=503, detail="KB not loaded")
    return calculate_vat(request.amount, request.inclusive)

@router.post("/payroll")
async def payroll_calc(request: PayrollRequest):
    if not KB_LOADED:
        raise HTTPException(status_code=503, detail="KB not loaded")
    return calculate_payroll(request.gross)

@router.post("/classify")
async def classify_tx(request: ClassifyRequest):
    if not KB_LOADED:
        raise HTTPException(status_code=503, detail="KB not loaded")
    return classify_transaction(request.description)

@router.get("/search")
async def search(q: str, top_k: int = 5):
    if not KB_LOADED:
        raise HTTPException(status_code=503, detail="KB not loaded")
    return {"results": search_knowledge(q, top_k), "count": top_k}