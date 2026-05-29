"""app/api/services/company_identity_service.py — Company Identity Engine (Task 12B).

Determines whether the tenant is the buyer or seller in a transaction by
comparing the INN/TIN found in document text against the tenant's registered
company INN stored in tenant_settings under the key "company.inn".

Georgian company identification numbers:
  - Legal entities: 9-digit number (საიდენტიფიკაციო კოდი)
  - Individuals:    11-digit personal ID number

Role resolution:
  INN in text == tenant's INN  →  seller (we issued the invoice)  → sales journal
  INN in text != tenant's INN  →  buyer  (we received the invoice) → purchase journal
"""
from __future__ import annotations

import re
from typing import Any

from app.api.services.tenant_config_service import get_tenant_setting, set_tenant_setting

TENANT_INN_KEY = "company.inn"

# Georgian INN patterns: 9-digit (company) or 11-digit (individual)
_INN_PATTERN = re.compile(r"\b(\d{9}|\d{11})\b")

# Journal type → accounting instruction
JOURNAL_TYPE_MAP: dict[str, dict[str, Any]] = {
    "sales": {
        "description": "Sales invoice — we are the seller",
        "debit_account": "1210",   # receivable_trade
        "credit_accounts": ["6110", "3310"],  # sales_revenue, vat_payable
    },
    "purchase": {
        "description": "Purchase invoice — we are the buyer",
        "debit_accounts": ["7910", "3311"],  # other_expense (or asset), vat_input
        "credit_account": "3110",  # accounts_payable
    },
}


def extract_inns(text: str) -> list[str]:
    """Return all unique INN candidates found in *text* (9 or 11 digits)."""
    return list(dict.fromkeys(m.group(1) for m in _INN_PATTERN.finditer(text)))


def classify_party_role(tenant_inn: str, doc_inns: list[str]) -> str:
    """Return 'seller', 'buyer', or 'unknown' based on INN match.

    If the tenant's INN appears in the document → tenant is the seller.
    If other INNs are present but tenant's is not → tenant is the buyer.
    If no INNs found → unknown.
    """
    if not doc_inns:
        return "unknown"
    if tenant_inn and tenant_inn in doc_inns:
        return "seller"
    return "buyer"


async def get_tenant_inn(tenant_id: str) -> str | None:
    """Return the tenant's registered INN, or None if not set."""
    value = await get_tenant_setting(tenant_id, TENANT_INN_KEY, None)
    if value is None:
        return None
    return str(value).strip() or None


async def set_tenant_inn(tenant_id: str, inn: str) -> bool:
    """Store the tenant's company INN. Returns True on success."""
    inn = inn.strip()
    if not _INN_PATTERN.fullmatch(inn):
        raise ValueError(f"Invalid INN format: '{inn}' — must be 9 or 11 digits")
    return await set_tenant_setting(tenant_id, TENANT_INN_KEY, inn)


async def resolve_journal_type(tenant_id: str, text: str) -> dict[str, Any]:
    """Analyse *text*, compare INNs against tenant's registered INN, and return
    a classification result with the recommended journal type.

    Return shape:
        {
            "inns_found": [...],
            "tenant_inn": "123456789" | None,
            "role": "seller" | "buyer" | "unknown",
            "journal_type": "sales" | "purchase" | None,
            "journal_hint": {...} | None,
            "confidence": "high" | "low",
        }
    """
    doc_inns = extract_inns(text)
    tenant_inn = await get_tenant_inn(tenant_id)

    role = classify_party_role(tenant_inn or "", doc_inns)

    journal_type: str | None = None
    journal_hint: dict | None = None
    confidence = "low"

    if role == "seller":
        journal_type = "sales"
        journal_hint = JOURNAL_TYPE_MAP["sales"]
        confidence = "high"
    elif role == "buyer" and doc_inns:
        journal_type = "purchase"
        journal_hint = JOURNAL_TYPE_MAP["purchase"]
        confidence = "high" if tenant_inn else "low"

    return {
        "inns_found": doc_inns,
        "tenant_inn": tenant_inn,
        "role": role,
        "journal_type": journal_type,
        "journal_hint": journal_hint,
        "confidence": confidence,
    }
