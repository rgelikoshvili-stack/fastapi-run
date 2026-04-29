"""app/api/services/taxation_engine.py
Georgian tax calculation engine for document-triggered journal entries.

Rates (2024–2025):
  PIT   — 20% (income tax for individuals / sole traders)
  PAYG  —  2% (pension employer contribution, საპენსიო დამსაქმებლის)
  Emp.  —  2% (pension employee contribution, საპენსიო დასაქმებულის)
  VAT   — 18% standard (0% exempt)
  CIT   — 15% on distributed profit (distributed profit = profit / 0.85)
  Div   —  5% withholding on dividends
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

# ── Georgian tax rates ───────────────────────────────────────────────────────
PIT_RATE         = Decimal("0.20")
PAYG_EMPLOYER    = Decimal("0.02")   # employer pension contrib
PAYG_EMPLOYEE    = Decimal("0.02")   # employee pension contrib
VAT_RATE         = Decimal("0.18")
CIT_RATE         = Decimal("0.15")   # on grossed-up distributed profit
DIVIDEND_WHT     = Decimal("0.05")   # withholding on dividend
ROYALTY_WHT      = Decimal("0.10")
INTEREST_WHT     = Decimal("0.05")


def _d(val) -> Decimal:
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal("0")


def _round2(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ── VAT ─────────────────────────────────────────────────────────────────────

def calculate_vat(amount: Decimal, inclusive: bool = False) -> dict:
    """
    inclusive=False → amount is net, VAT on top
    inclusive=True  → amount already includes VAT, extract it
    """
    amount = _d(amount)
    if inclusive:
        vat_amount = _round2(amount * VAT_RATE / (1 + VAT_RATE))
        net        = _round2(amount - vat_amount)
        total      = amount
    else:
        vat_amount = _round2(amount * VAT_RATE)
        net        = amount
        total      = _round2(amount + vat_amount)

    return {
        "net_amount":  float(net),
        "vat_amount":  float(vat_amount),
        "total":       float(total),
        "vat_rate":    18,
        "inclusive":   inclusive,
    }


# ── PIT / PAYG (individual / IM service invoice) ────────────────────────────

def calculate_service_pit(gross: Decimal, apply_pension: bool = True) -> dict:
    """
    For ფ.პ. / ი.მ. receiving payment for services.
    Returns amounts to withhold.

    gross = contract invoice amount (already net of VAT)
    """
    gross = _d(gross)

    pit  = _round2(gross * PIT_RATE)

    if apply_pension:
        emp_pension  = _round2(gross * PAYG_EMPLOYEE)
        empr_pension = _round2(gross * PAYG_EMPLOYER)
    else:
        emp_pension  = Decimal("0")
        empr_pension = Decimal("0")

    net_to_person = _round2(gross - pit - emp_pension)
    total_cost    = _round2(gross + empr_pension)

    return {
        "gross":              float(gross),
        "pit":                float(pit),
        "employee_pension":   float(emp_pension),
        "employer_pension":   float(empr_pension),
        "net_to_person":      float(net_to_person),
        "total_employer_cost": float(total_cost),
        # Journal accounts
        "accounts": {
            "expense":            "7120",  # labour / service expense
            "pit_payable":        "3320",  # PIT payable to RS
            "pension_emp_payable":"3380",  # pension employee portion
            "pension_empr_payable":"3380", # pension employer portion (same liability a/c)
            "bank_payment":       "1210",  # cash / bank
        },
    }


# ── Payroll ──────────────────────────────────────────────────────────────────

def calculate_payroll(gross: Decimal, is_resident: bool = True) -> dict:
    """Standard employee payroll calculation."""
    gross = _d(gross)

    pit          = _round2(gross * PIT_RATE) if is_resident else _round2(gross * Decimal("0.20"))
    emp_pension  = _round2(gross * PAYG_EMPLOYEE)
    empr_pension = _round2(gross * PAYG_EMPLOYER)
    net          = _round2(gross - pit - emp_pension)

    return {
        "gross":                  float(gross),
        "pit":                    float(pit),
        "employee_pension":       float(emp_pension),
        "employer_pension":       float(empr_pension),
        "net":                    float(net),
        "total_employer_cost":    float(_round2(gross + empr_pension)),
    }


# ── CIT (Corporate Income Tax) ───────────────────────────────────────────────

def calculate_cit(distributed_profit: Decimal) -> dict:
    """
    Georgian CIT is on distributed profit.
    Tax base = distributed_profit / (1 - 0.15) = profit / 0.85
    """
    distributed = _d(distributed_profit)
    tax_base = _round2(distributed / (1 - CIT_RATE))
    cit = _round2(tax_base * CIT_RATE)

    return {
        "distributed_profit": float(distributed),
        "tax_base":           float(tax_base),
        "cit":                float(cit),
        "net_dividend":       float(_round2(distributed - cit)),
        "accounts": {
            "cit_expense":   "7800",
            "cit_payable":   "3340",
            "retained_earn": "4210",
        },
    }


# ── Dividend withholding ─────────────────────────────────────────────────────

def calculate_dividend_withholding(gross: Decimal) -> dict:
    gross = _d(gross)
    wht   = _round2(gross * DIVIDEND_WHT)
    net   = _round2(gross - wht)
    return {
        "gross_dividend":    float(gross),
        "withholding_tax":   float(wht),
        "net_to_shareholder": float(net),
        "rate":              5,
        "accounts": {
            "dividend_payable": "3370",
            "wht_payable":      "3350",
            "bank":             "1210",
        },
    }


# ── Top-level document tax analysis ─────────────────────────────────────────

def analyse_document_taxes(
    doc_type: str,
    total_amount: Optional[float],
    provider_type: str,          # "fp", "im", "shps", "sp", "npo", "unknown"
    is_our_purchase: bool = True,
    vat_inclusive: bool = False,
) -> dict:
    """
    Given a parsed document, return required tax withholdings and journal hints.

    Returns:
      {
        "requires_pit": bool,
        "requires_vat": bool,
        "pit_detail":   dict | None,
        "vat_detail":   dict | None,
        "warnings":     [str],
      }
    """
    amount = _d(total_amount or 0)
    warnings = []
    pit_detail = None
    vat_detail = None

    requires_pit = provider_type in ("fp", "im") and is_our_purchase
    requires_vat = doc_type in ("tax_invoice", "invoice") and amount > 0

    if requires_pit and amount > 0:
        pit_detail = calculate_service_pit(amount, apply_pension=True)

    if requires_vat and amount > 0:
        vat_detail = calculate_vat(amount, inclusive=vat_inclusive)

    if provider_type == "fp" and amount > 0 and not requires_pit:
        warnings.append("FP provider but not flagged as our purchase — verify PIT withholding")

    if doc_type == "waybill" and provider_type in ("fp", "im"):
        warnings.append("Waybill from individual — ensure tax invoice also received")

    return {
        "requires_pit": requires_pit,
        "requires_vat": requires_vat,
        "pit_detail":   pit_detail,
        "vat_detail":   vat_detail,
        "warnings":     warnings,
    }
