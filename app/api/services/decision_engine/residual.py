"""
decision_engine/residual.py
Residual classification via Claude with retry + deterministic fallback.
"""
import json
import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

# Deterministic fallback rules for residual amounts
_FALLBACK_RULES = [
    (["სატრანსპორტო", "მიტანა", "delivery", "freight", "courier"], "7310", "Transport expense"),
    (["საბანკო", "საკომისიო", "commission", "bank fee", "service fee"], "7510", "Bank/service fee"),
    (["სარეკლამო", "marketing", "advertising", "pr "], "7810", "Marketing expense"),
    (["დღგ", "vat", "tax"], "3330", "VAT payable"),
    (["შეფუთვა", "packaging", "materials", "მასალა"], "7110", "Materials/packaging"),
    (["პრემია", "bonus", "ჯილდო", "reward"], "7221", "Bonus/reward"),
]


def _fallback_classify(description: str, amount: float) -> dict:
    desc_lower = (description or "").lower()
    for keywords, account, label in _FALLBACK_RULES:
        if any(kw in desc_lower for kw in keywords):
            return {
                "account_code": account,
                "explanation": f"Rule-based: {label}",
                "confidence": 0.60,
                "model_used": "fallback",
                "status": "pending_approval",
            }
    # Absolute fallback
    return {
        "account_code": "7990",
        "explanation": "Unclassified residual — manual review required",
        "confidence": 0.40,
        "model_used": "fallback",
        "status": "manual_review",
    }


def classify_residual(
    description: str,
    amount: float,
    context: Optional[dict] = None,
    tenant_id: str = "default",
) -> dict:
    """
    Classify a residual amount using Claude.
    Retries once on JSON parse failure; falls back to deterministic rules.
    """
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        log.info("classify_residual: ANTHROPIC_API_KEY not set — using fallback")
        return _fallback_classify(description, amount)

    ctx_str = ""
    if context:
        if context.get("matched_description"):
            ctx_str += f"\nMatched lines: {context['matched_description']}"
        if context.get("partner"):
            ctx_str += f"\nPartner: {context['partner']}"
        if context.get("invoice_total"):
            ctx_str += f"\nInvoice total: {context['invoice_total']} GEL"

    prompt = (
        f"ინვოისი ან ტრანზაქცია:{ctx_str}\n\n"
        f"დარჩენილი (residual) თანხა: {amount} GEL\n"
        f"აღწერა: {description or 'N/A'}\n\n"
        "დააბრუნე მხოლოდ JSON ობიექტი:\n"
        '{"account_code": "XXXX", "explanation": "...", "confidence": 0.0-1.0}'
    )

    for attempt in range(2):
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=256,
                temperature=0.0,
                system=(
                    "შენ ხარ ქართული ბუღალტრული AI. "
                    "დააბრუნე მხოლოდ valid JSON, სხვა ტექსტი — არა. "
                    "account_code = 4-ნიშნა საბუღალტრო კოდი. "
                    "confidence = 0.0-1.0."
                ),
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()

            # Strip markdown code fences if present
            raw = raw.strip("` \n")
            if raw.startswith("json"):
                raw = raw[4:]

            data = json.loads(raw)
            account_code = str(data.get("account_code") or "").strip()
            confidence = float(data.get("confidence") or 0.5)

            if not account_code:
                raise ValueError("missing account_code")

            return {
                "account_code": account_code,
                "explanation": data.get("explanation") or "",
                "confidence": confidence,
                "model_used": "claude-sonnet-4-6",
                "status": "pending_approval" if confidence >= 0.70 else "manual_review",
            }

        except json.JSONDecodeError as e:
            log.warning("classify_residual attempt %d JSON parse failed: %s", attempt + 1, e)
        except Exception as e:
            log.warning("classify_residual attempt %d error: %s", attempt + 1, e)
            break  # Don't retry non-JSON errors

    log.info("classify_residual: all attempts failed, using fallback")
    return _fallback_classify(description, amount)


def gemini_validate(draft_lines: list[dict], context: dict) -> dict:
    """
    Gemini validation for low-confidence / mismatch cases.
    Falls back to ok=True if GEMINI_API_KEY not set.
    """
    api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return {"ok": True, "issues": [], "model_used": "stub"}

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        lines_summary = "\n".join(
            f"- {l.get('description','?')}: {l.get('amount',0)} GEL → account {l.get('account_code','?')} (conf={l.get('confidence',0):.2f})"
            for l in draft_lines
        )
        prompt = (
            f"Review these accounting journal entries:\n{lines_summary}\n"
            f"Context: {context.get('explanation','')}\n"
            "Return JSON: {\"ok\": true/false, \"issues\": [\"...\"]}"
        )

        resp = model.generate_content(prompt)
        raw = resp.text.strip().strip("`").strip()
        if raw.startswith("json"):
            raw = raw[4:]
        data = json.loads(raw)
        return {
            "ok": bool(data.get("ok", True)),
            "issues": data.get("issues") or [],
            "model_used": "gemini-2.5-flash",
        }
    except Exception as e:
        log.warning("gemini_validate failed: %s", e)
        return {"ok": True, "issues": [f"gemini_error: {str(e)}"], "model_used": "stub"}
