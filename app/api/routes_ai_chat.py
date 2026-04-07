"""
Bridge Hub — AI Chat Routes V3 Final
→ app/api/routes_ai_chat.py
"""

import os
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from openai import OpenAI

try:
    from bridge_hub_knowledge import (
        calculate_vat, calculate_payroll, calculate_cit,
        calculate_depreciation, classify_transaction,
        search_knowledge, learn_new_rule, get_context_for_llm,
        get_stats, CHART_OF_ACCOUNTS,
    )
    KB_LOADED = True
    print("✅ Bridge Hub Knowledge Base V2 ჩაიტვირთა")
except ImportError as e:
    KB_LOADED = False
    print(f"⚠️ KB ვერ მოიძებნა: {e}")

_vector_db_available = False
try:
    from bridge_hub_vector_db import (
        hybrid_search, semantic_search, learn_from_correction,
        get_vector_stats, index_files, get_context_for_llm_hybrid,
    )
    _vector_db_available = True
    print("✅ ChromaDB ჩაიტვირთა")
except ImportError:
    print("ℹ️ ChromaDB არ არის — keyword search")

try:
    _client = OpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1"
    )
    LLM_AVAILABLE = bool(os.getenv("OPENROUTER_API_KEY"))
except Exception:
    _client = None
    LLM_AVAILABLE = False

router = APIRouter(prefix="/api/ai", tags=["AI Assistant"])

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    tenant_id: Optional[str] = "global"
    use_vector_search: Optional[bool] = True

class ChatResponse(BaseModel):
    answer: str
    sources: list = []
    confidence: float = 0.0
    search_method: str = "keyword"
    session_id: Optional[str] = None

class VATRequest(BaseModel):
    amount: float
    inclusive: bool = True
    service_type: Optional[str] = "standard"

class PayrollRequest(BaseModel):
    gross: float
    include_employee_payg: Optional[bool] = True

class CITRequest(BaseModel):
    distributed_profit: float

class DepreciationRequest(BaseModel):
    cost: float
    residual: float
    useful_life_years: int
    method: Optional[str] = "straight_line"

class ClassifyRequest(BaseModel):
    description: str
    tenant_id: Optional[str] = "global"

class LearnRequest(BaseModel):
    pattern: str
    account: str
    tenant_id: Optional[str] = "global"
    note: Optional[str] = ""
    use_vector: Optional[bool] = True

class IndexRequest(BaseModel):
    files_dir: Optional[str] = None
    force_reindex: Optional[bool] = False

SYSTEM_PROMPT = """შენ ხარ Bridge Hub-ის AI ბუღალტერი — ქართული ERP სისტემის ჭკვიანი ასისტენტი.

🇬🇪 საქართველოს საგადასახადო სისტემა:
- VAT (დღგ): 18% — ნეტო = ბრუტო ÷ 1.18 | ექსპორტი: 0% | სამედიცინო/განათლება: გათავისუფლებული
- PIT (საშემოსავლო): 20% + PAYG თანამშრომელი 2% + PAYG დამსაქმებელი 2% | ვადა: ყოველი თვის 15-მდე | ფორმა N4
- CIT (მოგება): 15% ესტონური მოდელი — მხოლოდ განაწილებულ მოგებაზე | ფორმა N101
- Withholding: დივიდენდი 5%, Royalty 10%, პროცენტი 5%

📊 ანგარიშთა გეგმა:
- 1110 ნაღდი | 1120 ბანკი | 1310 მარაგები | 1510 ძირითადი საშუალებები
- 3310 დღგ | 3320 PIT | 3330 PAYG | 3340 CIT | 3350 Withholding
- 6110 გაყიდვები | 6120 მომსახურება | 7210 ხელფასი | 7310 ქირა
- 7410 კომუნალური | 7510 საბანკო საკომისიო | 7710 რეკლამა | 7720 წარმომადგენლობითი

📚 ACCA/IFRS: IFRS 15, IFRS 16 (ROU), IAS 2, IAS 16
🏦 ინტეგრაციები: Balance.ge, 1C, TBC Bank, BOG, RS.ge

წესები:
1. ყოველთვის ქართულად პასუხობ
2. გაანგარიშებები ნაბიჯ-ნაბიჯ
3. ბუღალტრული გატარება Dr/Cr ფორმატით
4. კონკრეტული ანგარიშის კოდები
5. გამონაკლისები — აუცილებლად მიუთითე"""


