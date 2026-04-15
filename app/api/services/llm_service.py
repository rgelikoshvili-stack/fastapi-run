import re
﻿"""
app/api/services/llm_service.py
Bridge Hub — Unified LLM Gateway
"""

import os, re, json, hashlib, logging
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

MODEL_COSTS = {
    "gpt-4o":            {"in": 0.0000025,  "out": 0.000010},
    "gpt-4o-mini":       {"in": 0.00000015, "out": 0.0000006},
    "claude-sonnet-4-6": {"in": 0.000003,   "out": 0.000015},
    "gemini-2.5-flash":  {"in": 0.00000125, "out": 0.000005},
}

_cache: dict = {}
CACHE_MAX = 5000


def _cache_key(description: str, tenant_id: str) -> str:
    return hashlib.md5(f"{tenant_id}:{description.strip().lower()}".encode()).hexdigest()


def _get_db():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def _log_cost(tenant_id, model, tokens_in, tokens_out):
    cost = (tokens_in  * MODEL_COSTS.get(model, {}).get("in",  0) +
            tokens_out * MODEL_COSTS.get(model, {}).get("out", 0))
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO llm_cost_log
                    (tenant_id, model, tokens_in, tokens_out, cost_usd, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (tenant_id, model, tokens_in, tokens_out,
                  round(cost, 8), datetime.now(timezone.utc)))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"llm_cost_log: {e}")
    return round(cost, 8)


def classify(description: str, context: dict, tenant_id: str = "default") -> dict:
    ck = _cache_key(description, tenant_id)
    if ck in _cache:
        r = _cache[ck].copy()
        r["source"] = "cache"
        r["llm_cost"] = 0.0
        return r
    try:
        result = _call_gpt(description, context, "gpt-4o", tenant_id)
        if result.get("confidence", 0) < 0.60:
            mini = _call_gpt(description, context, "gpt-4o-mini", tenant_id)
            if mini.get("confidence", 0) >= result.get("confidence", 0):
                result = mini
        if len(_cache) >= CACHE_MAX:
            del _cache[next(iter(_cache))]
        _cache[ck] = result.copy()
        return result
    except Exception as e:
        logger.error(f"classify error: {e}")
        return {"account_code": None, "confidence": 0.0,
                "source": "error", "llm_cost": 0.0}


def _call_gpt(description, context, model, tenant_id):
    from openai import OpenAI
    client = OpenAI(
            api_key=os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY"),
            base_url="https://openrouter.ai/api/v1" if os.environ.get("OPENROUTER_API_KEY") else None,
        )
    prompt = f"ტრანზაქცია: {description}"
    if context.get("partner"): prompt += f"\nპარტნიორი: {context['partner']}"
    if context.get("amount"):  prompt += f"\nთანხა: {context['amount']} GEL"
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "შენ ხარ ქართული საბუღალტრო AI. გაანალიზე ტრანზაქცია და დააბრუნე JSON ობიექტი. account_code უნდა იყოს რეალური 4-ნიშნა საბუღალტრო კოდი (7110=ხელფასი, 7130=კომუნალური, 7190=სხვა ხარჯი, 6100=შემოსავალი). confidence=0.0-1.0. reasoning=მოკლე ახსნა."},
            {"role": "user",   "content": prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_tokens=200
    )
    data = json.loads(resp.choices[0].message.content)
    cost = _log_cost(tenant_id, model,
                     resp.usage.prompt_tokens, resp.usage.completion_tokens)
    return {
        "account_code": data.get("account_code"),
        "confidence":   float(data.get("confidence", 0.5)),
        "reasoning":    data.get("reasoning", ""),
        "source":       f"gpt:{model}",
        "llm_cost":     cost,
    }


