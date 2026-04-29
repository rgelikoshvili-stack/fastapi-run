"""app/api/services/doc_journal_builder.py
Builds Dr/Cr journal entries from a parsed document with full Georgian tax logic.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from app.api.services.party_resolver import PartyResolution, OurRole
from app.api.services.operation_classifier import OperationCategory, CATEGORY_TO_ACCOUNT
from app.api.services.contract_classifier import ProviderType
from app.api.services.taxation_engine import (
    calculate_vat,
    calculate_service_pit,
    calculate_payroll,
)


def build_journal(
    doc,
    party: PartyResolution,
    category: OperationCategory,
    is_vat_payer: bool = True,
    provider_type: ProviderType = ProviderType.SHPS,
) -> dict:
    """
    Return:
    {
      "entries":      [{"dr"|"cr": account_code, "amount": float, "note": str}],
      "is_foreign":   bool,
      "warnings":     [str],
      "tax_detail":   dict | None,   # PIT/PAYG breakdown if individual
    }
    """
    if party.our_role == OurRole.FOREIGN:
        return {"entries": [], "is_foreign": True, "warnings": party.warnings, "tax_detail": None}

    if party.our_role == OurRole.BUYER:
        return _buyer_entries(doc, party, category, is_vat_payer, provider_type)

    if party.our_role == OurRole.SELLER:
        return _seller_entries(doc, party, category, is_vat_payer)

    return {"entries": [], "is_foreign": False, "warnings": party.warnings, "tax_detail": None}


def _d(val) -> Decimal:
    try:
        return Decimal(str(val)) if val is not None else Decimal("0")
    except Exception:
        return Decimal("0")


def _buyer_entries(
    doc,
    party: PartyResolution,
    category: OperationCategory,
    is_vat_payer: bool,
    provider_type: ProviderType,
) -> dict:
    total   = _d(getattr(doc, "total_with_vat", None) or getattr(doc, "total_amount", None))
    doc_vat = _d(getattr(doc, "total_vat", None))
    entries = []
    warnings: list[str] = []
    tax_detail = None

    # ── Individual / IM provider — PIT withholding ───────────────────────────
    if provider_type in (ProviderType.FP, ProviderType.IM) and total > 0:
        pit_info = calculate_service_pit(total, apply_pension=True)
        tax_detail = pit_info

        expense_acc = CATEGORY_TO_ACCOUNT.get(category, "7490")
        entries.append({
            "dr": expense_acc,
            "amount": float(total),
            "note": f"{category.value} — {party.counterparty_name or 'ი.მ./ფ.პ.'}"
        })
        # PIT payable
        entries.append({
            "cr": "3320",
            "amount": pit_info["pit"],
            "note": "საშემოსავლო გადასახადი (PIT 20%)"
        })
        # Pension (employee portion)
        if pit_info["employee_pension"] > 0:
            entries.append({
                "cr": "3380",
                "amount": pit_info["employee_pension"],
                "note": "საპენსიო — დასაქმებული (2%)"
            })
        # Pension (employer portion) as additional expense
        if pit_info["employer_pension"] > 0:
            entries.append({
                "dr": "7190",
                "amount": pit_info["employer_pension"],
                "note": "საპენსიო — დამსაქმებელი (2%)"
            })
            entries.append({
                "cr": "3380",
                "amount": pit_info["employer_pension"],
                "note": "საპენსიო — დამსაქმებელი (2%)"
            })
        # Net payment to person
        entries.append({
            "cr": "3110",
            "amount": float(total),
            "note": f"კრედიტორი — {party.counterparty_name}"
        })
        return {"entries": entries, "is_foreign": False, "warnings": warnings, "tax_detail": tax_detail}

    # ── Advance payment ───────────────────────────────────────────────────────
    if category == OperationCategory.ADVANCE_PAYMENT:
        entries.append({
            "dr": "1490",
            "amount": float(total),
            "note": f"ავანსი — {party.counterparty_name}"
        })
        entries.append({
            "cr": "1010",
            "amount": float(total),
            "note": "ბანკიდან გადახდა"
        })
        return {"entries": entries, "is_foreign": False, "warnings": warnings, "tax_detail": None}

    # ── Standard goods/services purchase ─────────────────────────────────────
    vat = doc_vat if is_vat_payer and doc_vat > 0 else Decimal("0")
    if is_vat_payer and vat == 0 and total > 0:
        # Calculate VAT from total
        vat_info = calculate_vat(total, inclusive=True)
        vat  = _d(vat_info["vat_amount"])
    net = total - vat

    asset_categories = (OperationCategory.IT_HARDWARE, OperationCategory.FURNITURE)
    if category in asset_categories and net >= 1000:
        asset_acc = CATEGORY_TO_ACCOUNT[category]
        entries.append({
            "dr": asset_acc,
            "amount": float(net),
            "note": f"ძირ. საშუალება — {party.counterparty_name}"
        })
    else:
        expense_acc = CATEGORY_TO_ACCOUNT.get(category, "7490")
        entries.append({
            "dr": expense_acc,
            "amount": float(net),
            "note": category.value
        })

    if is_vat_payer and vat > 0:
        entries.append({
            "dr": "1410",
            "amount": float(vat),
            "note": "შეძენილი დღგ"
        })

    entries.append({
        "cr": "3110",
        "amount": float(total),
        "note": f"კრედიტორი — {party.counterparty_name}"
    })

    return {"entries": entries, "is_foreign": False, "warnings": warnings, "tax_detail": None}


def _seller_entries(
    doc,
    party: PartyResolution,
    category: OperationCategory,
    is_vat_payer: bool,
) -> dict:
    total   = _d(getattr(doc, "total_with_vat", None) or getattr(doc, "total_amount", None))
    doc_vat = _d(getattr(doc, "total_vat", None))

    vat = doc_vat if is_vat_payer and doc_vat > 0 else Decimal("0")
    if is_vat_payer and vat == 0 and total > 0:
        vat_info = calculate_vat(total, inclusive=True)
        vat = _d(vat_info["vat_amount"])
    net = total - vat

    product_categories = (
        OperationCategory.IT_HARDWARE,
        OperationCategory.FURNITURE,
        OperationCategory.OFFICE_SUPPLIES,
    )
    revenue_acc = "6110" if category in product_categories else "6210"

    entries = [
        {"dr": "1110", "amount": float(total), "note": f"დებიტორი — {party.counterparty_name}"},
        {"cr": revenue_acc, "amount": float(net), "note": "შემოსავალი"},
    ]

    if is_vat_payer and vat > 0:
        entries.append({"cr": "3330", "amount": float(vat), "note": "დარიცხული დღგ"})

    return {"entries": entries, "is_foreign": False, "warnings": [], "tax_detail": None}


# ── Convenience function for document pipeline ───────────────────────────────

def build_journal_from_doc(
    extraction: dict,
    our_inn: Optional[str] = None,
    is_vat_payer: bool = True,
) -> dict:
    """
    Simplified builder used by the document pipeline route.
    extraction: dict from ExtractedDocument.model_dump()
    Returns journal entries + completeness info.
    """
    from app.api.services.contract_classifier import classify_provider_type, ProviderType as PT
    from app.api.services.taxation_engine import analyse_document_taxes

    doc_type    = extraction.get("document_type", "unknown")
    seller_inn  = extraction.get("seller_inn") or (extraction.get("seller") or {}).get("inn")
    buyer_inn   = extraction.get("buyer_inn") or (extraction.get("buyer") or {}).get("inn")
    total       = extraction.get("total_amount") or extraction.get("total_with_vat") or 0
    vat_amount  = extraction.get("total_vat") or 0

    # Determine our role
    our_role = "buyer"
    if our_inn:
        if seller_inn == our_inn:
            our_role = "seller"
        elif buyer_inn == our_inn:
            our_role = "buyer"

    provider_name = (extraction.get("seller") or {}).get("name") if our_role == "buyer" else None
    p_type = classify_provider_type(provider_name, seller_inn if our_role == "buyer" else buyer_inn)

    # Tax analysis
    tax_info = analyse_document_taxes(
        doc_type=doc_type,
        total_amount=total,
        provider_type=p_type.value,
        is_our_purchase=(our_role == "buyer"),
        vat_inclusive=bool(vat_amount and total and vat_amount > 0),
    )

    entries = []
    net  = float(total) - float(vat_amount) if vat_amount else float(total)
    vat  = float(vat_amount) if vat_amount else 0.0

    if our_role == "buyer":
        if p_type in (PT.FP, PT.IM) and total:
            pit_d = tax_info.get("pit_detail") or {}
            entries.append({"dr": "7490", "amount": float(total), "note": f"მომსახურება — {provider_name or seller_inn or '?'}"})
            if pit_d.get("pit"):
                entries.append({"cr": "3320", "amount": pit_d["pit"], "note": "PIT 20%"})
            if pit_d.get("employee_pension"):
                entries.append({"cr": "3380", "amount": pit_d["employee_pension"], "note": "საპენსიო 2%"})
            entries.append({"cr": "3110", "amount": float(total), "note": "კრედიტორი"})
        else:
            if vat and is_vat_payer:
                entries.append({"dr": "7490", "amount": net, "note": "ხარჯი"})
                entries.append({"dr": "1410", "amount": vat, "note": "დღგ შეძენილი"})
            else:
                entries.append({"dr": "7490", "amount": float(total), "note": "ხარჯი"})
            entries.append({"cr": "3110", "amount": float(total), "note": "კრედიტორი"})
    else:
        if vat and is_vat_payer:
            entries.append({"dr": "1110", "amount": float(total), "note": "დებიტორი"})
            entries.append({"cr": "6210", "amount": net, "note": "შემოსავალი"})
            entries.append({"cr": "3330", "amount": vat, "note": "დღგ დარიცხული"})
        else:
            entries.append({"dr": "1110", "amount": float(total), "note": "დებიტორი"})
            entries.append({"cr": "6210", "amount": float(total), "note": "შემოსავალი"})

    return {
        "entries":       entries,
        "our_role":      our_role,
        "provider_type": p_type.value,
        "tax_detail":    tax_info,
        "warnings":      tax_info.get("warnings", []),
    }