def _local_answer(message: str) -> Optional[str]:
    if not KB_LOADED:
        return None
    msg = message.lower()

    # CIT — პირველი!
    cit_match = re.search(r'(\d+[\.,]?\d*)\s*(?:ლარი|₾|lari)', msg)
    if cit_match and any(w in msg for w in ["cit", "დივიდენდი", "dividend"]):
        amount = float(cit_match.group(1).replace(",", "."))
        r = calculate_cit(amount)
        return (
            f"📊 **CIT გაანგარიშება — {amount}₾**\n\n"
            f"| | თანხა |\n|---|---|\n"
            f"| განაწილებული მოგება | **{r['distributed_profit']}₾** |\n"
            f"| CIT (15%) | **{r['cit']}₾** |\n"
            f"| **ნეტო დივიდენდი** | **{r['net_dividend']}₾** |\n\n"
            f"📒 **გატარება:**\n```\n{r['journal']}\n```\n\n"
            f"⏰ **ვადა:** {r['deadline']}"
        )

    # Payroll — მეორე!
    pay_match = re.search(r'(\d+[\.,]?\d*)\s*(?:ლარი|₾|lari)', msg)
    if pay_match and any(w in msg for w in ["ხელფასი", "salary", "payroll", "pit", "payg"]):
        amount = float(pay_match.group(1).replace(",", "."))
        r = calculate_payroll(amount)
        return (
            f"👤 **ხელფასის გაანგარიშება — {amount}₾**\n\n"
            f"| | თანხა |\n|---|---|\n"
            f"| ბრუტო ხელფასი | **{r['gross']}₾** |\n"
            f"| PIT (20%) | **{r['pit']}₾** |\n"
            f"| PAYG თანამშრომელი (2%) | **{r['payg_employee']}₾** |\n"
            f"| **ნეტო (ხელზე)** | **{r['net']}₾** |\n"
            f"| PAYG დამსაქმებელი (2%) | **{r['payg_employer']}₾** |\n"
            f"| **ჯამური ხარჯი** | **{r['total_employer_cost']}₾** |\n\n"
            f"📒 **გატარება:**\n```\n{r['journal']}\n```\n\n"
            f"⏰ **ვადა:** {r['deadline']}"
        )

    # VAT — მესამე!
    vat_match = re.search(r'(\d+[\.,]?\d*)\s*(?:ლარი|₾|lari)', msg)
    if vat_match and any(w in msg for w in ["vat", "დღგ", "ამოიღე", "გამოყავი"]):
        amount = float(vat_match.group(1).replace(",", "."))
        inclusive = not any(w in msg for w in ["გარეშე", "without", "exclusive"])
        r = calculate_vat(amount, inclusive=inclusive)
        if r.get("vat", 0) == 0:
            return f"ℹ️ **{r.get('note', 'VAT = 0')}**"
        return (
            f"💰 **VAT გაანგარიშება — {amount}₾**\n\n"
            f"| | თანხა |\n|---|---|\n"
            f"| ნეტო (VAT-ის გარეშე) | **{r['net']}₾** |\n"
            f"| დღგ (18%) | **{r['vat']}₾** |\n"
            f"| ბრუტო (VAT-ჩათვლილი) | **{r['gross']}₾** |\n\n"
            f"📒 **გატარება:**\n```\n{r['journal']}\n```"
        )

    # VAT განაკვეთი
    if any(w in msg for w in ["vat", "დღგ"]) and any(w in msg for w in ["განაკვეთი", "რამდენია", "%", "რა არის"]):
        return (
            "📊 **დღგ (VAT) — საქართველო**\n\n"
            "| | |\n|---|---|\n"
            "| სტანდარტული | **18%** |\n"
            "| ექსპორტი | **0%** |\n"
            "| სამედიცინო/განათლება | **გათავისუფლებული** |\n"
            "| VAT გადამხდელი | ბრუნვა > 100,000₾/წელ |\n"
            "| დეკლარაცია | კვარტლის 15-მდე |"
        )

    return None


@router.get("/stats")
async def ai_stats():
    result = {
        "status": "loaded" if KB_LOADED else "not_loaded",
        "llm_available": LLM_AVAILABLE,
        "vector_db_available": _vector_db_available,
    }
    if KB_LOADED:
        result["knowledge_base"] = get_stats()
    return result


