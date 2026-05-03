"""
app/api/services/ai_service.py
Bridge Hub — Unified AI Gateway
OpenRouter: GPT-4o, Claude, Gemini, Fallback
"""
import os
import time
import logging
from typing import Optional
from openai import OpenAI
from app.api.metrics import AI_CLASSIFICATION_TOTAL, AI_CLASSIFICATION_DURATION
 
logger = logging.getLogger(__name__)
 
# ── Config ──
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")
 
# OpenRouter-ი ჩართულია თუ key გვაქვს
USE_OPENROUTER = bool(OPENROUTER_API_KEY)
 
# მოდელები
MODELS = {
    "default":  "openai/gpt-4o-mini",        # სწრაფი, იაფი
    "powerful": "openai/gpt-4o",              # რთული ანალიზი
    "georgian": "anthropic/claude-sonnet-4-5", # ქართული ტექსტი
    "fallback": "openai/gpt-4o-mini",         # fallback
}
 
 
def _get_client() -> tuple[OpenAI, str]:
    """
    OpenRouter ან OpenAI client + base model.
    """
    if USE_OPENROUTER:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
            default_headers={
                "HTTP-Referer": "https://bridgehub.ge",
                "X-OpenRouter-Title": "Bridge Hub AI Financial OS",
            },
        )
        return client, MODELS["default"]
    else:
        client = OpenAI(api_key=OPENAI_API_KEY)
        return client, "gpt-4o-mini"
 
 
def classify_transaction(
    description: str,
    amount: float,
    partner: str = "",
    context: dict = None,
    tenant_id: str = "default",
) -> dict:
    """
    ტრანზაქციის AI კლასიფიკაცია.
    OpenRouter → GPT-4o-mini (სწრაფი + იაფი)
    """
    client, model = _get_client()
 
    prompt = f"""ქართული ბუღალტრული სისტემა. კლასიფიცირე ტრანზაქცია:
 
აღწერა: {description}
თანხა: {amount} ₾
პარტნიორი: {partner or 'უცნობი'}
 
დაგვიბრუნე JSON:
{{
  "account_code": "XXXX",
  "account_name": "ანგარიშის სახელი",
  "debit_account": "XXXX", 
  "credit_account": "XXXX",
  "category": "კატეგორია",
  "confidence": 0.0-1.0,
  "reason": "მოკლე ახსნა"
}}
 
Balance.ge COA: 7510=საბანკო საკომ., 7410=კავშირგ., 7210=იჯარა, 7110=ხელფასი, 3320=PIT, 3161=PAYG"""
 
    try:
        start = time.time()
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300,
        )
        elapsed = round(time.time() - start, 2)
        content = resp.choices[0].message.content
 
        import json, re
        m = re.search(r'\{.*\}', content, re.DOTALL)
        if m:
            result = json.loads(m.group())
        else:
            result = {"account_code": "9999", "confidence": 0.5}
 
        AI_CLASSIFICATION_TOTAL.labels(tenant=tenant_id, result="success").inc()
        AI_CLASSIFICATION_DURATION.labels(model=model).observe(elapsed)
        return {
            "ok": True,
            "model": model,
            "provider": "openrouter" if USE_OPENROUTER else "openai",
            "elapsed": elapsed,
            **result,
        }

    except Exception as e:
        logger.error(f"AI classify error: {e}")
        AI_CLASSIFICATION_TOTAL.labels(tenant=tenant_id, result="failure").inc()
        # fallback — rule-based
        return _rule_based_classify(description, amount)
 
 
