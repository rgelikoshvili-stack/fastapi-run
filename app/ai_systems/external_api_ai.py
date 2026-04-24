"""
app/ai_systems/external_api_ai.py
Bridge Hub — External API AI (Phase 5)

Responsibilities:
  1. Pre-posting validation  — AI checks journal entries before Balance.ge / 1C
  2. Error analysis          — interprets Balance.ge / RS.GE error messages
  3. Human gate assessment   — decides if human approval is required
  4. Correction suggestions  — tells the human what to fix and why

Architecture rule: this module NEVER calls external APIs directly.
It wraps posting_service.py and routes_balance_ge.py — no duplication.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Risk thresholds for human gate
# ─────────────────────────────────────────────────────────────
_HIGH_VALUE_THRESHOLD = 50_000      # GEL — always requires human
_LOW_CONFIDENCE_THRESHOLD = 0.75    # below this → human review
_ALWAYS_HUMAN_TARGETS = {"oris"}    # RS.GE always needs human


# ─────────────────────────────────────────────────────────────
# Human Gate Assessment (no LLM needed — rule-based is reliable)
# ─────────────────────────────────────────────────────────────

def assess_human_gate(draft: dict, target: str) -> dict:
    """
    Decide if external posting needs human approval.

    Returns:
        {
          "requires_human": bool,
          "reasons": [str],
          "risk_level": "low" | "medium" | "high",
          "auto_proceed": bool,
        }
    """
    reasons = []
    risk_score = 0

    amount = float(draft.get("amount") or 0)
    confidence = float(draft.get("confidence_score") or 1.0)
    status = str(draft.get("status", ""))
    target_norm = target.lower().strip()

    # Rule 1 — RS.GE always requires human
    if target_norm in _ALWAYS_HUMAN_TARGETS:
        reasons.append(f"RS.GE posting always requires human approval")
        risk_score += 3

    # Rule 2 — high value
    if amount >= _HIGH_VALUE_THRESHOLD:
        reasons.append(f"High value transaction: {amount:,.2f} GEL ≥ {_HIGH_VALUE_THRESHOLD:,}")
        risk_score += 2

    # Rule 3 — low AI confidence
    if confidence < _LOW_CONFIDENCE_THRESHOLD:
        reasons.append(f"Low AI confidence: {confidence:.0%} < {_LOW_CONFIDENCE_THRESHOLD:.0%}")
        risk_score += 2

    # Rule 4 — not approved yet
    if status != "approved":
        reasons.append(f"Draft status is '{status}', not 'approved'")
        risk_score += 3

    # Rule 5 — validation errors present
    if draft.get("validation_errors"):
        reasons.append("Draft has validation errors")
        risk_score += 2

    risk_level = "low" if risk_score == 0 else ("medium" if risk_score <= 2 else "high")
    requires_human = risk_score >= 2

    return {
        "requires_human": requires_human,
        "reasons": reasons,
        "risk_level": risk_level,
        "auto_proceed": not requires_human,
        "risk_score": risk_score,
    }


# ─────────────────────────────────────────────────────────────
# Pre-posting Validation (AI-powered)
# ─────────────────────────────────────────────────────────────

def validate_before_posting(draft: dict, target: str, tenant_id: str = "default") -> dict:
    """
    AI validates journal entry before sending to external system.

    Returns:
        {
          "valid": bool,
          "issues": [str],
          "corrected_draft": dict | None,
          "confidence": float,
          "source": "ai" | "rules",
        }
    """
    issues = []

    # Fast rule-based checks (always run first)
    amount = float(draft.get("amount") or 0)
    if amount <= 0:
        issues.append("Amount must be positive")

    dr = draft.get("debit_account") or draft.get("dr_account")
    cr = draft.get("credit_account") or draft.get("cr_account")
    if not dr:
        issues.append("Missing debit account")
    if not cr:
        issues.append("Missing credit account")
    if dr and cr and dr == cr:
        issues.append(f"Debit and credit accounts are identical: {dr}")
    if not draft.get("description"):
        issues.append("Missing description")

    # If basic checks fail — return immediately, no need for LLM
    if len(issues) >= 2:
        return {
            "valid": False,
            "issues": issues,
            "corrected_draft": None,
            "confidence": 0.0,
            "source": "rules",
        }

    # AI validation for semantic correctness
    ai_result = _ai_validate(draft, target, tenant_id)
    if ai_result:
        issues.extend(ai_result.get("issues", []))
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "corrected_draft": ai_result.get("corrected_draft"),
            "confidence": ai_result.get("confidence", 0.9),
            "source": "ai",
        }

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "corrected_draft": None,
        "confidence": 0.85,
        "source": "rules",
    }


def _ai_validate(draft: dict, target: str, tenant_id: str) -> Optional[dict]:
    """Claude validates the journal entry semantically."""
    try:
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None

        client = anthropic.Anthropic(api_key=api_key)

        system = (
            "შენ ხარ Bridge Hub-ის External API Validator.\n"
            "შეამოწმე journal entry-ი posting-მდე.\n"
            "გადასახადის განაკვეთები: VAT 18%, PIT 20%, PAYG 2%, CIT 15%\n"
            "COA: 1xxx=asset, 3xxx=liability, 4xxx=equity, 6xxx=revenue, 7xxx=expense\n\n"
            "დააბრუნე JSON:\n"
            '{"issues": ["..."], "corrected_draft": null_or_dict, "confidence": 0.95, "notes": "..."}'
        )

        user_msg = (
            f"Target: {target}\n"
            f"Description: {draft.get('description')}\n"
            f"Amount: {draft.get('amount')} GEL\n"
            f"Debit: {draft.get('debit_account') or draft.get('dr_account')}\n"
            f"Credit: {draft.get('credit_account') or draft.get('cr_account')}\n"
            f"Partner: {draft.get('partner', '')}\n\n"
            "Validate and return JSON:"
        )

        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )

        raw = (resp.content[0].text or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        data = json.loads(raw.strip())
        return data

    except Exception as e:
        log.debug("ai_validate failed: %s", e)
        return None


# ─────────────────────────────────────────────────────────────
# Error Analysis (AI interprets Balance.ge / 1C error messages)
# ─────────────────────────────────────────────────────────────

def analyze_posting_error(error_text: str, draft: dict, target: str, tenant_id: str = "default") -> dict:
    """
    AI interprets a posting error and suggests a human-readable fix.

    Returns:
        {
          "georgian_explanation": str,
          "suggested_fix": str,
          "can_auto_retry": bool,
          "retry_changes": dict | None,
        }
    """
    if not error_text:
        return {
            "georgian_explanation": "უცნობი შეცდომა",
            "suggested_fix": "გადაამოწმე კავშირი და სცადე თავიდან",
            "can_auto_retry": False,
            "retry_changes": None,
        }

    try:
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return _fallback_error_analysis(error_text)

        client = anthropic.Anthropic(api_key=api_key)

        system = (
            "შენ ხარ Bridge Hub-ის Error Analyst.\n"
            "გაანალიზე Balance.ge / 1C / RS.GE შეცდომის შეტყობინება.\n"
            "ახსენი ქართულად მარტივად. მიეცი კონკრეტული გამოსწორება.\n\n"
            "JSON format:\n"
            '{"georgian_explanation": "...", "suggested_fix": "...", '
            '"can_auto_retry": false, "retry_changes": null}'
        )

        user_msg = (
            f"External system: {target}\n"
            f"Error: {error_text[:500]}\n"
            f"Draft: {draft.get('description')} | {draft.get('amount')} GEL\n"
            f"Dr: {draft.get('debit_account')} Cr: {draft.get('credit_account')}\n\n"
            "Analyze and return JSON:"
        )

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
        log.debug("analyze_posting_error failed: %s", e)
        return _fallback_error_analysis(error_text)


def _fallback_error_analysis(error_text: str) -> dict:
    """Rule-based error interpretation when LLM unavailable."""
    err_lower = error_text.lower()
    if "auth" in err_lower or "401" in err_lower or "403" in err_lower:
        fix = "API Key შეამოწმე — Balance.ge credentials განახლება საჭიროა"
    elif "duplicate" in err_lower or "already" in err_lower:
        fix = "ეს გატარება უკვე გაგზავნილია — duplicate posting"
    elif "account" in err_lower or "code" in err_lower:
        fix = "ანგარიშის კოდი არასწორია — COA-ში შეამოწმე"
    elif "amount" in err_lower or "value" in err_lower:
        fix = "თანხა არასწორი ფორმატია — 2 ათობითი ადგილი"
    elif "timeout" in err_lower or "connect" in err_lower:
        fix = "კავშირის პრობლემა — ცოტა შემდეგ სცადე"
    else:
        fix = "ხელით გადაამოწმე და სცადე თავიდან"

    return {
        "georgian_explanation": f"გარე სისტემის შეცდომა: {error_text[:200]}",
        "suggested_fix": fix,
        "can_auto_retry": "timeout" in err_lower or "connect" in err_lower,
        "retry_changes": None,
    }
