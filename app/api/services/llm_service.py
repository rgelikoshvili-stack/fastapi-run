"""
app/api/services/llm_service.py
Bridge Hub — Unified LLM Gateway
"""

import json
import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.api.db import get_conn, _q

logger = logging.getLogger(__name__)

MODEL_COSTS = {
    "gpt-4o": {"in": 0.0000025, "out": 0.000010},
    "gpt-4o-mini": {"in": 0.00000015, "out": 0.0000006},
    "claude-sonnet-4-6": {"in": 0.000003, "out": 0.000015},
    "gemini-2.5-flash": {"in": 0.00000125, "out": 0.000005},
}

_cache: dict = {}
CACHE_MAX = 5000


def _cache_key(description: str, tenant_id: str) -> str:
    return hashlib.md5(f"{tenant_id}:{description.strip().lower()}".encode()).hexdigest()



def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _extract_amount_from_text(text: str) -> float:
    text = _safe_text(text)
    m = re.search(r"(\d+(?:[.,]\d+)?)", text)
    if not m:
        return 0.0
    return float(m.group(1).replace(",", "."))


def _fire_log_cost(tenant_id, model, tokens_in, tokens_out) -> float:
    """Sync wrapper — schedules _log_cost as a background task if loop is running."""
    cost = round(
        tokens_in * MODEL_COSTS.get(model, {}).get("in", 0)
        + tokens_out * MODEL_COSTS.get(model, {}).get("out", 0),
        8,
    )
    try:
        import asyncio as _aio
        loop = _aio.get_running_loop()
        loop.create_task(_log_cost(tenant_id, model, tokens_in, tokens_out))
    except RuntimeError:
        pass  # no running loop — skip logging (sync/thread-pool context)
    return cost


async def _log_cost(tenant_id, model, tokens_in, tokens_out) -> float:
    cost = round(
        tokens_in * MODEL_COSTS.get(model, {}).get("in", 0)
        + tokens_out * MODEL_COSTS.get(model, {}).get("out", 0),
        8,
    )
    try:
        async with get_conn() as conn:
            await conn.execute(_q("""
                INSERT INTO llm_cost_log
                    (tenant_id, model, tokens_in, tokens_out, cost_usd, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """), tenant_id, model, tokens_in, tokens_out, cost, datetime.now(timezone.utc))
    except Exception as e:
        logger.warning("llm_cost_log failed: %s", e)
    return cost


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
        return {
            "account_code": None,
            "confidence": 0.0,
            "reasoning": f"LLM classify error: {str(e)}",
            "source": "error",
            "llm_cost": 0.0,
        }


def _call_gpt(description: str, context: dict, model: str, tenant_id: str) -> dict:
    from openai import OpenAI

    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY / OPENAI_API_KEY is not configured")

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1" if os.environ.get("OPENROUTER_API_KEY") else None,
    )

    prompt = f"ტრანზაქცია: {description}"

    if context.get("partner"):
        prompt += f"\nპარტნიორი: {context['partner']}"
    if context.get("amount"):
        prompt += f"\nთანხა: {context['amount']} GEL"
    if context.get("memory_account_code"):
        prompt += f"\nწინა მეხსიერების ანგარიში: {context['memory_account_code']}"
    if context.get("memory_reasoning"):
        prompt += f"\nწინა მეხსიერების ახსნა: {context['memory_reasoning']}"
    if context.get("context"):
        prompt += f"\nკონტექსტი:\n{context['context']}"

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "შენ ხარ ქართული საბუღალტრო AI. "
                    "გაანალიზე ტრანზაქცია და დააბრუნე JSON ობიექტი. "
                    "account_code უნდა იყოს რეალური 4-ნიშნა საბუღალტრო კოდი. "
                    "confidence=0.0-1.0. reasoning=მოკლე ახსნა ქართულად."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_tokens=200,
    )

    data = json.loads(resp.choices[0].message.content)
    cost = _fire_log_cost(tenant_id, model, resp.usage.prompt_tokens, resp.usage.completion_tokens)

    return {
        "account_code": data.get("account_code"),
        "confidence": float(data.get("confidence", 0.5)),
        "reasoning": data.get("reasoning", ""),
        "source": f"gpt:{model}",
        "llm_cost": cost,
    }