def chat_with_ai(
    message: str,
    session_history: list = None,
    file_content: str = None,
    tenant_id: str = "default",
) -> dict:
    """
    AI Chat — Bridge Hub ბუღალტრული ასისტენტი.
    ქართული ტექსტისთვის → Claude
    """
    client, _ = _get_client()
 
    # ქართული ტექსტი → Claude
    georgian_chars = sum(1 for c in message if '\u10d0' <= c <= '\u10ff')
    if USE_OPENROUTER and georgian_chars > 3:
        model = MODELS["georgian"]
    else:
        model = MODELS["default"]
 
    system = """შენ ხარ Bridge Hub-ის AI ბუღალტერი-ასისტენტი.
შეგიძლია:
- ტრანზაქციების კლასიფიკაცია Balance.ge COA-ს მიხედვით
- VAT 18%, PAYG 2%, PIT 20% გამოთვლები
- Dr/Cr გატარებების შემოთავაზება
- ქართული საგადასახადო კანონმდებლობის კონსულტაცია
ყოველთვის პასუხობ ქართულ ენაზე."""
 
    messages = [{"role": "system", "content": system}]
    if session_history:
        messages.extend(session_history[-6:])
    if file_content:
        messages.append({"role": "user", "content": f"ფაილის შიგნი:\n{file_content[:2000]}"})
    messages.append({"role": "user", "content": message})
 
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
            max_tokens=800,
        )
        return {
            "ok": True,
            "reply": resp.choices[0].message.content,
            "model": model,
            "provider": "openrouter" if USE_OPENROUTER else "openai",
        }
    except Exception as e:
        logger.error(f"AI chat error: {e}")
        return {"ok": False, "reply": "AI სერვისი დროებით მიუწვდომელია.", "error": str(e)}
 
 
def analyze_invoice_ai(
    text_content: str,
    tenant_id: str = "default",
) -> dict:
    """
    Invoice ტექსტის AI ანალიზი — GPT-4o (powerful).
    """
    client, _ = _get_client()
    model = MODELS["powerful"] if USE_OPENROUTER else "gpt-4o"
 
    prompt = f"""ინვოისიდან ამოიღე:
{text_content[:3000]}
 
JSON:
{{
  "amount": 0.0,
  "vat_amount": 0.0,
  "net_amount": 0.0,
  "partner": "",
  "invoice_number": "",
  "date": "YYYY-MM-DD",
  "currency": "GEL"
}}"""
 
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=300,
        )
        import json, re
        m = re.search(r'\{.*\}', resp.choices[0].message.content, re.DOTALL)
        if m:
            return {"ok": True, "model": model, **json.loads(m.group())}
    except Exception as e:
        logger.error(f"Invoice AI error: {e}")
    return {"ok": False, "error": "AI ანალიზი ვერ მოხდა"}
 
 
def get_ai_status() -> dict:
    """AI სერვისის სტატუსი."""
    return {
        "ok": True,
        "provider": "openrouter" if USE_OPENROUTER else "openai",
        "openrouter_enabled": USE_OPENROUTER,
        "openai_fallback": bool(OPENAI_API_KEY),
        "models": MODELS if USE_OPENROUTER else {"default": "gpt-4o-mini"},
        "features": [
            "transaction classification",
            "georgian language (Claude)",
            "invoice analysis",
            "ai chat",
            "fallback" if USE_OPENROUTER else "no fallback",
        ],
    }
 
 
# ── Rule-based fallback ──
def _rule_based_classify(description: str, amount: float) -> dict:
    d = (description or "").lower()
    rules = [
        (["საკომისიო", "commission", "fee"],           "7510", "საბანკო საკომ."),
        (["მაგთი", "silknet", "internet", "geocell"],  "7410", "კავშირგ. ხარჯი"),
        (["იჯარა", "ქირა", "rent"],                   "7210", "საიჯ. ხარჯი"),
        (["ხელფას", "salary"],                         "7110", "სახელფ. ხარჯი"),
        (["pit", "საშემოსავლო"],                       "3320", "PIT"),
        (["payg", "საპენსიო"],                         "3161", "PAYG"),
        (["ელ.ენ", "telasi", "electricity"],           "7310", "კომუნ. ხარჯი"),
        (["საწვავ", "fuel"],                           "7510", "სამგ. ხარჯი"),
    ]
    for kws, acc, name in rules:
        if any(k in d for k in kws):
            return {
                "ok": True,
                "model": "rule-based",
                "provider": "fallback",
                "account_code": acc,
                "account_name": name,
                "debit_account": acc,
                "credit_account": "1210",
                "confidence": 0.80,
                "reason": "rule-based fallback",
            }
    return {
        "ok": True,
        "model": "rule-based",
        "provider": "fallback",
        "account_code": "9999",
        "account_name": "Uncategorized",
        "confidence": 0.30,
        "reason": "კლასიფიკაცია ვერ მოხდა",
    }