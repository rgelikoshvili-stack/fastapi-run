"""app/api/services/rsge_comparison_service.py
Bridge Hub — RS.ge document comparison constants and helpers.

Defines mismatch type codes and risk level constants used when comparing
RS.ge-imported documents against Bridge Hub journal drafts and invoices.
All values are plain strings — no DB access, no external calls.
"""
from __future__ import annotations

# ── Mismatch type codes ───────────────────────────────────────────────────────

MATCHED               = "matched"
AMOUNT_MISMATCH       = "amount_mismatch"
VAT_MISMATCH          = "vat_mismatch"
SELLER_BUYER_MISMATCH = "seller_buyer_mismatch"
MISSING_IN_BRIDGE     = "missing_in_bridge"
MISSING_IN_RSGE       = "missing_in_rsge"
DUPLICATE             = "duplicate"
REQUIRES_REVIEW       = "requires_review"

# ── Risk level codes ──────────────────────────────────────────────────────────

RISK_LOW    = "RISK_LOW"
RISK_MEDIUM = "RISK_MEDIUM"
RISK_HIGH   = "RISK_HIGH"

# ── Risk assignment helpers ───────────────────────────────────────────────────

_MISMATCH_RISK: dict[str, str] = {
    MATCHED:               RISK_LOW,
    AMOUNT_MISMATCH:       RISK_MEDIUM,
    VAT_MISMATCH:          RISK_MEDIUM,
    SELLER_BUYER_MISMATCH: RISK_HIGH,
    MISSING_IN_BRIDGE:     RISK_HIGH,
    MISSING_IN_RSGE:       RISK_MEDIUM,
    DUPLICATE:             RISK_HIGH,
    REQUIRES_REVIEW:       RISK_MEDIUM,
}


def risk_for_mismatch(mismatch_type: str) -> str:
    """Return the default risk level for a given mismatch type."""
    return _MISMATCH_RISK.get(mismatch_type, RISK_MEDIUM)
