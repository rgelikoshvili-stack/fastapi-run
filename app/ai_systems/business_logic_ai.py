"""
app/ai_systems/business_logic_ai.py
Bridge Hub — AI-First Business Logic Engine

Architecture:
  Input  → transaction description + amount + type + context
  AI     → Claude generates Dr/Cr journal entries (COA codes)
  Validate → debits == credits (±0.01 tolerance)
  Fallback → accounting_rules.py hardcoded builders
  Output → journal_lines + confidence + source
"""
from __future__ import annotations

import json
import logging
from typing import Optional

log = logging.getLogger(__name__)

# Re-use existing knowledge — no duplication
from app.knowledge.chart_of_accounts import CHART_OF_ACCOUNTS, TAX_RATES
from app.knowledge.tax_rules import (
    calculate_vat,
    calculate_payroll,
    calculate_cit,
    calculate_withholding,
)

# Re-use existing accounting rules as fallback — no duplication
from app.api.services.accounting_rules import (
    UNIFIED_ACCOUNTS,
    build_vat_posting,
    build_vat_posting_from_net,
    build_payroll_posting,
    build_payroll_from_net_posting,
    build_cit_posting,
    build_dividend_posting,
    build_bank_fee_posting,
    build_expense_posting,
    build_simple_revenue_posting,
    build_depreciation_posting,
)

# ─────────────────────────────────────────────────────────────
# COA context for LLM (compact — top accounts only)
# ─────────────────────────────────────────────────────────────
_COA_SUMMARY = "\n".join(
    f"{code}: {info['name']} ({info['type']})"
    for code, info in CHART_OF_ACCOUNTS.items()
    if code in {
        "1110","1120","1210","1310","1510","1520",
        "3110","3120","3310","3311","3320","3330","3335",
        "3340","3350","3360","3370",
        "4110","4210",
        "6110","6120",
        "7110","7210","7220","7310","7410","7510","7520",
        "7610","7710","7720","7910","9210",
    }
)

_SYSTEM_PROMPT = f"""შენ ხარ Bridge Hub-ის Business Logic AI.
შენი ერთადერთი ამოცანა: ტრანზაქციისთვის სწორი Dr/Cr ბუღალტრული გატარება.

ქართული COA (Chart of Accounts):
{_COA_SUMMARY}

გადასახადის განაკვეთები:
- VAT: 18%  (inclusive formula: amount / 1.18 = net)
- PIT: 20%  (payroll)
- PAYG employee: 2%,  employer: 2%
- CIT: 15%  (Estonian model — on distributed profit)
- Dividend withholding: 5% (resident), 10% (non-resident)

წესები:
1. გააბალანსე: sum(debit amounts) == sum(credit amounts)
2. გამოიყენე მხოლოდ COA სიიდან კოდები
3. ყოველ line-ს ჰქონდეს: account (4-digit), side (dr/cr), amount (float), description (str)
4. amount-ი ყოველთვის დადებითი
5. დააბრუნე მხოლოდ JSON — არანაირი ახსნა

JSON format:
{{
  "lines": [
    {{"account": "XXXX", "side": "dr", "amount": 0.00, "description": "..."}},
    {{"account": "XXXX", "side": "cr", "amount": 0.00, "description": "..."}}
  ],
  "confidence": 0.95,
  "notes": "optional explanation"
}}"""


# ─────────────────────────────────────────────────────────────
# Fallback map — known types → accounting_rules.py builders
# ─────────────────────────────────────────────────────────────
_FALLBACK_MAP = {
    "vat_purchase":    lambda a, **kw: _lines_from_posting(build_vat_posting(a)),
    "vat_sale":        lambda a, **kw: _lines_from_posting(build_vat_posting_from_net(a)),
    "payroll_gross":   lambda a, **kw: _lines_from_posting(build_payroll_posting(a)),
    "payroll_net":     lambda a, **kw: _lines_from_posting(build_payroll_from_net_posting(a)),
    "cit":             lambda a, **kw: _lines_from_posting(build_cit_posting(a)),
    "dividend":        lambda a, **kw: _lines_from_posting(build_dividend_posting(a)["step1"]),
    "bank_fee":        lambda a, **kw: _lines_from_posting(build_bank_fee_posting(a)),
    "revenue":         lambda a, **kw: _lines_from_posting(build_simple_revenue_posting(a)),
    "depreciation":    lambda a, **kw: _lines_from_posting(build_depreciation_posting(a)),
    "expense":         lambda a, acc=None, **kw: _lines_from_posting(
                           build_expense_posting(a, account_code=acc or UNIFIED_ACCOUNTS["other_expense"])
                       ),
}


