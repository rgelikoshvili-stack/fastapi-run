"""app/integrations/rs_ge_api.py — Revenue Service of Georgia (rs.ge) integration.

Provides helpers for:
 - VAT return filing data preparation (RS Form 10)
 - Withholding tax declaration (Form 1)
 - Taxpayer verification by INN

Note: rs.ge does not have a public REST API — submissions are via their web portal.
This module prepares structured payloads in rs.ge XML/JSON format for manual upload
or future automation via Selenium/Playwright.
"""
import logging
from decimal import Decimal
from datetime import date
from typing import Optional

log = logging.getLogger(__name__)


def build_vat_return(
    tenant_inn: str,
    period_year: int,
    period_month: int,
    taxable_sales: Decimal,
    vat_collected: Decimal,
    taxable_purchases: Decimal,
    vat_paid: Decimal,
) -> dict:
    """Build RS Form 10 (VAT Return) payload for a given period."""
    vat_payable = vat_collected - vat_paid
    return {
        "form": "RS-Form-10",
        "taxpayer_inn": tenant_inn,
        "period": {
            "year": period_year,
            "month": period_month,
            "description": f"{period_year}-{period_month:02d}",
        },
        "sales": {
            "taxable_turnover": float(taxable_sales),
            "vat_18pct": float(vat_collected),
        },
        "purchases": {
            "deductible_purchases": float(taxable_purchases),
            "vat_credit": float(vat_paid),
        },
        "payable": {
            "vat_payable": float(max(vat_payable, Decimal("0"))),
            "vat_refundable": float(max(-vat_payable, Decimal("0"))),
        },
        "generated_at": date.today().isoformat(),
        "status": "draft",
        "note": "Submit via rs.ge portal → VAT → Form 10",
    }


def build_withholding_declaration(
    tenant_inn: str,
    period_year: int,
    period_month: int,
    payments: list[dict],
) -> dict:
    """Build RS Form 1 (Withholding Tax) payload.

    payments: list of {recipient_inn, amount, tax_rate, tax_amount, payment_type}
    """
    total_paid = sum(p.get("amount", 0) for p in payments)
    total_tax = sum(p.get("tax_amount", 0) for p in payments)
    return {
        "form": "RS-Form-1",
        "taxpayer_inn": tenant_inn,
        "period": {
            "year": period_year,
            "month": period_month,
        },
        "payments": payments,
        "totals": {
            "total_paid": float(total_paid),
            "total_tax_withheld": float(total_tax),
        },
        "generated_at": date.today().isoformat(),
        "status": "draft",
        "note": "Submit via rs.ge portal → Withholding Tax → Form 1",
    }


def verify_taxpayer_inn(inn: str) -> dict:
    """Validate INN format (does not call rs.ge — offline validation only)."""
    inn = inn.strip()
    if not inn.isdigit():
        return {"valid": False, "reason": "INN must contain digits only"}
    if len(inn) == 9:
        return {"valid": True, "type": "legal_entity", "inn": inn}
    if len(inn) == 11:
        return {"valid": True, "type": "individual", "inn": inn}
    return {"valid": False, "reason": f"Invalid length {len(inn)} (expected 9 or 11)"}


def format_period_code(year: int, month: Optional[int] = None) -> str:
    """RS portal period code format."""
    if month:
        return f"{year}{month:02d}"
    return str(year)
