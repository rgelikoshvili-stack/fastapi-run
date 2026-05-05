import logging
from decimal import Decimal
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel
from typing import Optional

from app.api.authz import require_permission
from app.api.db import get_conn, get_db, _q
from app.api.response_utils import ok_response, error_response
from app.api.audit import log_event
from app.api.services.currency_service import get_rate, convert
from app.api.services.cache_service import cache_get, cache_set, CACHE_TTL

log = logging.getLogger(__name__)

router = APIRouter(prefix="/currency", tags=["currency"])

DEFAULT_RATES = {
    "USD": 2.72, "EUR": 2.95, "GBP": 3.45,
    "RUB": 0.030, "TRY": 0.082, "CHF": 3.10,
    "CNY": 0.375, "JPY": 0.018, "UAH": 0.066,
    "AMD": 0.007, "AZN": 1.60, "GEL": 1.0,
}

class ConvertRequest(BaseModel):
    amount: float
    from_currency: str
    to_currency: Optional[str] = "GEL"
    date: Optional[str] = None

class RateUpdate(BaseModel):
    currency: str
    rate: float


@router.get("/rates")
async def get_rates(date: Optional[str] = Query(None, description="YYYY-MM-DD; defaults to today")):
    """Get all exchange rates to GEL, optionally for a specific date."""
    from datetime import date as _date
    cache_key = f"rates:{date or str(_date.today())}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    try:
        async with get_conn() as conn:
            if date:
                rows = [dict(r) for r in await conn.fetch(_q("""
                    SELECT COALESCE(from_code, currency) AS currency, rate, fetched_at
                    FROM exchange_rates
                    WHERE DATE(COALESCE(fetched_at, updated_at)) <= %s
                      AND (to_code = 'GEL' OR to_code IS NULL)
                    ORDER BY COALESCE(fetched_at, updated_at) DESC
                """), date)]
            else:
                rows = [dict(r) for r in await conn.fetch("""
                    SELECT COALESCE(from_code, currency) AS currency, rate,
                           COALESCE(fetched_at, updated_at) AS fetched_at
                    FROM exchange_rates
                    ORDER BY COALESCE(fetched_at, updated_at) DESC
                """)]
        seen = {}
        for r in rows:
            c = r["currency"]
            if c and c not in seen:
                seen[c] = {"currency": c, "rate": float(r["rate"]), "fetched_at": str(r.get("fetched_at") or "")}
        rates_dict = {c: d["rate"] for c, d in seen.items()} if seen else DEFAULT_RATES
        updated_at = rows[0]["fetched_at"] if rows else None
    except Exception as e:
        log.warning("get_rates endpoint DB error: %s", e)
        rates_dict = DEFAULT_RATES
        updated_at = None

    result = ok_response("Exchange rates (to GEL)", {
        "base": "GEL",
        "date": date or "latest",
        "rates": rates_dict,
        "updated_at": str(updated_at) if updated_at else None,
        "source": "NBG",
    })
    cache_set(cache_key, result, CACHE_TTL["exchange_rates"])
    return result


@router.post("/convert")
def convert_currency(data: ConvertRequest):
    """Convert amount between any two currencies via GEL."""
    from_cur = data.from_currency.upper()
    to_cur   = (data.to_currency or "GEL").upper()
    try:
        result = convert(Decimal(str(data.amount)), from_cur, to_cur, data.date)
        return ok_response("Converted", result)
    except Exception as e:
        return error_response("Conversion failed", "CONVERT_ERROR", str(e))


@router.get("/convert")
def convert_currency_get(
    from_currency: str = Query(..., description="Source currency code (e.g. USD)"),
    to_currency:   str = Query("GEL", description="Target currency code"),
    amount:        float = Query(..., description="Amount to convert"),
    date:          Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """GET-friendly currency conversion."""
    try:
        result = convert(Decimal(str(amount)), from_currency.upper(), to_currency.upper(), date)
        return ok_response("Converted", result)
    except Exception as e:
        return error_response("Conversion failed", "CONVERT_ERROR", str(e))


@router.post("/rates/update")
async def update_rate(data: RateUpdate, request: Request):
    require_permission(request, "settings:write")
    currency = data.currency.upper()
    try:
        async with get_conn() as conn:
            await conn.execute(_q("""
                INSERT INTO exchange_rates (currency, rate, updated_at, from_code, to_code, source, fetched_at)
                VALUES (%s, %s, NOW(), %s, 'GEL', 'manual', NOW())
                ON CONFLICT (currency) DO UPDATE
                    SET rate=EXCLUDED.rate, updated_at=EXCLUDED.updated_at,
                        from_code=EXCLUDED.from_code, to_code=EXCLUDED.to_code,
                        source=EXCLUDED.source, fetched_at=EXCLUDED.fetched_at
            """), currency, data.rate, currency)
        log_event("currency.rate_update", "exchange_rates", currency,
                  new_value={"currency": currency, "rate": data.rate})
    except Exception as e:
        return error_response("Update failed", "UPDATE_ERROR", str(e))
    return ok_response("Rate updated", {"currency": currency, "rate": data.rate})


@router.post("/rates/sync-nbg")
async def sync_nbg_rates(request: Request):
    require_permission(request, "settings:write")
    """Fetch live rates from National Bank of Georgia and store in DB."""
    import asyncio
    try:
        from app.integrations.nbg_api import sync_rates_to_db

        def _sync():
            conn = get_db()
            try:
                return sync_rates_to_db(conn)
            finally:
                conn.close()

        loop = asyncio.get_event_loop()
        updated = await loop.run_in_executor(None, _sync)
        return ok_response("NBG rates synced", {"updated": updated})
    except Exception as e:
        log.error("action=nbg_sync_error: %s", e)
        return error_response("NBG sync failed", "NBG_ERROR", str(e))
