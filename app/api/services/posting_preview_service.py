"""
app/api/services/posting_preview_service.py
Bridge Hub — Shadow Posting (Predictive Impact)

Read-only: fetches draft, computes P&L/VAT/tax impact, returns preview.
NO writes to any table.
"""

import logging
from decimal import Decimal
from typing import Optional

import psycopg2.extras

from app.api.db import get_db

log = logging.getLogger(__name__)

# Account code → impact category mapping
_INCOME_PREFIX = ("6",)
_EXPENSE_PREFIX = ("7",)
_VAT_ACCOUNTS = {"3410", "1230", "1231"}      # VAT payable / receivable
_TAX_ACCOUNTS = {
    "3320": "PIT (საშემოსავლო)",
    "3340": "CIT (მოგების გადასახადი)",
    "3350": "Withholding",
    "3370": "Dividend payable",
}
_ASSET_PREFIX = ("1", "2")
_LIABILITY_PREFIX = ("3", "4")


def _classify_account(code: str) -> str:
    if not code:
        return "unknown"
    if code[:1] in _INCOME_PREFIX:
        return "income"
    if code[:1] in _EXPENSE_PREFIX:
        return "expense"
    if code in _VAT_ACCOUNTS:
        return "vat"
    if code in _TAX_ACCOUNTS:
        return "tax"
    if code[:1] in _ASSET_PREFIX:
        return "asset"
    if code[:1] in _LIABILITY_PREFIX:
        return "liability"
    return "other"


def _impact_narrative(draft: dict) -> dict:
    amount = Decimal(str(draft.get("amount") or 0))
    debit = str(draft.get("debit_account") or draft.get("account_code") or "")
    credit = str(draft.get("credit_account") or "")
    description = draft.get("description") or ""
    currency = draft.get("currency") or "GEL"
    status = draft.get("status") or "unknown"

    debit_cat = _classify_account(debit)
    credit_cat = _classify_account(credit)

    pl_impact: Optional[Decimal] = None
    pl_direction = None
    vat_change: Optional[Decimal] = None
    tax_impact: Optional[Decimal] = None
    tax_type: Optional[str] = None
    notes = []

    # P&L impact
    if debit_cat == "expense":
        pl_impact = -amount
        pl_direction = "decrease"
        notes.append(f"ამ გატარების შემდეგ ხარჯი გაიზრდება {amount:,.2f} {currency}-ით")
    elif credit_cat == "income":
        pl_impact = amount
        pl_direction = "increase"
        notes.append(f"ამ გატარების შემდეგ შემოსავალი გაიზრდება {amount:,.2f} {currency}-ით")
    elif debit_cat == "income":
        pl_impact = -amount
        pl_direction = "decrease"
        notes.append(f"ამ გატარების შემდეგ შემოსავალი შემცირდება {amount:,.2f} {currency}-ით")
    elif credit_cat == "expense":
        pl_impact = amount
        pl_direction = "increase"
        notes.append(f"ამ გატარების შემდეგ ხარჯი შემცირდება {amount:,.2f} {currency}-ით")

    # VAT impact
    if debit_cat == "vat" or credit_cat == "vat":
        vat_account = debit if debit_cat == "vat" else credit
        if vat_account == "3410":
            vat_change = amount if credit_cat == "vat" else -amount
            direction = "გაიზრდება" if vat_change > 0 else "შემცირდება"
            notes.append(f"დღგ ვალდებულება {direction} {abs(vat_change):,.2f} {currency}-ით")
        elif vat_account in ("1230", "1231"):
            vat_change = amount if debit_cat == "vat" else -amount
            direction = "გაიზრდება" if vat_change > 0 else "შემცირდება"
            notes.append(f"დღგ ჩათვლა {direction} {abs(vat_change):,.2f} {currency}-ით")

    # Tax impact
    for acc, label in _TAX_ACCOUNTS.items():
        if debit == acc or credit == acc:
            tax_impact = amount
            tax_type = label
            direction = "გაიზრდება" if credit == acc else "შემცირდება"
            notes.append(f"{label} {direction} {amount:,.2f} {currency}-ით")
            break

    # VAT estimate if no explicit VAT account but it's an expense/income
    if vat_change is None and pl_impact is not None:
        estimated_vat = (abs(pl_impact) * Decimal("18") / Decimal("118")).quantize(Decimal("0.01"))
        notes.append(
            f"სავარაუდო დღგ კომპონენტი: {estimated_vat:,.2f} {currency} "
            f"(18% ჩათვლით, თუ ეს გადასახადდებული ოპერაციაა)"
        )

    if not notes:
        notes.append(
            f"ბალანსის გადაადგილება: Dr {debit or '—'} / Cr {credit or '—'} "
            f"— {amount:,.2f} {currency}"
        )

    return {
        "pl_impact": float(pl_impact) if pl_impact is not None else None,
        "pl_direction": pl_direction,
        "vat_change": float(vat_change) if vat_change is not None else None,
        "tax_impact": float(tax_impact) if tax_impact is not None else None,
        "tax_type": tax_type,
        "debit_category": debit_cat,
        "credit_category": credit_cat,
        "summary": " | ".join(notes),
        "notes": notes,
        "currency": currency,
        "amount": float(amount),
        "draft_status": status,
    }


def preview_posting_service(draft_id: int, tenant_id: str) -> dict:
    """
    Read-only: compute impact of posting draft_id.
    Returns structured impact without any DB writes.
    """
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """
            SELECT id, description, partner, amount, currency,
                   account_code, debit_account, credit_account,
                   reason, status, date, confidence, source_document_id
            FROM journal_drafts
            WHERE id = %s AND tenant_id = %s
            """,
            (draft_id, tenant_id),
        )
        row = cur.fetchone()
        if not row:
            return {
                "ok": False,
                "error": {"code": "NOT_FOUND", "details": f"Draft {draft_id} not found"},
            }

        draft = dict(row)
        impact = _impact_narrative(draft)

        return {
            "ok": True,
            "preview": True,
            "draft_id": draft_id,
            "draft": {
                "description": draft["description"],
                "partner": draft["partner"],
                "amount": float(draft["amount"] or 0),
                "currency": draft["currency"] or "GEL",
                "debit_account": draft["debit_account"],
                "credit_account": draft["credit_account"],
                "date": str(draft["date"]) if draft["date"] else None,
                "status": draft["status"],
                "confidence": float(draft["confidence"] or 0),
                "source_document_id": draft.get("source_document_id"),
            },
            "impact": impact,
            "warning": "ეს არის preview — DB-ში ჩანაწერი არ შეიქმნება",
        }

    except Exception as e:
        log.error("preview_posting_service draft_id=%s tenant=%s: %s", draft_id, tenant_id, e)
        return {
            "ok": False,
            "error": {"code": "INTERNAL_ERROR", "details": str(e)},
        }
    finally:
        cur.close()
        conn.close()