@router.post("/chat", response_model=ChatResponse)
async def ai_chat(request: ChatRequest):
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="შეტყობინება ცარიელია")

    if KB_LOADED:
        local = _local_answer(message)
        if local:
            return ChatResponse(
                answer=local, sources=["kb"],
                confidence=0.98, search_method="local_rules",
                session_id=request.session_id,
            )

    context = ""
    sources = []
    search_method = "keyword"

    if request.use_vector_search and _vector_db_available:
        try:
            context = get_context_for_llm_hybrid(message, max_chars=4000)
            search_method = "hybrid"
            sources = ["ChromaDB + KB"]
        except Exception:
            pass

    if not context and KB_LOADED:
        context = get_context_for_llm(message, max_chars=3000)
        results = search_knowledge(message, top_k=5)
        sources = [f"{r['category']}: {r['source']}" for r in results]

    if LLM_AVAILABLE and _client:
        content = f"კონტექსტი:\n{context}\n\nკითხვა: {message}" if context else message
        for model in ["google/gemini-1.5-flash", "openai/gpt-4o-mini"]:
            try:
                resp = _client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": content},
                    ],
                    temperature=0.3, max_tokens=1000,
                )
                return ChatResponse(
                    answer=resp.choices[0].message.content,
                    sources=sources, confidence=0.92,
                    search_method=search_method,
                    session_id=request.session_id,
                )
            except Exception:
                continue
        return ChatResponse(answer="⚠️ AI დროებით მიუწვდომელია", confidence=0.3)

    answer = f"📚 {context[:800]}" if context else "სცადეთ: '5900 ლარი VAT' ან '3000 ლარი ხელფასი'"
    return ChatResponse(answer=answer, sources=sources, confidence=0.7)


@router.get("/search")
async def ai_search(q: str, top_k: int = 5, use_vector: bool = True):
    if use_vector and _vector_db_available:
        try:
            return {"query": q, "results": hybrid_search(q, top_k), "method": "hybrid"}
        except Exception:
            pass
    if KB_LOADED:
        return {"query": q, "results": search_knowledge(q, top_k), "method": "keyword"}
    raise HTTPException(status_code=503, detail="KB not loaded")


@router.post("/vat")
async def vat_calc(request: VATRequest):
    if not KB_LOADED:
        raise HTTPException(status_code=503)
    return calculate_vat(request.amount, request.inclusive, request.service_type)


@router.post("/payroll")
async def payroll_calc(request: PayrollRequest):
    if not KB_LOADED:
        raise HTTPException(status_code=503)
    return calculate_payroll(request.gross, request.include_employee_payg)


@router.post("/cit")
async def cit_calc(request: CITRequest):
    if not KB_LOADED:
        raise HTTPException(status_code=503)
    return calculate_cit(request.distributed_profit)


@router.post("/depreciation")
async def dep_calc(request: DepreciationRequest):
    if not KB_LOADED:
        raise HTTPException(status_code=503)
    return calculate_depreciation(request.cost, request.residual, request.useful_life_years, request.method)


@router.post("/classify")
async def classify_tx(request: ClassifyRequest):
    if not KB_LOADED:
        raise HTTPException(status_code=503)
    result = classify_transaction(request.description, request.tenant_id)
    return {**result, "account_type": CHART_OF_ACCOUNTS.get(result["account"], {}).get("type", "unknown")}


@router.post("/learn")
async def learn_rule(request: LearnRequest):
    results = {}
    if KB_LOADED:
        results["python_rules"] = learn_new_rule(request.pattern, request.account, request.tenant_id, request.note)
    if request.use_vector and _vector_db_available:
        try:
            results["vector_db"] = learn_from_correction(request.pattern, request.account, tenant_id=request.tenant_id, note=request.note)
        except Exception as e:
            results["vector_db"] = {"status": "error", "error": str(e)}
    account_name = CHART_OF_ACCOUNTS.get(request.account, {}).get("name", request.account) if KB_LOADED else request.account
    return {
        "status": "learned",
        "message": f"✅ ვისწავლე: '{request.pattern}' → {request.account} ({account_name})",
        "stored_in": list(results.keys()),
    }


@router.post("/index")
async def index_files_ep(request: IndexRequest):
    if not _vector_db_available:
        raise HTTPException(status_code=503, detail="ChromaDB არ არის")
    stats = index_files(request.files_dir, request.force_reindex)
    return {"status": "success", **stats}


@router.get("/vector-stats")
async def vector_stats():
    if not _vector_db_available:
        return {"available": False}
    try:
        return {"available": True, **get_vector_stats()}
    except Exception as e:
        return {"available": True, "error": str(e)}