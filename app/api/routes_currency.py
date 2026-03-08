from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import psycopg2.extras
from app.api.db import get_db
from app.api.response_utils import ok_response, error_response
from app.api.audit import log_event

router = APIRouter(prefix="/currency", tags=["currency"])

DEFAULT_RATES = {
    "USD": 2.72, "EUR": 2.95, "GBP": 3.45,
    "RUB": 0.030, "TRY": 0.082, "CHF": 3.10, "GEL": 1.0
}

class ConvertRequest(BaseModel):
    amount: float
    from_currency: str
    to_currency: Optional[str] = "GEL"

class RateUpdate(BaseModel):
    currency: str
    rate: float

def get_rates_from_db():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT currency, rate FROM exchange_rates")
        rows = cur.fetchall()
        return {r["currency"]: float(r["rate"]) for r in rows} if rows else DEFAULT_RATES
    except:
        return DEFAULT_RATES
    finally:
        cur.close(); conn.close()

@router.get("/rates")
def get_rates():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM exchange_rates ORDER BY currency")
        rows = cur.fetchall()
        rates = {r["currency"]: float(r["rate"]) for r in rows} if rows else DEFAULT_RATES
        updated_at = str(rows[0]["updated_at"]) if rows else None
    except:
        rates = DEFAULT_RATES
        updated_at = None
    finally:
        cur.close(); conn.close()
    return ok_response("Exchange rates (to GEL)", {
        "base": "GEL", "rates": rates,
        "updated_at": updated_at, "source": "NBG"
    })

@router.post("/convert")
def convert_currency(data: ConvertRequest):
    from_cur = data.from_currency.upper()
    to_cur = data.to_currency.upper()
    rates = get_rates_from_db()
    if from_cur not in rates:
        return error_response("Unknown currency", "INVALID_CURRENCY", f"{from_cur} not supported")
    if to_cur not in rates:
        return error_response("Unknown currency", "INVALID_CURRENCY", f"{to_cur} not supported")
    gel = data.amount * rates[from_cur]
    result = gel / rates[to_cur]
    return ok_response("Converted", {
        "original": {"amount": data.amount, "currency": from_cur},
        "converted": {"amount": round(result, 4), "currency": to_cur},
        "rate": round(rates[from_cur] / rates[to_cur], 6),
        "via_gel": round(gel, 4)
    })

@router.post("/rates/update")
def update_rate(data: RateUpdate):
    currency = data.currency.upper()
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO exchange_rates (currency, rate, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (currency) DO UPDATE SET rate=%s, updated_at=NOW()
        """, (currency, data.rate, data.rate))
        conn.commit()
        log_event("currency.rate_update", "exchange_rates", currency,
                  new_value={"currency": currency, "rate": data.rate})
    except Exception as e:
        conn.rollback()
        return error_response("Update failed", "UPDATE_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Rate updated", {"currency": currency, "rate": data.rate})
