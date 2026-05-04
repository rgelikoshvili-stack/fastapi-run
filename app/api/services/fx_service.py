"""app/api/services/fx_service.py — Multi-currency FX gain/loss calculations.

Georgian accounting standard:
  - Transactions recorded at transaction-date NBG rate
  - At reporting date, monetary items re-measured at closing rate
  - Difference → FX gain (account 8310) or FX loss (account 8320)

Journal entry structure:
  FX Gain:  Dr  Asset/Liability   Cr  8310 FX Gain
  FX Loss:  Dr  8320 FX Loss      Cr  Asset/Liability
"""
from __future__ import annotations
import logging
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from app.api.db import get_conn, _q

log = logging.getLogger(__name__)

FX_GAIN_ACCOUNT = "8310"   # Foreign currency gain
FX_LOSS_ACCOUNT = "8320"   # Foreign currency loss
ROUNDING = Decimal("0.01")


async def _get_rate_conn(conn, currency: str, rate_date: date) -> Optional[Decimal]:
    """Fetch rate using an existing asyncpg conn (no extra pool checkout)."""
    if currency.upper() == "GEL":
        return Decimal("1")
    row = await conn.fetchrow(_q(
        "SELECT rate FROM exchange_rates WHERE currency = %s ORDER BY updated_at DESC LIMIT 1"
    ), currency.upper())
    return Decimal(str(row["rate"])) if row else None


async def get_rate(currency: str, rate_date: date) -> Optional[Decimal]:
    """Fetch NBG rate for a currency. Opens own pool connection."""
    async with get_conn() as conn:
        return await _get_rate_conn(conn, currency, rate_date)


def calculate_fx_difference(
    original_amount_foreign: Decimal,
    currency: str,
    original_rate: Decimal,
    current_rate: Decimal,
) -> dict:
    """
    Calculate FX difference for a foreign-currency balance.

    Returns:
        {
          "original_gel": float,   # booked amount in GEL
          "current_gel": float,    # re-measured amount in GEL
          "difference_gel": float, # positive = gain, negative = loss
          "is_gain": bool,
          "account": "8310"|"8320"
        }
    """
    original_gel = (original_amount_foreign * original_rate).quantize(ROUNDING, ROUND_HALF_UP)
    current_gel = (original_amount_foreign * current_rate).quantize(ROUNDING, ROUND_HALF_UP)
    diff = (current_gel - original_gel).quantize(ROUNDING, ROUND_HALF_UP)
    is_gain = diff >= 0

    return {
        "currency": currency,
        "original_amount_foreign": float(original_amount_foreign),
        "original_rate": float(original_rate),
        "current_rate": float(current_rate),
        "original_gel": float(original_gel),
        "current_gel": float(current_gel),
        "difference_gel": float(diff),
        "is_gain": is_gain,
        "account": FX_GAIN_ACCOUNT if is_gain else FX_LOSS_ACCOUNT,
    }


async def revalue_open_items(tenant_id: str, revalue_date: date) -> list[dict]:
    """
    Re-measure all open foreign-currency items (unpaid invoices, open payables)
    at the given date's NBG rate. Returns list of FX journal entries to post.
    """
    results = []
    try:
        async with get_conn() as conn:
            rows = await conn.fetch(_q("""
                SELECT id, currency, total, original_rate, account_code
                FROM invoices
                WHERE tenant_id = %s
                  AND currency != 'GEL'
                  AND status NOT IN ('paid', 'cancelled')
                  AND original_rate IS NOT NULL
                  AND original_rate > 0
            """), tenant_id)

            for row in rows:
                inv_id   = row["id"]
                currency = row["currency"]
                total    = row["total"]
                orig_rate = row["original_rate"]
                acct     = row["account_code"]

                current_rate = await _get_rate_conn(conn, currency, revalue_date)
                if not current_rate:
                    log.warning("No rate for %s on %s", currency, revalue_date)
                    continue

                fx = calculate_fx_difference(
                    Decimal(str(total)), currency,
                    Decimal(str(orig_rate)), current_rate,
                )
                if abs(fx["difference_gel"]) < 0.01:
                    continue

                results.append({
                    "source": "invoice",
                    "source_id": inv_id,
                    "description": f"FX {'gain' if fx['is_gain'] else 'loss'} revaluation — {currency} invoice #{inv_id}",
                    "debit_account":  fx["account"] if not fx["is_gain"] else acct,
                    "credit_account": fx["account"] if fx["is_gain"] else acct,
                    "amount_gel": abs(fx["difference_gel"]),
                    "currency": currency,
                    **fx,
                })
    except Exception as e:
        log.warning("revalue_open_items failed: %s", e)

    return results


def build_fx_journal_entry(fx_result: dict, tenant_id: str, entry_date: date) -> dict:
    """Build a journal entry dict from FX revaluation result."""
    return {
        "tenant_id": tenant_id,
        "entry_date": entry_date.isoformat(),
        "description": fx_result["description"],
        "currency": "GEL",
        "lines": [
            {
                "account_code": fx_result["debit_account"],
                "debit": abs(fx_result["difference_gel"]),
                "credit": 0,
                "description": f"FX revaluation Dr — {fx_result['currency']}",
            },
            {
                "account_code": fx_result["credit_account"],
                "debit": 0,
                "credit": abs(fx_result["difference_gel"]),
                "description": f"FX revaluation Cr — {fx_result['currency']}",
            },
        ],
        "source_type": "fx_revaluation",
        "source_id": str(fx_result.get("source_id", "")),
        "is_fx": True,
    }
