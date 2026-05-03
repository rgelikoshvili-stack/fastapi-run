"""app/integrations/nbg_api.py — National Bank of Georgia exchange rates.

API: https://nbg.gov.ge/gw/api/ct/monetarypolicy/currencies/ka/json
Returns rates relative to GEL (1 unit of foreign currency = X GEL).
"""
import logging
import urllib.request
import json
from datetime import date
from typing import Optional

log = logging.getLogger(__name__)

_NBG_URL = "https://nbg.gov.ge/gw/api/ct/monetarypolicy/currencies/ka/json"

_SUPPORTED = {"USD", "EUR", "GBP", "CHF", "RUB", "TRY", "CNY", "JPY", "UAH", "AMD", "AZN"}


def fetch_nbg_rates(target_date: Optional[str] = None) -> dict:
    """Fetch live exchange rates from NBG.

    Returns dict: {currency: rate_to_gel, ...} including GEL=1.0.
    Falls back to empty dict on error — caller should use DEFAULT_RATES.
    """
    url = _NBG_URL
    if target_date:
        url += f"?date={target_date}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BridgeHub/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log.warning("action=nbg_fetch_failed error=%s", e)
        return {}

    rates = {"GEL": 1.0}
    try:
        currencies = payload[0].get("currencies", [])
        for c in currencies:
            code = c.get("code", "").upper()
            rate = c.get("rate")
            quantity = c.get("quantity", 1)
            if code in _SUPPORTED and rate and quantity:
                rates[code] = round(float(rate) / int(quantity), 6)
    except Exception as e:
        log.warning("action=nbg_parse_failed error=%s", e)
        return {}

    log.info("action=nbg_rates_fetched count=%d date=%s", len(rates), target_date or date.today())
    return rates


def sync_rates_to_db(conn) -> int:
    """Fetch NBG rates and upsert into exchange_rates table (both old and new columns).
    Returns count updated.
    """
    rates = fetch_nbg_rates()
    if not rates:
        return 0

    cur = conn.cursor()
    updated = 0
    try:
        for currency, rate in rates.items():
            if currency == "GEL":
                continue
            # Write to both the legacy columns (currency/rate) and new columns
            # (from_code/to_code/fetched_at) in one upsert.
            cur.execute(
                """
                INSERT INTO exchange_rates
                    (currency, rate, updated_at, from_code, to_code, source, fetched_at)
                VALUES (%s, %s, NOW(), %s, 'GEL', 'nbg', NOW())
                ON CONFLICT (currency) DO UPDATE
                    SET rate       = EXCLUDED.rate,
                        updated_at = EXCLUDED.updated_at,
                        from_code  = EXCLUDED.from_code,
                        to_code    = EXCLUDED.to_code,
                        source     = EXCLUDED.source,
                        fetched_at = EXCLUDED.fetched_at
                """,
                (currency, rate, currency),
            )
            updated += 1
        conn.commit()
    except Exception as e:
        conn.rollback()
        log.error("action=nbg_db_sync_failed error=%s", e)
        updated = 0
    finally:
        cur.close()

    log.info("action=nbg_rates_synced count=%d", updated)
    return updated