def generate_preview(draft: dict, tenant_id: str = "default") -> str:
    """Clean deterministic preview — no LLM (prevents hallucination)."""
    desc = _safe_text(draft.get("description", "")) or "ტრანზაქცია"
    amount = draft.get("amount", 0) or 0
    if not amount:
        amount = _extract_amount_from_text(desc)
    account = _safe_text(draft.get("account_dr", ""))
    partner = _safe_text(draft.get("partner", ""))

    parts = [desc]
    if partner and partner.lower() not in desc.lower():
        parts.append(partner)
    if account:
        parts.append(f"ანგ. {account}")
    if amount:
        parts.append(f"{amount:,.2f} ₾")

    return " | ".join(parts)


# In-memory cache — primary storage is DB (chat_session_service)
# This dict acts as a write-through cache to avoid DB round-trips per turn
_chat_history: dict = {}
_HISTORY_MAX_TURNS = 10


async def _load_history(session_id: str, tenant_id: str) -> list:
    """Load from DB, fall back to in-memory cache."""
    if not session_id:
        return []
    if session_id in _chat_history:
        return _chat_history[session_id]
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(_q(
                "SELECT messages FROM chat_sessions WHERE session_id=%s AND tenant_id=%s"
            ), session_id, tenant_id)
        if not row:
            return []
        msgs = row["messages"]
        if isinstance(msgs, str):
            msgs = json.loads(msgs)
        if isinstance(msgs, list):
            _chat_history[session_id] = msgs
        return msgs if isinstance(msgs, list) else []
    except Exception:
        return []


async def _save_history(session_id: str, tenant_id: str, messages: list, role: str = None) -> None:
    """Write-through: update cache + persist to DB."""
    if not session_id:
        return
    trimmed = messages[-(2 * _HISTORY_MAX_TURNS):]
    _chat_history[session_id] = trimmed
    try:
        async with get_conn() as conn:
            await conn.execute(_q("""
                INSERT INTO chat_sessions (session_id, tenant_id, role, messages, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (session_id, tenant_id)
                DO UPDATE SET
                    messages   = EXCLUDED.messages,
                    role       = COALESCE(EXCLUDED.role, chat_sessions.role),
                    updated_at = NOW()
            """), session_id, tenant_id, role, json.dumps(trimmed, ensure_ascii=False))
    except Exception as e:
        logger.warning("save_history failed: %s", e)


