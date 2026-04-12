"""
Bridge Hub — Accounting Rules & Formatting
app/api/services/accounting_rules.py

როლი:
- ბუღალტრული გატარებების ძრავა
- human-readable journal ტექსტი
- Balance.ge payload generation
- tax-aware posting templates

Source of truth:
- bridge_hub_knowledge.py → TAX_RATES / CHART_OF_ACCOUNTS / posting standards

არ შეიცავს:
- knowledge file loading
- classify_transaction
- learned rules
- search_knowledge
- raw tax law text
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
    return {
        "gross": gross,
        "net": net,
        "vat": vat,
        "vat_rate": vat_rate,
    }


def add_vat_to_net(net_amount: float, vat_rate: float = 0.18) -> dict:
    net = _round2(net_amount)
    vat = _round2(net * vat_rate)
    gross = _round2(net + vat)
    return {
        "gross": gross,
        "net": net,
        "vat": vat,
        "vat_rate": vat_rate,
    }


def estonian_cit_from_distributed_amount(amount: float, cit_rate: float = 0.15, divisor: float = 0.85) -> dict:
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


def gross_up_salary_from_net(net_amount: float, pit_rate: float = 0.20, employee_pension_rate: float = 0.02) -> dict:
    net_amount = _round2(net_amount)
    gross = _round2(net_amount / (1 - pit_rate - employee_pension_rate))
    pit = _round2(gross * pit_rate)
    employee_pension = _round2(gross * employee_pension_rate)
    return {
        "gross": gross,
        "pit": pit,
        "employee_pension": employee_pension,
        "net": net_amount,
    }


def calculate_pension_components(gross_salary: float, employee_rate: float = 0.02, employer_rate: float = 0.02) -> dict:
    gross_salary = _round2(gross_salary)
    employee_pension = _round2(gross_salary * employee_rate)
    employer_pension = _round2(gross_salary * employer_rate)
    return {
        "gross": gross_salary,
        "employee_pension": employee_pension,
        "employer_pension": employer_pension,
        "employee_rate": employee_rate,
        "employer_rate": employer_rate,
    }


def calculate_withholding_tax(amount: float, rate: float) -> dict:
    amount = _round2(amount)
    tax = _round2(amount * rate)
    net = _round2(amount - tax)
    return {
        "gross": amount,
        "tax": tax,
        "net": net,
        "rate": rate,
    }


def calculate_property_tax(tax_base: float, rate: float) -> dict:
    tax_base = _round2(tax_base)
    tax = _round2(tax_base * rate)
    return {
        "tax_base": tax_base,
        "rate": rate,
        "tax": tax,
    }


# ═══════════════════════════════════════════════════════
# 4. SALES / REVENUE POSTINGS
# ═══════════════════════════════════════════════════════

def build_vat_posting(
    gross_amount: float,
    vat_rate: float = 0.18,
    payment_status: str = "paid",
    revenue_account: str = UNIFIED_ACCOUNTS["sales_revenue"],
    vat_account: str = UNIFIED_ACCOUNTS["vat_payable"],
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
    receivable_account: str = UNIFIED_ACCOUNTS["receivable_trade"],
) -> dict:
    calc = split_vat_from_gross(gross_amount, vat_rate=vat_rate)
    debit_account = bank_account if payment_status == "paid" else receivable_account
    debit_label = "Bank/Cash" if payment_status == "paid" else "Trade Receivable"

    lines = [
        _make_line(debit_account, debit_label, debit=calc["gross"]),
        _make_line(revenue_account, "Revenue", credit=calc["net"]),
        _make_line(vat_account, "VAT Payable", credit=calc["vat"]),
    ]

    return _posting_result(
        "vat_sale",
        lines,
        description=f"VAT sale ({payment_status})",
        calculation={"payment_status": payment_status, **calc},
    )


def build_vat_posting_from_net(
    net_amount: float,
    vat_rate: float = 0.18,
    payment_status: str = "paid",
    revenue_account: str = UNIFIED_ACCOUNTS["sales_revenue"],
    vat_account: str = UNIFIED_ACCOUNTS["vat_payable"],
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
    receivable_account: str = UNIFIED_ACCOUNTS["receivable_trade"],
) -> dict:
    calc = add_vat_to_net(net_amount, vat_rate=vat_rate)
    debit_account = bank_account if payment_status == "paid" else receivable_account
    debit_label = "Bank/Cash" if payment_status == "paid" else "Trade Receivable"

    lines = [
        _make_line(debit_account, debit_label, debit=calc["gross"]),
        _make_line(revenue_account, "Revenue", credit=calc["net"]),
        _make_line(vat_account, "VAT Payable", credit=calc["vat"]),
    ]

    return _posting_result(
        "vat_sale",
        lines,
        description=f"VAT sale from net ({payment_status})",
        calculation={"payment_status": payment_status, **calc},
    )


def build_simple_revenue_posting(
    amount: float,
    payment_status: str = "paid",
    revenue_account: str = UNIFIED_ACCOUNTS["sales_revenue"],
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
    receivable_account: str = UNIFIED_ACCOUNTS["receivable_trade"],
) -> dict:
    amount = _round2(amount)
    debit_account = bank_account if payment_status == "paid" else receivable_account
    debit_label = "Bank/Cash" if payment_status == "paid" else "Trade Receivable"

    lines = [
        _make_line(debit_account, debit_label, debit=amount),
        _make_line(revenue_account, "Revenue", credit=amount),
    ]

    return _posting_result(
        "simple_revenue",
        lines,
        description=f"Simple revenue ({payment_status})",
        calculation={"payment_status": payment_status, "amount": amount},
    )


def build_service_revenue_posting(
    amount: float,
    payment_status: str = "paid",
    revenue_account: str = UNIFIED_ACCOUNTS["service_revenue"],
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
    receivable_account: str = UNIFIED_ACCOUNTS["receivable_trade"],
) -> dict:
    amount = _round2(amount)
    debit_account = bank_account if payment_status == "paid" else receivable_account
    debit_label = "Bank/Cash" if payment_status == "paid" else "Trade Receivable"

    lines = [
        _make_line(debit_account, debit_label, debit=amount),
        _make_line(revenue_account, "Service Revenue", credit=amount),
    ]

    return _posting_result(
        "service_revenue",
        lines,
        description=f"Service revenue ({payment_status})",
        calculation={"payment_status": payment_status, "amount": amount},
    )


def build_export_revenue_posting(
    amount: float,
    payment_status: str = "paid",
    revenue_account: str = UNIFIED_ACCOUNTS["sales_revenue"],
    receivable_account: str = UNIFIED_ACCOUNTS["receivable_trade"],
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
) -> dict:
    amount = _round2(amount)
    debit_account = bank_account if payment_status == "paid" else receivable_account
    debit_label = "Bank/Cash" if payment_status == "paid" else "Trade Receivable"

    lines = [
        _make_line(debit_account, debit_label, debit=amount),
        _make_line(revenue_account, "Export Revenue (0% VAT)", credit=amount),
    ]

    return _posting_result(
        "export_revenue",
        lines,
        description=f"Export revenue ({payment_status})",
        calculation={"payment_status": payment_status, "amount": amount, "vat_rate": 0.0},
    )


def build_customer_advance_posting(
    amount: float,
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
    advance_account: str = UNIFIED_ACCOUNTS["customer_advance"],
) -> dict:
    amount = _round2(amount)
    lines = [
        _make_line(bank_account, "Bank/Cash", debit=amount),
        _make_line(advance_account, "Customer Advance", credit=amount),
    ]
    return _posting_result(
        "customer_advance",
        lines,
        description="Customer advance received",
        calculation={"amount": amount},
    )


def build_receivable_collection_posting(
    amount: float,
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
    receivable_account: str = UNIFIED_ACCOUNTS["receivable_trade"],
) -> dict:
    amount = _round2(amount)
    lines = [
        _make_line(bank_account, "Bank/Cash", debit=amount),
        _make_line(receivable_account, "Trade Receivable", credit=amount),
    ]
    return _posting_result(
        "receivable_collection",
        lines,
        description="Receivable collection",
        calculation={"amount": amount},
    )


# ═══════════════════════════════════════════════════════
# 5. PURCHASE / EXPENSE POSTINGS
# ═══════════════════════════════════════════════════════

def build_expense_posting(
    amount: float,
    expense_account: str,
    payment_status: str = "paid",
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
    payable_account: str = UNIFIED_ACCOUNTS["accounts_payable"],
) -> dict:
    amount = _round2(amount)
    credit_account = bank_account if payment_status == "paid" else payable_account
    credit_label = "Bank/Cash" if payment_status == "paid" else "Accounts Payable"

    lines = [
        _make_line(expense_account, "Expense", debit=amount),
        _make_line(credit_account, credit_label, credit=amount),
    ]

    return _posting_result(
        "expense",
        lines,
        description=f"Expense ({payment_status})",
        calculation={"amount": amount, "payment_status": payment_status},
    )


def build_purchase_vat_posting(
    gross_amount: float,
    expense_or_inventory_account: str,
    payment_status: str = "paid",
    input_vat_account: str = UNIFIED_ACCOUNTS["vat_input"],
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
    payable_account: str = UNIFIED_ACCOUNTS["accounts_payable"],
) -> dict:
    calc = split_vat_from_gross(gross_amount)
    credit_account = bank_account if payment_status == "paid" else payable_account
    credit_label = "Bank/Cash" if payment_status == "paid" else "Accounts Payable"

    lines = [
        _make_line(expense_or_inventory_account, "Expense / Inventory", debit=calc["net"]),
        _make_line(input_vat_account, "Input VAT", debit=calc["vat"]),
        _make_line(credit_account, credit_label, credit=calc["gross"]),
    ]

    return _posting_result(
        "purchase_vat",
        lines,
        description=f"Purchase with VAT ({payment_status})",
        calculation={"payment_status": payment_status, **calc},
    )


def build_supplier_invoice_posting(
    amount: float,
    expense_account: str,
    payable_account: str = UNIFIED_ACCOUNTS["accounts_payable"],
) -> dict:
    amount = _round2(amount)
    lines = [
        _make_line(expense_account, "Expense", debit=amount),
        _make_line(payable_account, "Accounts Payable", credit=amount),
    ]
    return _posting_result(
        "supplier_invoice",
        lines,
        description="Supplier invoice accrual",
        calculation={"amount": amount},
    )


def build_supplier_payment_posting(
    amount: float,
    payable_account: str = UNIFIED_ACCOUNTS["accounts_payable"],
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
) -> dict:
    amount = _round2(amount)
    lines = [
        _make_line(payable_account, "Accounts Payable", debit=amount),
        _make_line(bank_account, "Bank/Cash", credit=amount),
    ]
    return _posting_result(
        "supplier_payment",
        lines,
        description="Supplier payment",
        calculation={"amount": amount},
    )


def build_prepaid_expense_posting(
    amount: float,
    prepaid_account: str = UNIFIED_ACCOUNTS["prepaid_expense"],
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
) -> dict:
    amount = _round2(amount)
    lines = [
        _make_line(prepaid_account, "Prepaid Expense", debit=amount),
        _make_line(bank_account, "Bank/Cash", credit=amount),
    ]
    return _posting_result(
        "prepaid_expense",
        lines,
        description="Prepaid expense",
        calculation={"amount": amount},
    )


def build_bank_fee_posting(
    amount: float,
    expense_account: str = UNIFIED_ACCOUNTS["bank_fee_expense"],
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
) -> dict:
    return build_expense_posting(
        amount=amount,
        expense_account=expense_account,
        payment_status="paid",
        bank_account=bank_account,
    )


def build_interest_expense_posting(
    amount: float,
    expense_account: str = UNIFIED_ACCOUNTS["interest_expense"],
    payable_or_bank_account: str = UNIFIED_ACCOUNTS["bank"],
    is_paid: bool = True,
) -> dict:
    amount = _round2(amount)
    credit_label = "Bank/Cash" if is_paid else "Interest Payable"

    lines = [
        _make_line(expense_account, "Interest Expense", debit=amount),
        _make_line(payable_or_bank_account, credit_label, credit=amount),
    ]

    return _posting_result(
        "interest_expense",
        lines,
        description="Interest expense",
        calculation={"amount": amount, "is_paid": is_paid},
    )


def build_representative_expense_posting(
    amount: float,
    expense_account: str = UNIFIED_ACCOUNTS["representative_expense"],
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
) -> dict:
    return build_expense_posting(
        amount=amount,
        expense_account=expense_account,
        payment_status="paid",
        bank_account=bank_account,
    )


def build_marketing_expense_posting(
    amount: float,
    expense_account: str = UNIFIED_ACCOUNTS["marketing_expense"],
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
) -> dict:
    return build_expense_posting(
        amount=amount,
        expense_account=expense_account,
        payment_status="paid",
        bank_account=bank_account,
    )


# ═══════════════════════════════════════════════════════
# 6. PAYROLL / PIT / PENSION
# ═══════════════════════════════════════════════════════

def build_payroll_posting(
    gross_salary: float,
    pit_rate: float = 0.20,
    employee_pension_rate: float = 0.02,
    employer_pension_rate: float = 0.02,
    salary_expense_account: str = UNIFIED_ACCOUNTS["salary_expense"],
    salary_payable_account: str = UNIFIED_ACCOUNTS["net_salary_payable"],
    pit_payable_account: str = UNIFIED_ACCOUNTS["pit_payable"],
    employee_pension_account: str = UNIFIED_ACCOUNTS["employee_pension_payable"],
    employer_pension_expense_account: str = UNIFIED_ACCOUNTS["employer_pension_expense"],
    employer_pension_payable_account: str = UNIFIED_ACCOUNTS["employer_pension_payable"],
) -> dict:
    gross_salary = _round2(gross_salary)
    pit = _round2(gross_salary * pit_rate)
    employee_pension = _round2(gross_salary * employee_pension_rate)
    employer_pension = _round2(gross_salary * employer_pension_rate)
    net_salary = _round2(gross_salary - pit - employee_pension)
    total_employer_cost = _round2(gross_salary + employer_pension)

    lines = [
        _make_line(salary_expense_account, "Salary Expense", debit=gross_salary),
        _make_line(pit_payable_account, "PIT Payable", credit=pit),
        _make_line(employee_pension_account, "Employee Pension Payable", credit=employee_pension),
        _make_line(salary_payable_account, "Net Salary Payable", credit=net_salary),
    ]

    employer_lines = [
        _make_line(employer_pension_expense_account, "Employer Pension Expense", debit=employer_pension),
        _make_line(employer_pension_payable_account, "Employer Pension Payable", credit=employer_pension),
    ]

    return {
        "type": "payroll",
        "gross_salary": gross_salary,
        "pit": pit,
        "employee_pension": employee_pension,
        "employer_pension": employer_pension,
        "net_salary": net_salary,
        "total_employer_cost": total_employer_cost,
        "lines": lines,
        "employer_pension_lines": employer_lines,
        "human_readable": _format_lines(lines) + "\n\n" + _format_lines(employer_lines),
        "balance_ge_payload": {
            "main": _to_balance_ge(lines, description="Payroll Accrual"),
            "employer_pension": _to_balance_ge(employer_lines, description="Employer Pension Accrual"),
        },
    }


def build_payroll_from_net_posting(
    net_salary: float,
    pit_rate: float = 0.20,
    employee_pension_rate: float = 0.02,
    employer_pension_rate: float = 0.02,
) -> dict:
    calc = gross_up_salary_from_net(
        net_salary,
        pit_rate=pit_rate,
        employee_pension_rate=employee_pension_rate,
    )
    return build_payroll_posting(
        gross_salary=calc["gross"],
        pit_rate=pit_rate,
        employee_pension_rate=employee_pension_rate,
        employer_pension_rate=employer_pension_rate,
    )


def build_payroll_payment_posting(
    net_salary: float,
    salary_payable_account: str = UNIFIED_ACCOUNTS["net_salary_payable"],
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
) -> dict:
    net_salary = _round2(net_salary)

    lines = [
        _make_line(salary_payable_account, "Net Salary Payable", debit=net_salary),
        _make_line(bank_account, "Bank/Cash", credit=net_salary),
    ]

    return _posting_result(
        "payroll_payment",
        lines,
        description="Payroll Payment",
        calculation={"net_salary": net_salary},
    )


# ═══════════════════════════════════════════════════════
# 7. CIT / DIVIDEND / WITHHOLDING
# ═══════════════════════════════════════════════════════

def build_cit_posting(
    distributed_amount: float,
    cit_rate: float = 0.15,
    divisor: float = 0.85,
    cit_expense_account: str = UNIFIED_ACCOUNTS["profit_tax_expense"],
    cit_payable_account: str = UNIFIED_ACCOUNTS["cit_payable"],
) -> dict:
    calc = estonian_cit_from_distributed_amount(distributed_amount, cit_rate=cit_rate, divisor=divisor)
    lines = [
        _make_line(cit_expense_account, "Profit Tax Expense", debit=calc["cit"]),
        _make_line(cit_payable_account, "CIT Payable", credit=calc["cit"]),
    ]
    return _posting_result(
        "cit",
        lines,
        description="Profit Tax Accrual",
        calculation=calc,
    )


def build_dividend_posting(
    gross_amount: float,
    cit_rate: float = 0.15,
    divisor: float = 0.85,
    retained_earnings_account: str = UNIFIED_ACCOUNTS["retained_earnings"],
    dividends_payable_account: str = UNIFIED_ACCOUNTS["dividend_payable"],
    cit_payable_account: str = UNIFIED_ACCOUNTS["cit_payable"],
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
) -> dict:
    calc = estonian_cit_from_distributed_amount(
        gross_amount,
        cit_rate=cit_rate,
        divisor=divisor,
    )

    gross = calc["amount"]
    cit = calc["cit"]
    tax_base = calc["tax_base"]
    net_to_shareholder = calc["net_after_cit"]

    step1_lines = [
        _make_line(retained_earnings_account, "Retained Earnings", debit=gross),
        _make_line(dividends_payable_account, "Dividend Payable", credit=gross),
    ]

    step2_lines = [
        _make_line(dividends_payable_account, "Dividend Payable", debit=gross),
        _make_line(cit_payable_account, "CIT Payable", credit=cit),
        _make_line(bank_account, "Bank/Cash", credit=net_to_shareholder),
    ]

    return {
        "type": "dividend_2step",
        "gross": gross,
        "tax_base": tax_base,
        "cit": cit,
        "net_to_shareholder": net_to_shareholder,
        "cit_rate": cit_rate,
        "divisor": divisor,
        "step1": {
            "description": "Dividend Accrual",
            "lines": step1_lines,
            "human_readable": _format_lines(step1_lines),
            "balance_ge_payload": _to_balance_ge(step1_lines, description="Dividend Accrual"),
        },
        "step2": {
            "description": "Dividend Payment + CIT",
            "lines": step2_lines,
            "human_readable": _format_lines(step2_lines),
            "balance_ge_payload": _to_balance_ge(step2_lines, description="Dividend Payment + CIT"),
        },
    }


def build_withholding_posting(
    gross_amount: float,
    withholding_rate: float,
    expense_or_payable_account: str,
    withholding_payable_account: str = UNIFIED_ACCOUNTS["withholding_payable"],
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
) -> dict:
    calc = calculate_withholding_tax(gross_amount, withholding_rate)

    lines = [
        _make_line(expense_or_payable_account, "Expense / Payable", debit=calc["gross"]),
        _make_line(withholding_payable_account, "Withholding Payable", credit=calc["tax"]),
        _make_line(bank_account, "Bank/Cash", credit=calc["net"]),
    ]

    return _posting_result(
        "withholding",
        lines,
        description="Withholding tax posting",
        calculation=calc,
    )


def build_nonresident_service_withholding_posting(
    gross_amount: float,
    withholding_rate: float = 0.10,
    expense_account: str = "7810",
    withholding_payable_account: str = UNIFIED_ACCOUNTS["withholding_payable"],
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
) -> dict:
    return build_withholding_posting(
        gross_amount=gross_amount,
        withholding_rate=withholding_rate,
        expense_or_payable_account=expense_account,
        withholding_payable_account=withholding_payable_account,
        bank_account=bank_account,
    )


def build_interest_withholding_posting(
    gross_amount: float,
    withholding_rate: float = 0.05,
    expense_account: str = UNIFIED_ACCOUNTS["interest_expense"],
    withholding_payable_account: str = UNIFIED_ACCOUNTS["withholding_payable"],
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
) -> dict:
    return build_withholding_posting(
        gross_amount=gross_amount,
        withholding_rate=withholding_rate,
        expense_or_payable_account=expense_account,
        withholding_payable_account=withholding_payable_account,
        bank_account=bank_account,
    )


def build_royalty_withholding_posting(
    gross_amount: float,
    withholding_rate: float = 0.10,
    expense_account: str = "7810",
    withholding_payable_account: str = UNIFIED_ACCOUNTS["withholding_payable"],
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
) -> dict:
    return build_withholding_posting(
        gross_amount=gross_amount,
        withholding_rate=withholding_rate,
        expense_or_payable_account=expense_account,
        withholding_payable_account=withholding_payable_account,
        bank_account=bank_account,
    )


# ═══════════════════════════════════════════════════════
# 8. PROPERTY TAX / PENALTIES
# ═══════════════════════════════════════════════════════

def build_property_tax_posting(
    tax_amount: float,
    property_tax_expense_account: str = UNIFIED_ACCOUNTS["other_expense"],
    property_tax_payable_account: str = UNIFIED_ACCOUNTS["property_tax_payable"],
) -> dict:
    tax_amount = _round2(tax_amount)
    lines = [
        _make_line(property_tax_expense_account, "Property Tax Expense", debit=tax_amount),
        _make_line(property_tax_payable_account, "Property Tax Payable", credit=tax_amount),
    ]
    return _posting_result(
        "property_tax",
        lines,
        description="Property tax accrual",
        calculation={"tax_amount": tax_amount},
    )


def build_penalty_posting(
    amount: float,
    penalty_expense_account: str = UNIFIED_ACCOUNTS["other_expense"],
    payable_or_bank_account: str = UNIFIED_ACCOUNTS["bank"],
    is_paid: bool = True,
) -> dict:
    amount = _round2(amount)
    credit_label = "Bank/Cash" if is_paid else "Penalty Payable"
    lines = [
        _make_line(penalty_expense_account, "Penalty Expense", debit=amount),
        _make_line(payable_or_bank_account, credit_label, credit=amount),
    ]
    return _posting_result(
        "penalty",
        lines,
        description="Penalty posting",
        calculation={"amount": amount, "is_paid": is_paid},
    )


def build_late_fee_posting(
    amount: float,
    late_fee_expense_account: str = UNIFIED_ACCOUNTS["other_expense"],
    payable_or_bank_account: str = UNIFIED_ACCOUNTS["bank"],
    is_paid: bool = True,
) -> dict:
    amount = _round2(amount)
    credit_label = "Bank/Cash" if is_paid else "Late Fee Payable"
    lines = [
        _make_line(late_fee_expense_account, "Late Fee Expense", debit=amount),
        _make_line(payable_or_bank_account, credit_label, credit=amount),
    ]
    return _posting_result(
        "late_fee",
        lines,
        description="Late fee posting",
        calculation={"amount": amount, "is_paid": is_paid},
    )


# ═══════════════════════════════════════════════════════
# 9. INVENTORY / WRITE-OFF / SHORTAGE
# ═══════════════════════════════════════════════════════

def build_inventory_purchase_posting(
    amount: float,
    inventory_account: str = UNIFIED_ACCOUNTS["inventory"],
    bank_or_payable_account: str = UNIFIED_ACCOUNTS["accounts_payable"],
    is_paid: bool = False,
) -> dict:
    amount = _round2(amount)
    credit_label = "Bank/Cash" if is_paid else "Accounts Payable"
    lines = [
        _make_line(inventory_account, "Inventory", debit=amount),
        _make_line(bank_or_payable_account, credit_label, credit=amount),
    ]
    return _posting_result(
        "inventory_purchase",
        lines,
        description="Inventory purchase",
        calculation={"amount": amount, "is_paid": is_paid},
    )


def build_cogs_posting(
    amount: float,
    cogs_account: str = UNIFIED_ACCOUNTS["cogs"],
    inventory_account: str = UNIFIED_ACCOUNTS["inventory"],
) -> dict:
    amount = _round2(amount)
    lines = [
        _make_line(cogs_account, "COGS", debit=amount),
        _make_line(inventory_account, "Inventory", credit=amount),
    ]
    return _posting_result(
        "cogs",
        lines,
        description="COGS posting",
        calculation={"amount": amount},
    )


def build_inventory_shortage_posting(
    shortage_amount: float,
    expense_account: str = UNIFIED_ACCOUNTS["cogs"],
    inventory_account: str = UNIFIED_ACCOUNTS["inventory"],
) -> dict:
    shortage_amount = _round2(shortage_amount)
    lines = [
        _make_line(expense_account, "Inventory Shortage Expense", debit=shortage_amount),
        _make_line(inventory_account, "Inventory", credit=shortage_amount),
    ]
    return _posting_result(
        "inventory_shortage",
        lines,
        description="Inventory shortage",
        calculation={"shortage_amount": shortage_amount},
    )


def build_taxable_writeoff_posting(
    net_amount: float,
    vat_rate: float = 0.18,
    cit_rate: float = 0.15,
    divisor: float = 0.85,
    expense_account: str = "7290",
    inventory_account: str = UNIFIED_ACCOUNTS["inventory"],
    vat_payable_account: str = UNIFIED_ACCOUNTS["vat_payable"],
    cit_expense_account: str = UNIFIED_ACCOUNTS["profit_tax_expense"],
    cit_payable_account: str = UNIFIED_ACCOUNTS["cit_payable"],
) -> dict:
    net_amount = _round2(net_amount)

    vat_calc = add_vat_to_net(net_amount, vat_rate=vat_rate)
    cit_calc = estonian_cit_from_distributed_amount(
        net_amount,
        cit_rate=cit_rate,
        divisor=divisor,
    )

    vat = vat_calc["vat"]
    cit = cit_calc["cit"]

    lines = [
        _make_line(expense_account, "Write-off / Shortage Expense", debit=net_amount),
        _make_line(inventory_account, "Inventory", credit=net_amount),
        _make_line(expense_account, "VAT Expense", debit=vat),
        _make_line(vat_payable_account, "VAT Payable", credit=vat),
        _make_line(cit_expense_account, "Profit Tax Expense", debit=cit),
        _make_line(cit_payable_account, "CIT Payable", credit=cit),
    ]

    return _posting_result(
        "taxable_writeoff",
        lines,
        description="Taxable Write-off / Shortage",
        calculation={
            "net_amount": net_amount,
            "vat": vat,
            "cit_tax_base": cit_calc["tax_base"],
            "cit": cit,
            "gross_with_vat": vat_calc["gross"],
        },
    )


def build_free_supply_posting(
    net_amount: float,
    inventory_account: str = UNIFIED_ACCOUNTS["inventory"],
    expense_account: str = "7290",
    vat_payable_account: str = UNIFIED_ACCOUNTS["vat_payable"],
) -> dict:
    net_amount = _round2(net_amount)
    vat_calc = add_vat_to_net(net_amount)
    vat = vat_calc["vat"]

    lines = [
        _make_line(expense_account, "Free Supply Expense", debit=net_amount),
        _make_line(inventory_account, "Inventory", credit=net_amount),
        _make_line(expense_account, "VAT Expense", debit=vat),
        _make_line(vat_payable_account, "VAT Payable", credit=vat),
    ]

    return _posting_result(
        "free_supply",
        lines,
        description="Free supply posting",
        calculation={"net_amount": net_amount, "vat": vat},
    )


# ═══════════════════════════════════════════════════════
# 10. FIXED ASSETS / DEPRECIATION / LOANS / LEASE
# ═══════════════════════════════════════════════════════

def build_fixed_asset_purchase_posting(
    amount: float,
    fixed_asset_account: str = UNIFIED_ACCOUNTS["fixed_asset"],
    bank_or_payable_account: str = UNIFIED_ACCOUNTS["accounts_payable"],
    is_paid: bool = False,
) -> dict:
    amount = _round2(amount)
    credit_label = "Bank/Cash" if is_paid else "Accounts Payable"
    lines = [
        _make_line(fixed_asset_account, "Fixed Asset", debit=amount),
        _make_line(bank_or_payable_account, credit_label, credit=amount),
    ]
    return _posting_result(
        "fixed_asset_purchase",
        lines,
        description="Fixed asset purchase",
        calculation={"amount": amount, "is_paid": is_paid},
    )


def build_depreciation_posting(
    amount: float,
    depreciation_expense_account: str = UNIFIED_ACCOUNTS["depreciation_expense"],
    accumulated_depreciation_account: str = UNIFIED_ACCOUNTS["accumulated_depreciation"],
) -> dict:
    amount = _round2(amount)
    lines = [
        _make_line(depreciation_expense_account, "Depreciation Expense", debit=amount),
        _make_line(accumulated_depreciation_account, "Accumulated Depreciation", credit=amount),
    ]
    return _posting_result(
        "depreciation",
        lines,
        description="Depreciation posting",
        calculation={"amount": amount},
    )


def build_loan_receipt_posting(
    amount: float,
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
    loan_payable_account: str = UNIFIED_ACCOUNTS["loan_payable"],
) -> dict:
    amount = _round2(amount)
    lines = [
        _make_line(bank_account, "Bank/Cash", debit=amount),
        _make_line(loan_payable_account, "Loan Payable", credit=amount),
    ]
    return _posting_result(
        "loan_receipt",
        lines,
        description="Loan receipt",
        calculation={"amount": amount},
    )


def build_loan_repayment_posting(
    principal_amount: float,
    loan_payable_account: str = UNIFIED_ACCOUNTS["loan_payable"],
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
) -> dict:
    principal_amount = _round2(principal_amount)
    lines = [
        _make_line(loan_payable_account, "Loan Payable", debit=principal_amount),
        _make_line(bank_account, "Bank/Cash", credit=principal_amount),
    ]
    return _posting_result(
        "loan_repayment",
        lines,
        description="Loan repayment",
        calculation={"principal_amount": principal_amount},
    )


def build_lease_initial_posting(
    amount: float,
    rou_asset_account: str = "1710",
    lease_liability_account: str = UNIFIED_ACCOUNTS["lease_liability"],
) -> dict:
    amount = _round2(amount)
    lines = [
        _make_line(rou_asset_account, "ROU Asset", debit=amount),
        _make_line(lease_liability_account, "Lease Liability", credit=amount),
    ]
    return _posting_result(
        "lease_initial",
        lines,
        description="Lease initial recognition",
        calculation={"amount": amount},
    )


def build_lease_interest_posting(
    amount: float,
    interest_expense_account: str = UNIFIED_ACCOUNTS["interest_expense"],
    lease_liability_account: str = UNIFIED_ACCOUNTS["lease_liability"],
) -> dict:
    amount = _round2(amount)
    lines = [
        _make_line(interest_expense_account, "Lease Interest Expense", debit=amount),
        _make_line(lease_liability_account, "Lease Liability", credit=amount),
    ]
    return _posting_result(
        "lease_interest",
        lines,
        description="Lease interest accrual",
        calculation={"amount": amount},
    )


def build_lease_depreciation_posting(
    amount: float,
    depreciation_expense_account: str = UNIFIED_ACCOUNTS["depreciation_expense"],
    accumulated_depreciation_account: str = UNIFIED_ACCOUNTS["accumulated_depreciation"],
) -> dict:
    amount = _round2(amount)
    lines = [
        _make_line(depreciation_expense_account, "ROU Depreciation Expense", debit=amount),
        _make_line(accumulated_depreciation_account, "Accumulated Depreciation", credit=amount),
    ]
    return _posting_result(
        "lease_depreciation",
        lines,
        description="Lease depreciation posting",
        calculation={"amount": amount},
    )


# ═══════════════════════════════════════════════════════
# 11. QUICK TEST
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    print("accounting_rules ready")