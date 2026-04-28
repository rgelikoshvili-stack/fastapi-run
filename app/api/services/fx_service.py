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

log = logging.getLogger(__name__)

FX_GAIN_ACCOUNT = "8310"   # Foreign currency gain
FX_LOSS_ACCOUNT = "8320"   # Foreign currency loss
ROUNDING = Decimal("0.01")


def get_rate(conn, currency: str, rate_date: date) -> Optional[Decimal]:
    """Fetch NBG rate from exchange_rates table. Returns GEL per 1 unit of currency."""
    if currency.upper() == "GEL":
        return Decimal("1")
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT rate FROM exchange_rates
            WHERE currency = %s
            ORDER BY updated_at DESC LIMIT 1
        """, (currency.upper(),))
        row = cur.fetchone()
        return Decimal(str(row[0])) if row else None
    finally:
        cur.close()


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


def revalue_open_items(conn, tenant_id: str, revalue_date: date) -> list[dict]:
    """
    Re-measure all open foreign-currency items (unpaid invoices, open payables)
    at the given date's NBG rate. Returns list of FX journal entries to post.
    """
    cur = conn.cursor()
    results = []

    try:
        # Find invoices in foreign currency that are unpaid
        cur.execute("""
            SELECT id, currency, total, original_rate, account_code
            FROM invoices
            WHERE tenant_id = %s
              AND currency != 'GEL'
              AND status NOT IN ('paid', 'cancelled')
              AND original_rate IS NOT NULL
              AND original_rate > 0
        """, (tenant_id,))
        invoices = cur.fetchall()

        for inv_id, currency, total, orig_rate, acct in invoices:
            current_rate = get_rate(conn, currency, revalue_date)
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
                "debit_account": fx["account"] if not fx["is_gain"] else acct,
                "credit_account": fx["account"] if fx["is_gain"] else acct,
                "amount_gel": abs(fx["difference_gel"]),
                "currency": currency,
                **fx,
            })

    except Exception as e:
        log.warning("revalue_open_items failed: %s", e)
    finally:
        cur.close()

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