async def chat_with_claude(
    message: str,
    context: str = "",
    tenant_id: str = "default",
    role: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Optional[str]:
    """Claude as main Bridge Hub chat brain with conversation history."""
    try:
        from anthropic import AsyncAnthropic
        from app.api.services.prompt_profiles import get_profile

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured")

        client = AsyncAnthropic(api_key=api_key)
        profile = get_profile(role)
        system = profile["system"]
        max_tokens = profile.get("max_tokens", 4096)

        user_text = message
        if context:
            user_text = (
                f"REAL SYSTEM DATA (DO NOT INVENT):\n{context}\n\n"
                f"---\nUSER QUESTION:\n{message}"
            )

        history = await _load_history(session_id, tenant_id) if session_id else []
        messages = history + [{"role": "user", "content": user_text}]

        model_id = "claude-3-5-sonnet-20241022"
        resp = await client.messages.create(
            model=model_id, max_tokens=max_tokens, system=system, messages=messages,
        )

        await _log_cost(tenant_id, model_id,
                        getattr(resp.usage, "input_tokens", 0),
                        getattr(resp.usage, "output_tokens", 0))

        content = getattr(resp, "content", None) or []
        if not content:
            return None
        answer = (getattr(content[0], "text", "") or "").strip() or None

        if answer and session_id:
            await _save_history(session_id, tenant_id, history + [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": answer},
            ], role=role)

        return answer

    except Exception as e:
        logger.error("claude chat error: %s", e)
        return None


_ACTIONS_SUFFIX = """

RESPONSE FORMAT (always):
Return a JSON object:
{
  "answer": "..ქართული პასუხი..",
  "suggested_actions": [
    {
      "action": "approve_draft",
      "label": "✅ დაამტკიცე draft #1130",
      "route": "/api/approval/approve/1130",
      "method": "POST",
      "params": {"draft_id": 1130}
    }
  ]
}

suggested_actions rules:
- Include 0–3 relevant actions based on context
- Use ONLY these action types: approve_draft, reject_draft, view_draft,
  create_invoice, view_report, sync_bank, export_1c, post_balance_ge,
  view_audit, open_payroll
- If no action is relevant, return empty array []
- Never invent draft IDs or amounts not present in REAL SYSTEM CONTEXT
"""


async def chat_with_claude_structured(
    message: str,
    context: str = "",
    tenant_id: str = "default",
    role: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """
    Claude returns structured {answer, suggested_actions}.
    Falls back to plain text answer with empty actions on parse error.
    """
    try:
        from anthropic import AsyncAnthropic
        from app.api.services.prompt_profiles import get_profile

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured")

        client = AsyncAnthropic(api_key=api_key)
        profile = get_profile(role)
        system = profile["system"] + _ACTIONS_SUFFIX
        max_tokens = profile.get("max_tokens", 4096)

        user_text = message
        if context:
            user_text = (
                f"REAL SYSTEM DATA (DO NOT INVENT):\n{context}\n\n"
                f"---\nUSER QUESTION:\n{message}"
            )

        history = await _load_history(session_id, tenant_id) if session_id else []
        messages = history + [{"role": "user", "content": user_text}]

        model_id = "claude-sonnet-4-6"
        resp = await client.messages.create(
            model=model_id, max_tokens=max_tokens, system=system, messages=messages,
        )

        await _log_cost(tenant_id, model_id,
                        getattr(resp.usage, "input_tokens", 0),
                        getattr(resp.usage, "output_tokens", 0))

        raw = (getattr(resp.content[0], "text", "") or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        if raw.endswith("```"):
            raw = raw[:-3].strip()

        data = json.loads(raw)
        answer = str(data.get("answer", "")).strip()
        actions = data.get("suggested_actions", [])
        if not isinstance(actions, list):
            actions = []

        if answer and session_id:
            await _save_history(session_id, tenant_id, history + [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": answer},
            ], role=role)

        return {"answer": answer, "suggested_actions": actions}

    except (json.JSONDecodeError, KeyError, IndexError):
        plain = await chat_with_claude(message, context=context, tenant_id=tenant_id,
                                       role=role, session_id=session_id)
        return {"answer": plain or "", "suggested_actions": []}
    except Exception as e:
        logger.error("chat_with_claude_structured error: %s", e)
        return {"answer": "", "suggested_actions": []}


def analyze_error(error_text: str, context: dict, tenant_id: str = "default") -> str:
    try:
        from google import genai

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Balance.ge შეცდომა: {error_text}\nახსენი ქართულად 2 წინადადებით.",
        )
        _fire_log_cost(tenant_id, "gemini-2.5-flash", len(error_text) // 4, len(resp.text) // 4)
        return resp.text.strip()
    except Exception:
        return f"შეცდომა: {error_text}"


def analyze_correction(
    original: str,
    corrected: str,
    description: str,
    tenant_id: str = "default",
) -> dict:
    try:
        from google import genai

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        prompt = (
            f"კორექცია: '{description}' — {original}  {corrected}. "
            f'JSON: {{"pattern_keyword":"...","confidence_boost":0.1}}'
        )
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        text = resp.text.strip().replace("```json", "").replace("```", "")
        data = json.loads(text)
        return {
            "pattern_keyword": data.get("pattern_keyword", description[:30]),
            "confidence_boost": float(data.get("confidence_boost", 0.1)),
        }
    except Exception:
        return {
            "pattern_keyword": description[:30],
            "confidence_boost": 0.1,
        }


async def get_cost_summary(tenant_id: str, days: int = 30) -> dict:
    try:
        async with get_conn() as conn:
            rows = await conn.fetch(_q("""
                SELECT model, COUNT(*) calls, SUM(cost_usd) total_cost_usd
                FROM llm_cost_log
                WHERE tenant_id = %s
                  AND created_at >= NOW() - INTERVAL '%s days'
                GROUP BY model
                ORDER BY total_cost_usd DESC
            """), tenant_id, days)
        total = sum(float(r["total_cost_usd"] or 0) for r in rows)
        return {
            "tenant_id": tenant_id, "days": days,
            "total": round(total, 6),
            "by_model": [dict(r) for r in rows],
        }
    except Exception as e:
        return {"tenant_id": tenant_id, "error": str(e)}


def clear_cache():
    global _cache
    _cache = {}
    logger.info("LLM cache cleared")