def _lines_from_posting(posting: dict) -> list[dict]:
    """Convert accounting_rules.py posting dict → normalized lines list.

    accounting_rules.py uses: {account_code, label, debit, credit}
    """
    raw_lines = posting.get("lines", [])

    # Also include employer_pension_lines if present
    extra = posting.get("employer_pension_lines", [])
    all_raw = raw_lines + extra

    result = []
    for ln in all_raw:
        code = str(ln.get("account_code") or ln.get("account") or "")
        label = str(ln.get("label") or ln.get("description") or "")
        debit = float(ln.get("debit", 0) or 0)
        credit = float(ln.get("credit", 0) or 0)
        if debit > 0:
            result.append({"account": code, "side": "dr", "amount": debit, "description": label})
        if credit > 0:
            result.append({"account": code, "side": "cr", "amount": credit, "description": label})
    return result


def _validate_balance(lines: list[dict]) -> bool:
    dr_total = sum(l["amount"] for l in lines if l["side"] == "dr")
    cr_total = sum(l["amount"] for l in lines if l["side"] == "cr")
    return abs(dr_total - cr_total) < 0.02


# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────

def generate_journal_entries(
    description: str,
    amount: float,
    transaction_type: Optional[str] = None,
    context: Optional[dict] = None,
    tenant_id: str = "default",
) -> dict:
    """
    AI-first journal entry generator.

    Returns:
        {
          "lines": [{account, side, amount, description}, ...],
          "confidence": float,
          "source": "ai" | "fallback_rules" | "fallback_empty",
          "notes": str,
        }
    """
    context = context or {}
    amount = float(amount or 0)

    # 1. Try known-type fallback first (fast, reliable)
    if transaction_type and transaction_type in _FALLBACK_MAP:
        try:
            acc = context.get("account_code")
            lines = _FALLBACK_MAP[transaction_type](amount, acc=acc)
            if lines and _validate_balance(lines):
                return {
                    "lines": lines,
                    "confidence": 0.97,
                    "source": "fallback_rules",
                    "notes": f"accounting_rules.py → {transaction_type}",
                }
        except Exception as e:
            log.warning("fallback_rules failed for %s: %s", transaction_type, e)

    # 2. AI generation via Claude
    ai_result = _ai_generate(description, amount, transaction_type, context, tenant_id)
    if ai_result:
        return ai_result

    # 3. Last resort — empty skeleton
    log.error("business_logic_ai: all paths failed for '%s'", description)
    return {
        "lines": [],
        "confidence": 0.0,
        "source": "fallback_empty",
        "notes": "Could not generate journal entries",
    }


def _ai_generate(
    description: str,
    amount: float,
    transaction_type: Optional[str],
    context: dict,
    tenant_id: str,
) -> Optional[dict]:
    """Call Claude to generate journal entries."""
    try:
        import anthropic
        import os

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None

        client = anthropic.Anthropic(api_key=api_key)

        user_msg = (
            f"ტრანზაქცია: {description}\n"
            f"თანხა: {amount:.2f} GEL\n"
        )
        if transaction_type:
            user_msg += f"ტიპი: {transaction_type}\n"
        if context.get("partner"):
            user_msg += f"პარტნიორი: {context['partner']}\n"
        if context.get("notes"):
            user_msg += f"შენიშვნა: {context['notes']}\n"
        user_msg += "\nJSON:"

        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )

        raw = (resp.content[0].text or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)
        lines = data.get("lines", [])
        confidence = float(data.get("confidence", 0.85))
        notes = data.get("notes", "")

        if not lines:
            return None

        # Normalize line format
        normalized = []
        for ln in lines:
            normalized.append({
                "account": str(ln.get("account", "")),
                "side": str(ln.get("side", "dr")),
                "amount": float(ln.get("amount", 0)),
                "description": str(ln.get("description", description)),
            })

        if not _validate_balance(normalized):
            log.warning("AI journal not balanced — skipping")
            return None

        # Log cost
        try:
            from app.api.services.llm_service import _log_cost
            _log_cost(
                tenant_id, "claude-sonnet-4-6",
                getattr(resp.usage, "input_tokens", 0),
                getattr(resp.usage, "output_tokens", 0),
            )
        except Exception as e:
            log.warning("unexpected error: %s", e)

        return {
            "lines": normalized,
            "confidence": confidence,
            "source": "ai",
            "notes": notes,
        }

    except json.JSONDecodeError as e:
        log.error("business_logic_ai JSON parse error: %s", e)
        return None
    except Exception as e:
        log.error("business_logic_ai AI error: %s", e)
        return None
