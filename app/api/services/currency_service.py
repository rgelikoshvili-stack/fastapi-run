"""app/api/services/currency_service.py — Multi-currency helpers.

All rates are expressed as: 1 unit of from_code = X units of to_code.
GEL is the base currency.  NBG is the sole authoritative source.
"""
from __future__ import annotations
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from datetime import date as _date

from app.api.db import get_db, get_conn, _q

log = logging.getLogger(__name__)

_DEFAULT_RATES: dict[str, float] = {
    "USD": 2.72, "EUR": 2.95, "GBP": 3.45,
    "RUB": 0.030, "TRY": 0.082, "CHF": 3.10,
    "CNY": 0.375, "JPY": 0.018, "UAH": 0.066,
    "AMD": 0.007, "AZN": 1.60, "GEL": 1.0,
}


def get_rate(from_code: str, to_code: str, for_date: Optional[str] = None) -> Decimal:
    """Return exchange rate: 1 from_code = ? to_code.

    Looks up the closest available rate on or before for_date.
    Falls back to _DEFAULT_RATES if DB unavailable.
    """
    from_code = from_code.upper()
    to_code   = to_code.upper()

    if from_code == to_code:
        return Decimal("1.0")

    if to_code == "GEL":
        return _rate_to_gel(from_code, for_date)

    if from_code == "GEL":
        r = _rate_to_gel(to_code, for_date)
        if r == Decimal("0"):
            return Decimal("0")
        return (Decimal("1.0") / r).quantize(Decimal("0.000001"), ROUND_HALF_UP)

    # cross via GEL
    gel_from = _rate_to_gel(from_code, for_date)
    gel_to   = _rate_to_gel(to_code,   for_date)
    if gel_to == Decimal("0"):
        return Decimal("0")
    return (gel_from / gel_to).quantize(Decimal("0.000001"), ROUND_HALF_UP)


def _rate_to_gel(currency: str, for_date: Optional[str] = None) -> Decimal:
    """Return rate: 1 currency = ? GEL.  Uses DB first, DEFAULT_RATES as fallback."""
    if currency == "GEL":
        return Decimal("1.0")

    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            if for_date:
                cur.execute("""
                    SELECT rate FROM exchange_rates
                    WHERE (from_code = %s OR currency = %s)
                      AND (to_code = 'GEL' OR to_code IS NULL)
                      AND DATE(fetched_at) <= %s
                    ORDER BY fetched_at DESC
                    LIMIT 1
                """, (currency, currency, for_date))
            else:
                cur.execute("""
                    SELECT rate FROM exchange_rates
                    WHERE (from_code = %s OR currency = %s)
                      AND (to_code = 'GEL' OR to_code IS NULL)
                    ORDER BY COALESCE(fetched_at, updated_at) DESC
                    LIMIT 1
                """, (currency, currency))
            row = cur.fetchone()
            cur.close()
        finally:
            conn.close()

        if row:
            return Decimal(str(row[0]))
    except Exception as e:
        log.warning("currency_service._rate_to_gel db error: %s", e)

    fallback = _DEFAULT_RATES.get(currency)
    if fallback:
        log.warning(
            "currency_service: no DB rate for %s — using hardcoded fallback %.4f. "
            "Journal FX amounts may be inaccurate until NBG sync runs.",
            currency, fallback,
        )
        return Decimal(str(fallback))
    log.error("currency_service: no rate found for %s in DB or fallback table", currency)
    return Decimal("0")


async def _rate_to_gel_async(currency: str, for_date: Optional[str] = None) -> Decimal:
    """Async asyncpg version of _rate_to_gel."""
    if currency == "GEL":
        return Decimal("1.0")
    try:
        async with get_conn() as conn:
            if for_date:
                row = await conn.fetchrow(_q("""
                    SELECT rate FROM exchange_rates
                    WHERE (from_code = %s OR currency = %s)
                      AND (to_code = 'GEL' OR to_code IS NULL)
                      AND DATE(fetched_at) <= %s
                    ORDER BY fetched_at DESC LIMIT 1
                """), currency, currency, for_date)
            else:
                row = await conn.fetchrow(_q("""
                    SELECT rate FROM exchange_rates
                    WHERE (from_code = %s OR currency = %s)
                      AND (to_code = 'GEL' OR to_code IS NULL)
                    ORDER BY COALESCE(fetched_at, updated_at) DESC LIMIT 1
                """), currency, currency)
        if row:
            return Decimal(str(row["rate"]))
    except Exception as e:
        log.warning("currency_service._rate_to_gel_async db error: %s", e)
    fallback = _DEFAULT_RATES.get(currency)
    if fallback:
        log.warning(
            "currency_service: no DB rate for %s — using hardcoded fallback %.4f.",
            currency, fallback,
        )
        return Decimal(str(fallback))
    log.error("currency_service: no rate found for %s in DB or fallback table", currency)
    return Decimal("0")


async def get_rate_async(from_code: str, to_code: str, for_date: Optional[str] = None) -> Decimal:
    """Async version of get_rate for use in async contexts."""
    from_code = from_code.upper()
    to_code   = to_code.upper()
    if from_code == to_code:
        return Decimal("1.0")
    if to_code == "GEL":
        return await _rate_to_gel_async(from_code, for_date)
    if from_code == "GEL":
        r = await _rate_to_gel_async(to_code, for_date)
        if r == Decimal("0"):
            return Decimal("0")
        return (Decimal("1.0") / r).quantize(Decimal("0.000001"), ROUND_HALF_UP)
    gel_from = await _rate_to_gel_async(from_code, for_date)
    gel_to   = await _rate_to_gel_async(to_code,   for_date)
    if gel_to == Decimal("0"):
        return Decimal("0")
    return (gel_from / gel_to).quantize(Decimal("0.000001"), ROUND_HALF_UP)


def convert(amount: Decimal, from_code: str, to_code: str,
            for_date: Optional[str] = None) -> dict:
    """Convert amount and return full detail dict."""
    rate   = get_rate(from_code, to_code, for_date)
    result = (amount * rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
    return {
        "original":  {"amount": float(amount), "currency": from_code.upper()},
        "converted": {"amount": float(result), "currency": to_code.upper()},
        "rate":      float(rate),
        "date":      for_date or _date.today().isoformat(),
    }


def apply_fx_to_entry(entry: dict, conn=None) -> dict:
    """Fill amount_gel + exchange_rate on a journal entry dict (in-place)."""
    currency = (entry.get("currency") or "GEL").upper()
    if currency == "GEL":
        entry["amount_gel"]    = entry.get("amount", 0)
        entry["exchange_rate"] = 1.0
        return entry

    amount = Decimal(str(entry.get("amount") or 0))
    rate   = get_rate(currency, "GEL")
    entry["amount_gel"]    = float((amount * rate).quantize(Decimal("0.01"), ROUND_HALF_UP))
    entry["exchange_rate"] = float(rate)
    return entry