def generate_preview(draft: dict, tenant_id: str = "default") -> str:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        desc = draft.get("description", "")
        amount = draft.get("amount", 0) or 0
        if not amount:
            m = re.search(r"(\d+(?:[.,]\d+)?)", desc)
            amount = float(m.group(1).replace(",", ".")) if m else 0
        account = draft.get("account_dr", "")
        prompt = (
            f"შენ ხარ Bridge Hub AI — ქართული ბუღალტრული ასისტენტი. "
            f"ტრანზაქცია: '{desc}' | თანხა: {amount} GEL | ანგარიში: {account}. "
            f"დაწერე ერთი მოკლე, ზუსტი ქართული წინადადება."
        )
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=150,
            messages=[{"role": "user", "content": prompt}]
        )
        _log_cost(tenant_id, "claude-sonnet-4-6",
                  resp.usage.input_tokens, resp.usage.output_tokens)
        return resp.content[0].text.strip()
    except Exception as e:
        logger.error(f"preview error: {e}")
        desc = draft.get("description", "")
        amount = draft.get("amount", 0) or 0
        if not amount:
            m = re.search(r"(\d+(?:[.,]\d+)?)", desc)
            amount = float(m.group(1).replace(",", ".")) if m else 0
        return f"{desc} — {amount} GEL"


def chat_with_claude(message: str, context: str = "", tenant_id: str = "default") -> str:
    """Claude as main Bridge Hub chat brain"""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        system = (
            "შენ ხარ Bridge Hub AI — ქართული AI ბუღალტრული სისტემის ასისტენტი. "
            "შეგიძლია: VAT/დღგ 18%, Payroll PIT 20% + PAYG 2%, CIT 15%, "
            "დივიდენდი 5%, Balance.ge გატარებები, TBC/BOG ბანკის ამონაწერი, "
            "invoice OCR, 1C export, Excel/PDF export. "
            "ყოველთვის პასუხობ ქართულად. ციფრებს ლარში წარმოადგენ. "
            "ბუღალტრული კოდებისთვის გამოიყენე ქართული COA სტანდარტი."
        )
        messages = []
        if context:
            messages.append({"role": "user", "content": "კონტექსტი:\n" + context})
            messages.append({"role": "assistant", "content": "კონტექსტი გავითვალისწინე."})
        messages.append({"role": "user", "content": message})
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=system,
            messages=messages
        )
        _log_cost(tenant_id, "claude-sonnet-4-6",
                  resp.usage.input_tokens, resp.usage.output_tokens)
        return resp.content[0].text.strip()
    except Exception as e:
        logger.error(f"claude chat error: {e}")
        return None


def analyze_error(error_text: str, context: dict, tenant_id: str = "default") -> str:
    try:
        from google import genai
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Balance.ge შეცდომა: {error_text}\nახსენი ქართულად 2 წინადადებით.")
        _log_cost(tenant_id, "gemini-2.5-flash",
                  len(error_text) // 4, len(resp.text) // 4)
        return resp.text.strip()
    except Exception as e:
        return f"შეცდომა: {error_text}"


def analyze_correction(original: str, corrected: str,
                        description: str, tenant_id: str = "default") -> dict:
    try:
        from google import genai
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        prompt = (f"კორექცია: '{description}' — {original}  {corrected}. "
                  f"JSON: {{\"pattern_keyword\":\"...\",\"confidence_boost\":0.1}}")
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        text = resp.text.strip().replace("```json","").replace("```","")
        data = json.loads(text)
        return {
            "pattern_keyword":  data.get("pattern_keyword", description[:30]),
            "confidence_boost": float(data.get("confidence_boost", 0.1)),
        }
    except:
        return {"pattern_keyword": description[:30], "confidence_boost": 0.1}


def get_cost_summary(tenant_id: str, days: int = 30) -> dict:
    try:
        conn = _get_db()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT model, COUNT(*) calls, SUM(cost_usd) total_cost_usd
                FROM llm_cost_log
                WHERE tenant_id = %s
                  AND created_at >= NOW() - INTERVAL %s
                GROUP BY model
                ORDER BY total_cost_usd DESC
            """, (tenant_id, f"{days} days"))
            rows = cur.fetchall()
        conn.close()
        total = sum(r["total_cost_usd"] or 0 for r in rows)
        return {"tenant_id": tenant_id, "days": days,
                "total": round(total, 6),
                "by_model": [dict(r) for r in rows]}
    except Exception as e:
        return {"tenant_id": tenant_id, "error": str(e)}


def clear_cache():
    global _cache
    _cache = {}
    logger.info("LLM cache cleared")
