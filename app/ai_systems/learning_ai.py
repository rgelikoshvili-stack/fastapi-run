"""
app/ai_systems/learning_ai.py
Bridge Hub — Learning AI (Phase 5)

Wraps learning_service.py + pattern_decay_service.py — no duplication.
Adds AI layer:
  1. Pattern suggestion — when a correction happens, Claude analyzes WHY
     and suggests a concrete rule for the pattern engine.
  2. Learning health insights — natural language summary of pattern health.
  3. Confidence recommendations — AI flags patterns that should decay faster.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

# Re-use existing services — no duplication
from app.api.services.learning_service import (
    apply_approve_learning,
    apply_reject_learning,
    apply_correct_learning,
)
from app.api.services.pattern_decay_service import get_pattern_health_summary


# ─────────────────────────────────────────────────────────────
# PUBLIC API — drop-in replacements with AI enhancement
# ─────────────────────────────────────────────────────────────

async def learn_from_approval(draft: dict, tenant_id: str = "default") -> dict:
    """Wrap apply_approve_learning — no extra AI needed for approvals."""
    result = await apply_approve_learning(draft, tenant_id)
    return {"base": result, "ai_suggestion": None, "action": "approved"}


async def learn_from_rejection(draft: dict, reason: str, tenant_id: str = "default") -> dict:
    """Wrap apply_reject_learning — no extra AI needed for rejections."""
    result = await apply_reject_learning(draft, reason, tenant_id)
    return {"base": result, "ai_suggestion": None, "action": "rejected"}


async def learn_from_correction(
    original_draft: dict,
    corrected_draft: dict,
    tenant_id: str = "default",
) -> dict:
    """
    Wrap apply_correct_learning + AI pattern suggestion.

    When an accountant corrects a draft, Claude analyzes:
      - What changed (account codes, amount, description)
      - Why it was likely wrong
      - What rule should prevent this in future

    Returns:
        {
          "base": result from apply_correct_learning,
          "ai_suggestion": {
            "pattern_keyword": str,
            "suggested_account": str,
            "rule_explanation": str (Georgian),
            "confidence": float,
          } | None,
          "action": "corrected",
        }
    """
    result = await apply_correct_learning(
        draft=original_draft,
        corrected_account_code=corrected_draft.get("account_code", ""),
        corrected_reason=corrected_draft.get("reason", "manual_correction"),
        corrected_by=corrected_draft.get("corrected_by", "manual_review"),
        tenant_id=tenant_id,
    )
    ai_suggestion = _ai_suggest_pattern(original_draft, corrected_draft, tenant_id)
    return {
        "base": result,
        "ai_suggestion": ai_suggestion,
        "action": "corrected",
    }


def get_learning_insights(tenant_id: str = "default") -> dict:
    """
    Natural language summary of learning health for this tenant.

    Returns:
        {
          "summary": str (Georgian),
          "health_score": float,
          "recommendations": [str],
          "pattern_stats": dict,
        }
    """
    try:
        health = get_pattern_health_summary(tenant_id)
    except Exception as e:
        log.warning("get_pattern_health_summary failed: %s", e)
        health = {}

    ai_insights = _ai_health_insights(health, tenant_id)

    return {
        "summary": ai_insights.get("summary", _fallback_summary(health)),
        "health_score": _compute_health_score(health),
        "recommendations": ai_insights.get("recommendations", []),
        "pattern_stats": health,
    }


# ─────────────────────────────────────────────────────────────
# AI — Pattern suggestion on correction
# ─────────────────────────────────────────────────────────────

def _ai_suggest_pattern(
    original: dict,
    corrected: dict,
    tenant_id: str,
) -> Optional[dict]:
    """Claude analyzes a correction and suggests a reusable pattern rule."""
    orig_dr = original.get("debit_account") or original.get("dr_account", "")
    orig_cr = original.get("credit_account") or original.get("cr_account", "")
    corr_dr = corrected.get("debit_account") or corrected.get("dr_account", "")
    corr_cr = corrected.get("credit_account") or corrected.get("cr_account", "")

    # Only suggest if account codes actually changed
    if orig_dr == corr_dr and orig_cr == corr_cr:
        return None

    try:
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return _fallback_pattern_suggestion(original, corrected)

        client = anthropic.Anthropic(api_key=api_key)

        system = (
            "შენ ხარ Bridge Hub-ის Learning AI.\n"
            "ბუღალტერმა გაასწორა journal entry. გაანალიზე რა შეიცვალა და\n"
            "შემოგვთავაზე კონკრეტული წესი, რომ სამომავლოდ ეს შეცდომა\n"
            "ავტომატურად გამოსწორდეს.\n\n"
            "COA: 1xxx=აქტივი, 3xxx=ვალდებულება, 4xxx=კაპიტალი, 6xxx=შემოსავალი, 7xxx=ხარჯი\n\n"
            "დააბრუნე JSON:\n"
            '{"pattern_keyword": "საძიებო სიტყვა", "suggested_account": "XXXX", '
            '"rule_explanation": "ქართულად: რატომ ეს ანგარიში", "confidence": 0.85}'
        )

        user_msg = (
            f"აღწერა: {original.get('description', '')}\n"
            f"პარტნიორი: {original.get('partner', '')}\n"
            f"თანხა: {original.get('amount', 0)} GEL\n\n"
            f"ძველი: Dr {orig_dr} / Cr {orig_cr}\n"
            f"ახალი: Dr {corr_dr} / Cr {corr_cr}\n\n"
            "რა წესი ამოვიღოთ ამ გასწორებიდან? JSON:"
        )

        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )

        raw = (resp.content[0].text or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        return json.loads(raw.strip())

    except Exception as e:
        log.debug("_ai_suggest_pattern failed: %s", e)
        return _fallback_pattern_suggestion(original, corrected)


def _fallback_pattern_suggestion(original: dict, corrected: dict) -> dict:
    description = original.get("description", "").lower()
    corr_dr = corrected.get("debit_account") or corrected.get("dr_account", "")

    keyword = description.split()[0] if description.split() else "ტრანზაქცია"
    return {
        "pattern_keyword": keyword,
        "suggested_account": corr_dr,
        "rule_explanation": f"გასწორების საფუძველზე: {keyword} → {corr_dr}",
        "confidence": 0.6,
    }


# ─────────────────────────────────────────────────────────────
# AI — Learning health insights
# ─────────────────────────────────────────────────────────────

def _ai_health_insights(health: dict, tenant_id: str) -> dict:
    """Claude generates natural language learning health summary."""
    if not health:
        return {"summary": "სწავლის მონაცემები არ არის.", "recommendations": []}

    try:
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return {"summary": _fallback_summary(health), "recommendations": []}

        client = anthropic.Anthropic(api_key=api_key)

        system = (
            "შენ ხარ Bridge Hub-ის Learning Health Analyst.\n"
            "გააანალიზე AI სწავლის სტატისტიკა და მიეცი კონკრეტური რეკომენდაციები.\n"
            "ახსენი მარტივად, ქართულად.\n\n"
            "JSON format:\n"
            '{"summary": "...", "recommendations": ["...", "..."]}'
        )

        user_msg = f"სწავლის სტატისტიკა:\n{json.dumps(health, ensure_ascii=False, indent=2)}\n\nJSON:"

        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )

        raw = (resp.content[0].text or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        return json.loads(raw.strip())

    except Exception as e:
        log.debug("_ai_health_insights failed: %s", e)
        return {"summary": _fallback_summary(health), "recommendations": []}


def _fallback_summary(health: dict) -> str:
    total = health.get("total_patterns", 0)
    active = health.get("active_patterns", 0)
    decayed = health.get("decayed_patterns", 0)
    if not total:
        return "სწავლის ნიმუშები ჯერ არ არის."
    return (
        f"სულ {total} ნიმუში: {active} აქტიური, {decayed} მოძველებული. "
        f"სისტემა სწავლობს თქვენი კომპანიის ტრანზაქციების ნიმუშებს."
    )


def _compute_health_score(health: dict) -> float:
    total = health.get("total_patterns", 0)
    if not total:
        return 0.0
    active = health.get("active_patterns", 0)
    avg_conf = health.get("avg_confidence", 0.5)
    ratio = active / total if total else 0
    return round((ratio * 0.6 + avg_conf * 0.4), 3)
