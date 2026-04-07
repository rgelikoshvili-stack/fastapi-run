"""
Bridge Hub — AI Chat Routes (V3: Hybrid Search + ChromaDB + Self-Learning)
→ app/api/routes_ai_chat.py

Endpoints:
  GET  /api/ai/stats         — სტატისტიკა (Python rules + ChromaDB)
  POST /api/ai/chat          — AI ჩატი (Hybrid RAG)
  POST /api/ai/vat           — VAT გაანგარიშება
  POST /api/ai/payroll       — ხელფასი + PIT/PAYG
  POST /api/ai/cit           — CIT 15% (ესტონური მოდელი)
  POST /api/ai/depreciation  — ამორტიზაცია
  POST /api/ai/classify      — ტრანზაქციის კლასიფიკაცია
  GET  /api/ai/search        — ჰიბრიდური ძიება
  POST /api/ai/learn         — Self-learning (ბუღალტრის შესწორება)
  POST /api/ai/index         — ფაილების ინდექსირება ChromaDB-ში
  GET  /api/ai/vector-stats  — ChromaDB სტატისტიკა
"""

import os
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from openai import OpenAI

# ══════════════════════════════════════════════════════════════
# Knowledge Base — Python rules (სწრაფი, ყოველთვის ხელმისაწვდომი)
# ══════════════════════════════════════════════════════════════
try:
    from bridge_hub_knowledge import (
        calculate_vat,
        calculate_payroll,
        calculate_cit,
        calculate_depreciation,
        classify_transaction,
        search_knowledge,
        learn_new_rule,
        get_context_for_llm,
        get_stats,
        CHART_OF_ACCOUNTS,
    )
    KB_LOADED = True
    print("✅ Bridge Hub Knowledge Base V2 ჩაიტვირთა")
except ImportError as e:
    KB_LOADED = False
    print(f"⚠️  bridge_hub_knowledge.py ვერ მოიძებნა: {e}")

# ══════════════════════════════════════════════════════════════
# Vector DB — ChromaDB (სემანტიკური ძიება, optional)
# ══════════════════════════════════════════════════════════════
_vector_db_available = False
try:
    from bridge_hub_vector_db import (
        hybrid_search,
        semantic_search,
        learn_from_correction,
        get_vector_stats,
        index_files,
        get_context_for_llm_hybrid,
    )
    _vector_db_available = True
    print("✅ ChromaDB Vector DB ჩაიტვირთა")
except ImportError:
    print("ℹ️  ChromaDB არ არის — keyword search-ს ვიყენებ")

# ══════════════════════════════════════════════════════════════
# OpenAI კლიენტი
# ══════════════════════════════════════════════════════════════
try:
    _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    LLM_AVAILABLE = True
except Exception:
    _openai_client = None
    LLM_AVAILABLE = False

router = APIRouter(prefix="/api/ai", tags=["AI Assistant"])

# ══════════════════════════════════════════════════════════════
# Pydantic Models
# ══════════════════════════════════════════════════════════════
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


# ══════════════════════════════════════════════════════════════
# სისტემური პრომპტი
# ══════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """შენ ხარ Bridge Hub-ის AI ბუღალტერი — ქართული ERP სისტემის ჭკვიანი ასისტენტი.

🇬🇪 საქართველოს საგადასახადო სისტემა:
• VAT (დღგ): 18% — ნეტო = ბრუტო ÷ 1.18 | ექსპორტი: 0% | სამედიცინო/განათლება: გათავისუფლებული
• PIT (საშემოსავლო): 20% + PAYG 2% | ვადა: ყოველი თვის 15-მდე | ფორმა N4
• CIT (მოგება): 15% ესტონური მოდელი — მხოლოდ განაწილებულ მოგებაზე | ფორმა N101
• Withholding: დივიდენდი 5%, Royalty 10%, პროცენტი 5%

📊 ანგარიშთა გეგმა:
• 1110 ნაღდი | 1120 ბანკი | 1310 მარაგები | 1510 ძირითადი საშუალებები
• 3310 დღგ | 3320 PIT | 3330 PAYG | 3340 CIT | 3350 Withholding
• 6110 გაყიდვები | 6120 მომსახურება | 7210 ხელფასი | 7310 ქირა
• 7410 კომუნალური | 7510 საბანკო საკომისიო | 7710 რეკლამა | 7720 წარმომადგენლობითი

