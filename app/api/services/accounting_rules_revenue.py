"""
Bridge Hub — Accounting Rules: Revenue & Expense Postings
app/api/services/accounting_rules_revenue.py

Sections 4-5: Sales/Revenue and Purchase/Expense posting templates.
"""
from __future__ import annotations

from .accounting_rules_core import (
    UNIFIED_ACCOUNTS,
    _round2, _make_line, _posting_result,
    split_vat_from_gross, add_vat_to_net,
)


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
        "vat_sale", lines,
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
        "vat_sale", lines,
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
        "simple_revenue", lines,
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
        "service_revenue", lines,
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
        "export_revenue", lines,
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
        "customer_advance", lines,
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
        "receivable_collection", lines,
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
        "expense", lines,
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
        "purchase_vat", lines,
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
        "supplier_invoice", lines,
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
        "supplier_payment", lines,
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
        "prepaid_expense", lines,
        description="Prepaid expense",
        calculation={"amount": amount},
    )


def build_bank_fee_posting(
    amount: float,
    expense_account: str = UNIFIED_ACCOUNTS["bank_fee_expense"],
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
) -> dict:
    return build_expense_posting(
        amount=amount, expense_account=expense_account,
        payment_status="paid", bank_account=bank_account,
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
        "interest_expense", lines,
        description="Interest expense",
        calculation={"amount": amount, "is_paid": is_paid},
    )


def build_representative_expense_posting(
    amount: float,
    expense_account: str = UNIFIED_ACCOUNTS["representative_expense"],
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
) -> dict:
    return build_expense_posting(
        amount=amount, expense_account=expense_account,
        payment_status="paid", bank_account=bank_account,
    )


def build_marketing_expense_posting(
    amount: float,
    expense_account: str = UNIFIED_ACCOUNTS["marketing_expense"],
    bank_account: str = UNIFIED_ACCOUNTS["bank"],
) -> dict:
    return build_expense_posting(
        amount=amount, expense_account=expense_account,
        payment_status="paid", bank_account=bank_account,
    )
