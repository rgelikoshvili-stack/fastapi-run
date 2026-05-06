"""
Bridge Hub — Accounting Rules: Core Utilities
app/api/services/accounting_rules_core.py

Sections 0-3: account mapping, formatting, helpers, tax math.
"""
from __future__ import annotations

from datetime import date as dt
from typing import Optional, List, Dict, Any


# ═══════════════════════════════════════════════════════
# 0. UNIFIED ACCOUNT MAPPING
# ═══════════════════════════════════════════════════════

UNIFIED_ACCOUNTS = {
    "cash": "1110",
    "bank": "1120",
    "receivable_trade": "1210",
    "inventory": "1310",
    "prepaid_expense": "1430",
    "fixed_asset": "1510",
    "accumulated_depreciation": "1520",
    "intangible_asset": "1610",
    "accounts_payable": "3110",
    "customer_advance": "3120",
    "vat_payable": "3310",
    "vat_input": "3311",
    "pit_payable": "3320",
    "employee_pension_payable": "3330",
    "employer_pension_payable": "3335",
    "cit_payable": "3340",
    "withholding_payable": "3350",
    "net_salary_payable": "3360",
    "dividend_payable": "3370",
    "property_tax_payable": "3380",
    "loan_payable": "3410",
    "lease_liability": "3430",
    "share_capital": "4110",
    "retained_earnings": "4210",
    "sales_revenue": "6110",
    "service_revenue": "6120",
    "cogs": "7110",
    "salary_expense": "7210",
    "employer_pension_expense": "7220",
    "rent_expense": "7310",
    "utilities_expense": "7410",
    "bank_fee_expense": "7510",
    "interest_expense": "7520",
    "depreciation_expense": "7610",
    "marketing_expense": "7710",
    "representative_expense": "7720",
    "other_expense": "7910",
    "profit_tax_expense": "9210",
}


# ═══════════════════════════════════════════════════════
# 1. FORMAT
# ═══════════════════════════════════════════════════════

def format_gel(amount: float) -> str:
    """10000 -> 10,000.00₾"""
    return f"{float(amount):,.2f}₾"


# ═══════════════════════════════════════════════════════
# 2. HELPERS
# ═══════════════════════════════════════════════════════

def _round2(value: float) -> float:
    return round(float(value), 2)


def _make_line(account_code: str, label: str, debit: float = 0.0, credit: float = 0.0) -> dict:
    return {
        "account_code": str(account_code),
        "label": label,
        "debit": _round2(debit),
        "credit": _round2(credit),
    }


def _format_lines(lines: List[dict]) -> str:
    rows = []
    for line in lines:
        if line["debit"] > 0:
            rows.append(
                f"  Dr {line['account_code']} {line['label']:<30} {format_gel(line['debit']):>14}"
            )
        else:
            rows.append(
                f"  Cr {line['account_code']} {line['label']:<30} {format_gel(line['credit']):>14}"
            )
    return "\n".join(rows)


def _to_balance_ge(lines: List[dict], description: str = "", journal_date: Optional[str] = None) -> dict:
    return {
        "journal_date": journal_date or dt.today().isoformat(),
        "description": description,
        "lines": [
            {
                "account_code": line["account_code"],
                "debit": _round2(line["debit"]),
                "credit": _round2(line["credit"]),
            }
            for line in lines
        ],
    }


def _posting_result(
    posting_type: str,
    lines: List[dict],
    description: str,
    calculation: Optional[Dict[str, Any]] = None,
) -> dict:
    result = {
        "type": posting_type,
        "lines": lines,
        "human_readable": _format_lines(lines),
        "balance_ge_payload": _to_balance_ge(lines, description=description),
    }
    if calculation:
        result.update(calculation)
    return result


# ═══════════════════════════════════════════════════════
# 3. TAX CALC HELPERS
# ═══════════════════════════════════════════════════════

def split_vat_from_gross(gross_amount: float, vat_rate: float = 0.18) -> dict:
    gross = _round2(gross_amount)
    net = _round2(gross / (1 + vat_rate))
    vat = _round2(gross - net)
    return {"gross": gross, "net": net, "vat": vat, "vat_rate": vat_rate}


def add_vat_to_net(net_amount: float, vat_rate: float = 0.18) -> dict:
    net = _round2(net_amount)
    vat = _round2(net * vat_rate)
    gross = _round2(net + vat)
    return {"gross": gross, "net": net, "vat": vat, "vat_rate": vat_rate}


def estonian_cit_from_distributed_amount(
    amount: float, cit_rate: float = 0.15, divisor: float = 0.85
) -> dict:
    amount = _round2(amount)
    tax_base = _round2(amount / divisor)
    cit = _round2(tax_base * cit_rate)
    net_after_cit = _round2(amount - cit)
    return {
        "amount": amount,
        "tax_base": tax_base,
        "cit": cit,
        "net_after_cit": net_after_cit,
        "cit_rate": cit_rate,
        "divisor": divisor,
    }


def gross_up_salary_from_net(
    net_amount: float, pit_rate: float = 0.20, employee_pension_rate: float = 0.02
) -> dict:
    net_amount = _round2(net_amount)
    gross = _round2(net_amount / (1 - pit_rate - employee_pension_rate))
    pit = _round2(gross * pit_rate)
    employee_pension = _round2(gross * employee_pension_rate)
    return {"gross": gross, "pit": pit, "employee_pension": employee_pension, "net": net_amount}


def calculate_pension_components(
    gross_salary: float, employee_rate: float = 0.02, employer_rate: float = 0.02
) -> dict:
    gross_salary = _round2(gross_salary)
    return {
        "gross": gross_salary,
        "employee_pension": _round2(gross_salary * employee_rate),
        "employer_pension": _round2(gross_salary * employer_rate),
        "employee_rate": employee_rate,
        "employer_rate": employer_rate,
    }


def calculate_withholding_tax(amount: float, rate: float) -> dict:
    amount = _round2(amount)
    tax = _round2(amount * rate)
    return {"gross": amount, "tax": tax, "net": _round2(amount - tax), "rate": rate}


def calculate_property_tax(tax_base: float, rate: float) -> dict:
    tax_base = _round2(tax_base)
    return {"tax_base": tax_base, "rate": rate, "tax": _round2(tax_base * rate)}
