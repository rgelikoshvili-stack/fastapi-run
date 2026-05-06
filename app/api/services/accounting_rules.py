"""
Bridge Hub — Accounting Rules (backward-compatibility re-export)
app/api/services/accounting_rules.py

All logic lives in the focused sub-modules:
  accounting_rules_core.py    — accounts, format, helpers, tax math
  accounting_rules_revenue.py — revenue & expense postings (sections 4-5)
  accounting_rules_tax.py     — payroll, CIT, withholding, assets (sections 6-10)

Do NOT add new code here. Import directly from the sub-modules instead.
"""

from .accounting_rules_core import (
    UNIFIED_ACCOUNTS,
    format_gel,
    _round2,
    _make_line,
    _format_lines,
    _to_balance_ge,
    _posting_result,
    split_vat_from_gross,
    add_vat_to_net,
    estonian_cit_from_distributed_amount,
    gross_up_salary_from_net,
    calculate_pension_components,
    calculate_withholding_tax,
    calculate_property_tax,
)

from .accounting_rules_revenue import (
    build_vat_posting,
    build_vat_posting_from_net,
    build_simple_revenue_posting,
    build_service_revenue_posting,
    build_export_revenue_posting,
    build_customer_advance_posting,
    build_receivable_collection_posting,
    build_expense_posting,
    build_purchase_vat_posting,
    build_supplier_invoice_posting,
    build_supplier_payment_posting,
    build_prepaid_expense_posting,
    build_bank_fee_posting,
    build_interest_expense_posting,
    build_representative_expense_posting,
    build_marketing_expense_posting,
)

from .accounting_rules_tax import (
    build_payroll_posting,
    build_payroll_from_net_posting,
    build_payroll_payment_posting,
    build_cit_posting,
    build_dividend_posting,
    build_withholding_posting,
    build_nonresident_service_withholding_posting,
    build_interest_withholding_posting,
    build_royalty_withholding_posting,
    build_property_tax_posting,
    build_penalty_posting,
    build_late_fee_posting,
    build_inventory_purchase_posting,
    build_cogs_posting,
    build_inventory_shortage_posting,
    build_taxable_writeoff_posting,
    build_free_supply_posting,
    build_fixed_asset_purchase_posting,
    build_depreciation_posting,
    build_loan_receipt_posting,
    build_loan_repayment_posting,
    build_lease_initial_posting,
    build_lease_interest_posting,
    build_lease_depreciation_posting,
)

__all__ = [
    "UNIFIED_ACCOUNTS",
    "format_gel", "_round2", "_make_line", "_format_lines", "_to_balance_ge", "_posting_result",
    "split_vat_from_gross", "add_vat_to_net", "estonian_cit_from_distributed_amount",
    "gross_up_salary_from_net", "calculate_pension_components",
    "calculate_withholding_tax", "calculate_property_tax",
    "build_vat_posting", "build_vat_posting_from_net",
    "build_simple_revenue_posting", "build_service_revenue_posting",
    "build_export_revenue_posting", "build_customer_advance_posting",
    "build_receivable_collection_posting", "build_expense_posting",
    "build_purchase_vat_posting", "build_supplier_invoice_posting",
    "build_supplier_payment_posting", "build_prepaid_expense_posting",
    "build_bank_fee_posting", "build_interest_expense_posting",
    "build_representative_expense_posting", "build_marketing_expense_posting",
    "build_payroll_posting", "build_payroll_from_net_posting",
    "build_payroll_payment_posting", "build_cit_posting", "build_dividend_posting",
    "build_withholding_posting", "build_nonresident_service_withholding_posting",
    "build_interest_withholding_posting", "build_royalty_withholding_posting",
    "build_property_tax_posting", "build_penalty_posting", "build_late_fee_posting",
    "build_inventory_purchase_posting", "build_cogs_posting",
    "build_inventory_shortage_posting", "build_taxable_writeoff_posting",
    "build_free_supply_posting", "build_fixed_asset_purchase_posting",
    "build_depreciation_posting", "build_loan_receipt_posting",
    "build_loan_repayment_posting", "build_lease_initial_posting",
    "build_lease_interest_posting", "build_lease_depreciation_posting",
]