📚 ACCA/IFRS: IFRS 15 (შემოსავალი), IFRS 16 (იჯარა/ROU), IAS 2 (მარაგები), IAS 16 (ძირითადი)

🏦 ინტეგრაციები: Balance.ge, 1C, TBC Bank, BOG, RS.ge

წესები:
1. ყოველთვის ქართულად პასუხობ
2. გაანგარიშებები ნაბიჯ-ნაბიჯ
3. ბუღალტრული გატარება Dr/Cr ფორმატით
4. კონკრეტული ანგარიშის კოდები (7510, 3310 და სხვ.)
5. გამონაკლისები (ექსპორტი, სამედიცინო) — აუცილებლად მიუთითე"""


# ══════════════════════════════════════════════════════════════
# ლოკალური სწრაფი პასუხები (LLM-ის გარეშე)
# ══════════════════════════════════════════════════════════════
def _local_answer(message: str) -> Optional[str]:
    """სწრაფი ლოკალური პასუხი — 0ms, LLM-ის გარეშე."""
    if not KB_LOADED:
        return None
    msg = message.lower()

    # VAT გაანგარიშება
    vat_match = re.search(r'(\d+[\.,]?\d*)\s*(?:ლარი|₾|lari)', msg)
    if vat_match and any(w in msg for w in ["vat", "დღგ", "ამოიღე", "გამოყავი", "გამოვიყვანო"]):
        amount = float(vat_match.group(1).replace(",", "."))
        inclusive = not any(w in msg for w in ["გარეშე", "without", "exclusive"])
        result = calculate_vat(amount, inclusive=inclusive)
        if result.get("vat", 0) == 0:
            return f"ℹ️ **{result.get('note', 'VAT = 0')}**"
        return (
            f"💰 **VAT გაანგარიშება — {amount}₾**\n\n"
            f"| | თანხა |\n|---|---|\n"
            f"| ნეტო (VAT-ის გარეშე) | **{result['net']}₾** |\n"
            f"| დღგ (18%) | **{result['vat']}₾** |\n"
            f"| ბრუტო (VAT-ჩათვლილი) | **{result['gross']}₾** |\n\n"
            f"📒 **გატარება:**\n```\n{result['journal']}\n```"
        )

    # Payroll
    pay_match = re.search(r'(\d+[\.,]?\d*)\s*(?:ლარი|₾|lari)', msg)
    if pay_match and any(w in msg for w in ["ხელფასი", "salary", "payroll", "pit", "payg"]):
        amount = float(pay_match.group(1).replace(",", "."))
        result = calculate_payroll(amount)
        return (
            f"👤 **ხელფასის გაანგარიშება — {amount}₾**\n\n"
            f"| | თანხა |\n|---|---|\n"
            f"| ბრუტო ხელფასი | **{result['gross']}₾** |\n"
            f"| PIT (20%) | **{result['pit']}₾** |\n"
            f"| PAYG თანამშრომელი (2%) | **{result['payg_employee']}₾** |\n"
            f"| **ნეტო (ხელზე)** | **{result['net']}₾** |\n"
            f"| PAYG დამსაქმებელი (2%) | **{result['payg_employer']}₾** |\n"
            f"| **ჯამური ხარჯი** | **{result['total_employer_cost']}₾** |\n\n"
            f"📒 **გატარება:**\n```\n{result['journal']}\n```\n\n"
            f"⏰ **ვადა:** {result['deadline']}"
        )

    # VAT განაკვეთი
    if any(w in msg for w in ["vat", "დღგ"]) and any(w in msg for w in ["განაკვეთი", "რამდენია", "%", "რა არის"]):
        return (
            "📊 **დღგ (VAT) — საქართველო**\n\n"
            "| | |\n|---|---|\n"
            "| სტანდარტული განაკვეთი | **18%** |\n"
            "| ფორმულა (ჩათვლილი) | ნეტო = ბრუტო ÷ 1.18 |\n"
            "| ფორმულა (გარეშე) | VAT = ნეტო × 0.18 |\n"
            "| ექსპორტი | **0%** (ჩათვლის უფლებით) |\n"
            "| სამედიცინო/განათლება | **გათავისუფლებული** |\n"
            "| VAT გადამხდელი | ბრუნვა > 100,000₾/წელ |\n"
            "| დეკლარაცია | კვარტლის 15-მდე |\n\n"
            "📒 **გატარება (გაყიდვა):** Dr 1310 / Cr 6110 (ნეტო) + Cr 3310 (VAT)"
        )

    # CIT
    if any(w in msg for w in ["cit", "მოგება", "dividend", "დივიდენდი"]) and any(w in msg for w in ["განაკვეთი", "რამდენია", "%", "რა არის", "ესტონური"]):
        return (
            "📊 **მოგების გადასახადი (CIT) — ესტონური მოდელი**\n\n"
            "| | |\n|---|---|\n"
            "| განაკვეთი | **15%** |\n"
            "| მოდელი | ესტონური (მხოლოდ განაწილებულ მოგებაზე) |\n"
            "| ვადა | დივიდენდიდან 15 დღეში |\n"
            "| ფორმა | N101 |\n\n"
            "⚠️ **ჩათვლილი განაწილება:** წარმომადგენლობითი > 1%, არარეზიდენტზე Royalty\n\n"
            "📒 **გატარება:** Dr 4210 / Cr 3340 (CIT) + Cr 1120 (ნეტო)"
        )

    return None


# ══════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════

@router.get("/stats")
async def ai_stats():
    """სტატისტიკა — Python rules + ChromaDB."""
    result = {
        "status": "loaded" if KB_LOADED else "not_loaded",
        "llm_available": LLM_AVAILABLE,
        "vector_db_available": _vector_db_available,
    }
    if KB_LOADED:
        result["knowledge_base"] = get_stats()
    if _vector_db_available:
        try:
            result["vector_db"] = get_vector_stats()
        except Exception as e:
            result["vector_db"] = {"status": "error", "error": str(e)}
    return result


@router.post("/chat", response_model=ChatResponse)
async def ai_chat(request: ChatRequest):
    """AI ბუღალტრული ჩატი — Hybrid RAG (ChromaDB + Python Rules + GPT)."""
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="შეტყობინება ცარიელია")

    sources = []
    search_method = "keyword"

    # 1. სწრაფი ლოკალური პასუხი (LLM-ის გარეშე)
    if KB_LOADED:
        local = _local_answer(message)
        if local:
            return ChatResponse(
                answer=local,
                sources=["bridge_hub_knowledge.py"],
                confidence=0.98,
                search_method="local_rules",
                session_id=request.session_id,
            )

    # 2. კონტექსტის მომზადება — Hybrid ან Keyword
    context = ""
    if request.use_vector_search and _vector_db_available:
        try:
            context = get_context_for_llm_hybrid(message, max_chars=4000)
            search_method = "hybrid"
            sources = ["ChromaDB + Python Rules"]
        except Exception:
            pass

    if not context and KB_LOADED:
        context = get_context_for_llm(message, max_chars=3000)
        search_method = "keyword"
        results = search_knowledge(message, top_k=5)
        sources = [f"{r['category']}: {r['source']}" for r in results]

    # 3. LLM-ით პასუხი
    if LLM_AVAILABLE and _openai_client:
        try:
            user_content = message
            if context:
                user_content = f"კონტექსტი ({search_method}):\n{context}\n\nკითხვა: {message}"

            response = _openai_client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.3,
                max_tokens=1000,
            )
            answer = response.choices[0].message.content
            confidence = 0.92
        except Exception as e:
            answer = f"⚠️ LLM შეცდომა: {str(e)}\n\nსცადეთ: '5900 ლარი VAT' ან '3000 ლარი ხელფასი'"
            confidence = 0.5
    else:
        # LLM-ის გარეშე — ცოდნის ბაზიდან
        if context:
            answer = f"📚 **ცოდნის ბაზიდან:**\n\n{context[:800]}"
        else:
            answer = "🤔 ამ კითხვაზე პასუხი ვერ მოვძებნე. სცადეთ: '5900 ლარი VAT' ან '3000 ლარი ხელფასი'"
        confidence = 0.7

    return ChatResponse(
        answer=answer,
        sources=sources,
        confidence=confidence,
        search_method=search_method,
        session_id=request.session_id,
    )


@router.get("/search")
async def ai_search(q: str, top_k: int = 5, use_vector: bool = True):
    """ჰიბრიდური ძიება — Semantic + Keyword."""
    if use_vector and _vector_db_available:
        try:
            results = hybrid_search(q, top_k=top_k)
            return {"query": q, "results": results, "method": "hybrid", "count": len(results)}
        except Exception:
            pass
    if KB_LOADED:
        results = search_knowledge(q, top_k=top_k)
        return {"query": q, "results": results, "method": "keyword", "count": len(results)}
    raise HTTPException(status_code=503, detail="Knowledge base not loaded")


@router.post("/vat")
async def vat_calculate(request: VATRequest):
    """VAT გაანგარიშება — გამონაკლისების ჩათვლით."""
    if not KB_LOADED:
        raise HTTPException(status_code=503, detail="Knowledge base not loaded")
    return calculate_vat(request.amount, request.inclusive, request.service_type)


@router.post("/payroll")
async def payroll_calculate(request: PayrollRequest):
    """ხელფასის გაანგარიშება — PIT + PAYG + ნეტო."""
    if not KB_LOADED:
        raise HTTPException(status_code=503, detail="Knowledge base not loaded")
    return calculate_payroll(request.gross, request.include_employee_payg)


@router.post("/cit")
async def cit_calculate(request: CITRequest):
    """CIT — ესტონური მოდელი 15%."""
    if not KB_LOADED:
        raise HTTPException(status_code=503, detail="Knowledge base not loaded")
    return calculate_cit(request.distributed_profit)


@router.post("/depreciation")
async def depreciation_calculate(request: DepreciationRequest):
    """ამორტიზაციის გაანგარიშება."""
    if not KB_LOADED:
        raise HTTPException(status_code=503, detail="Knowledge base not loaded")
    return calculate_depreciation(request.cost, request.residual, request.useful_life_years, request.method)


@router.post("/classify")
async def classify(request: ClassifyRequest):
    """ტრანზაქციის კლასიფიკაცია — Tenant + Global + Learned წესებით."""
    if not KB_LOADED:
        raise HTTPException(status_code=503, detail="Knowledge base not loaded")
    result = classify_transaction(request.description, request.tenant_id)
    account_info = CHART_OF_ACCOUNTS.get(result["account"], {})
    return {
        **result,
        "account_type": account_info.get("type", "unknown"),
    }


@router.post("/learn")
async def learn_rule(request: LearnRequest):
    """
    Self-learning — ბუღალტერი ასწავლის AI-ს ახალ წესს.

    მაგ:
        {"pattern": "Wolt", "account": "7720", "note": "Wolt = წარმომადგენლობითი"}
        {"pattern": "AWS", "account": "7810", "note": "Amazon AWS = IT ხარჯი"}
        {"pattern": "Glovo", "account": "7720"}
    """
    results = {}

    # 1. Python rules-ში (სწრაფი, ყოველთვის)
    if KB_LOADED:
        py_result = learn_new_rule(request.pattern, request.account, request.tenant_id, request.note)
        results["python_rules"] = py_result

    # 2. ChromaDB-ში (სემანტიკური)
    if request.use_vector and _vector_db_available:
        try:
            vec_result = learn_from_correction(
                request.pattern, request.account,
                tenant_id=request.tenant_id, note=request.note,
            )
            results["vector_db"] = vec_result
        except Exception as e:
            results["vector_db"] = {"status": "error", "error": str(e)}

    account_name = CHART_OF_ACCOUNTS.get(request.account, {}).get("name", request.account) if KB_LOADED else request.account
    return {
        "status": "learned",
        "message": f"✅ ვისწავლე: '{request.pattern}' → {request.account} ({account_name})",
        "stored_in": list(results.keys()),
        "details": results,
    }


@router.post("/index")
async def index_knowledge_files(request: IndexRequest):
    """
    ფაილების ინდექსირება ChromaDB-ში.

    1. შექმენი საქაღალდე: knowledge_files/
    2. ჩასვი PDF, DOCX, TXT, MD ფაილები
    3. გამოიძახე ეს endpoint
    """
    if not _vector_db_available:
        raise HTTPException(
            status_code=503,
            detail="ChromaDB არ არის. გაუშვი: pip install chromadb sentence-transformers",
        )
    try:
        stats = index_files(request.files_dir, request.force_reindex)
        return {
            "status": "success",
            "indexed": stats.get("indexed", 0),
            "skipped": stats.get("skipped", 0),
            "chunks": stats.get("chunks", 0),
            "errors": stats.get("errors", 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vector-stats")
async def vector_db_stats():
    """ChromaDB სტატისტიკა."""
    if not _vector_db_available:
        return {"available": False, "message": "ChromaDB არ არის დაინსტალირებული"}
    try:
        stats = get_vector_stats()
        return {"available": True, **stats}
    except Exception as e:
        return {"available": True, "status": "error", "error": str(e)}
