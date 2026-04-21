"""app/api/services/doc_journal_builder.py
Builds journal entries from a parsed document, party resolution, and operation category.
"""
from __future__ import annotations
from decimal import Decimal
from typing import Optional

from app.api.services.party_resolver import PartyResolution, OurRole
from app.api.services.operation_classifier import OperationCategory, CATEGORY_TO_ACCOUNT


def build_journal(
    doc,
    party: PartyResolution,
    category: OperationCategory,
    is_vat_payer: bool = True,
) -> dict:
    """Return {entries: [...], is_foreign: bool, warnings: [...]}"""
    if party.our_role == OurRole.FOREIGN:
        return {"entries": [], "is_foreign": True, "warnings": party.warnings}

    if party.our_role == OurRole.BUYER:
        return _buyer_entries(doc, party, category, is_vat_payer)

    if party.our_role == OurRole.SELLER:
        return _seller_entries(doc, party, category, is_vat_payer)

    return {"entries": [], "is_foreign": False, "warnings": party.warnings}


def _buyer_entries(doc, party: PartyResolution, category: OperationCategory, is_vat_payer: bool) -> dict:
    total = Decimal(str(doc.total_with_vat or 0))
    vat = Decimal(str(doc.total_vat or 0)) if is_vat_payer else Decimal(0)
    net = total - vat

    entries = []

    if category == OperationCategory.ADVANCE_PAYMENT:
        entries.append({"dr": "1490", "amount": float(total), "note": f"ავანსი — {party.counterparty_name}"})
        entries.append({"cr": "1010", "amount": float(total), "note": "ბანკიდან გადახდა"})
        return {"entries": entries, "is_foreign": False, "warnings": []}

    asset_categories = (OperationCategory.IT_HARDWARE, OperationCategory.FURNITURE)
    if category in asset_categories and net >= 1000:
        asset_acc = CATEGORY_TO_ACCOUNT[category]
        entries.append({"dr": asset_acc, "amount": float(net), "note": f"ძირ. საშუალება — {party.counterparty_name}"})
    else:
        expense_acc = CATEGORY_TO_ACCOUNT.get(category, "7490")
        entries.append({"dr": expense_acc, "amount": float(net), "note": category.value})

    if vat > 0:
        entries.append({"dr": "1410", "amount": float(vat), "note": "შეძენილი ДДС"})

    entries.append({"cr": "3110", "amount": float(total), "note": f"კრედიტორი — {party.counterparty_name}"})

    return {"entries": entries, "is_foreign": False, "warnings": []}


def _seller_entries(doc, party: PartyResolution, category: OperationCategory, is_vat_payer: bool) -> dict:
    total = Decimal(str(doc.total_with_vat or 0))
    vat = Decimal(str(doc.total_vat or 0)) if is_vat_payer else Decimal(0)
    net = total - vat

    product_categories = (OperationCategory.IT_HARDWARE, OperationCategory.FURNITURE, OperationCategory.OFFICE_SUPPLIES)
    revenue_acc = "6110" if category in product_categories else "6210"

    entries = [
        {"dr": "1110", "amount": float(total), "note": f"დებიტორი — {party.counterparty_name}"},
        {"cr": revenue_acc, "amount": float(net), "note": "შემოსავალი"},
    ]

    if vat > 0:
        entries.append({"cr": "3330", "amount": float(vat), "note": "დარიცხული ДДС"})

    return {"entries": entries, "is_foreign": False, "warnings": []}
