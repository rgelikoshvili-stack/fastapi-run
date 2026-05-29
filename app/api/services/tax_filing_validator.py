"""app/api/services/tax_filing_validator.py — Tax filing-grade validation (Task 12E).

Pure functions that validate journal drafts before posting.  No DB access.

Validation rules:
  1. Balance      — sum(debit) == sum(credit) within 0.005 tolerance
  2. Account codes — each code exists in UNIFIED_ACCOUNTS values
  3. VAT direction — account 3310 (vat_payable) must be credit-only;
                     account 3311 (vat_input) must be debit-only
  4. CIT math      — if 3340 (cit_payable) is present, verify gross-up
                     matches 15/85 ratio (tolerance 0.05 GEL)
  5. VAT math      — if 3310 is present, verify an 18% relationship exists
                     between a revenue/receivable line and the VAT line
  6. No zero lines — journal lines with debit==0 AND credit==0 are rejected
"""
from __future__ import annotations

from typing import Any

from app.api.services.accounting_rules_core import UNIFIED_ACCOUNTS

# All valid account codes (values of UNIFIED_ACCOUNTS)
_VALID_CODES: frozenset[str] = frozenset(UNIFIED_ACCOUNTS.values())

# Georgian tax rates
VAT_RATE      = 0.18
CIT_RATE      = 0.15          # on distributed profit (gross-up: profit / 0.85 * 0.15)
CIT_DIVISOR   = 1 - CIT_RATE  # 0.85

# Accounts with strict direction rules
_CREDIT_ONLY_ACCOUNTS = {"3310"}   # vat_payable  — always a credit
_DEBIT_ONLY_ACCOUNTS  = {"3311"}   # vat_input    — always a debit


# ---------------------------------------------------------------------------
# Individual rule checkers (each returns a list of error dicts)
# ---------------------------------------------------------------------------

def check_balance(lines: list[dict]) -> list[dict]:
    """Rule 1 — debit total must equal credit total."""
    total_d = sum(float(l.get("debit",  0)) for l in lines)
    total_c = sum(float(l.get("credit", 0)) for l in lines)
    if abs(total_d - total_c) > 0.005:
        return [{"rule": "BALANCE", "message":
                 f"Journal is unbalanced: debit={total_d:.2f} credit={total_c:.2f} "
                 f"difference={abs(total_d-total_c):.4f}"}]
    return []


def check_account_codes(lines: list[dict]) -> list[dict]:
    """Rule 2 — every account_code must exist in UNIFIED_ACCOUNTS values."""
    errors = []
    for i, line in enumerate(lines):
        code = str(line.get("account_code", "")).strip()
        if not code:
            errors.append({"rule": "ACCOUNT_CODE", "line": i,
                            "message": "account_code is blank"})
        elif code not in _VALID_CODES:
            errors.append({"rule": "ACCOUNT_CODE", "line": i, "account_code": code,
                            "message": f"Unknown account code: {code}"})
    return errors


def check_vat_direction(lines: list[dict]) -> list[dict]:
    """Rule 3 — 3310 must only appear as credit; 3311 must only appear as debit."""
    errors = []
    for i, line in enumerate(lines):
        code   = str(line.get("account_code", "")).strip()
        debit  = float(line.get("debit",  0))
        credit = float(line.get("credit", 0))

        if code in _CREDIT_ONLY_ACCOUNTS and debit > 0:
            errors.append({"rule": "VAT_DIRECTION", "line": i, "account_code": code,
                            "message": f"Account {code} (VAT payable) must be credit-only; found debit={debit}"})
        if code in _DEBIT_ONLY_ACCOUNTS and credit > 0:
            errors.append({"rule": "VAT_DIRECTION", "line": i, "account_code": code,
                            "message": f"Account {code} (VAT input) must be debit-only; found credit={credit}"})
    return errors


def check_cit_math(lines: list[dict]) -> list[dict]:
    """Rule 4 — if 3340 (cit_payable) is present, verify 15/85 gross-up ratio.

    Expected: cit_amount = gross_profit * 0.15 / 0.85
    Tolerance: 0.05 GEL
    """
    cit_lines = [l for l in lines if str(l.get("account_code", "")) == "3340"]
    if not cit_lines:
        return []

    # Find dividend payable (3370) credit as proxy for gross profit base
    dividend_lines = [l for l in lines if str(l.get("account_code", "")) == "3370"]
    if not dividend_lines:
        return []

    cit_amount    = sum(float(l.get("credit", 0)) for l in cit_lines)
    dividend_base = sum(float(l.get("credit", 0)) for l in dividend_lines)

    if dividend_base <= 0:
        return []

    expected_cit = round(dividend_base / CIT_DIVISOR * CIT_RATE, 2)
    if abs(cit_amount - expected_cit) > 0.05:
        return [{"rule": "CIT_MATH", "message":
                 f"CIT amount {cit_amount:.2f} does not match expected {expected_cit:.2f} "
                 f"(15/85 gross-up on dividend base {dividend_base:.2f})"}]
    return []


def check_vat_math(lines: list[dict]) -> list[dict]:
    """Rule 5 — if 3310 is present, verify that VAT = revenue * 0.18 (tolerance 0.05 GEL).

    Looks for a revenue account (6110 or 6120) credit and a 3310 credit.
    """
    vat_lines = [l for l in lines if str(l.get("account_code", "")) == "3310"]
    if not vat_lines:
        return []

    revenue_lines = [
        l for l in lines
        if str(l.get("account_code", "")) in {"6110", "6120"}
    ]
    if not revenue_lines:
        return []

    vat_amount     = sum(float(l.get("credit", 0)) for l in vat_lines)
    revenue_amount = sum(float(l.get("credit", 0)) for l in revenue_lines)

    if revenue_amount <= 0:
        return []

    expected_vat = round(revenue_amount * VAT_RATE, 2)
    if abs(vat_amount - expected_vat) > 0.05:
        return [{"rule": "VAT_MATH", "message":
                 f"VAT amount {vat_amount:.2f} does not match expected {expected_vat:.2f} "
                 f"(18% of revenue {revenue_amount:.2f})"}]
    return []


def check_no_zero_lines(lines: list[dict]) -> list[dict]:
    """Rule 6 — lines with both debit=0 and credit=0 are rejected."""
    errors = []
    for i, line in enumerate(lines):
        if float(line.get("debit", 0)) == 0 and float(line.get("credit", 0)) == 0:
            errors.append({"rule": "ZERO_LINE", "line": i,
                            "message": "Journal line has debit=0 and credit=0"})
    return errors


# ---------------------------------------------------------------------------
# Composite validator
# ---------------------------------------------------------------------------

def validate_journal(lines: list[dict]) -> dict[str, Any]:
    """Run all validation rules and return a structured result.

    Return shape:
        {
          "valid": bool,
          "error_count": int,
          "errors": [{"rule": str, "message": str, ...}, ...],
          "warnings": [],
          "line_count": int,
          "total_debit": float,
          "total_credit": float,
        }
    """
    errors: list[dict] = []
    errors += check_balance(lines)
    errors += check_account_codes(lines)
    errors += check_vat_direction(lines)
    errors += check_cit_math(lines)
    errors += check_vat_math(lines)
    errors += check_no_zero_lines(lines)

    total_d = round(sum(float(l.get("debit",  0)) for l in lines), 2)
    total_c = round(sum(float(l.get("credit", 0)) for l in lines), 2)

    return {
        "valid":        len(errors) == 0,
        "error_count":  len(errors),
        "errors":       errors,
        "warnings":     [],
        "line_count":   len(lines),
        "total_debit":  total_d,
        "total_credit": total_c,
    }
