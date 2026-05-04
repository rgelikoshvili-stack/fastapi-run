"""app/api/routes_fx.py — Multi-currency FX gain/loss endpoints."""
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel
from datetime import date
from decimal import Decimal
from typing import Optional

from app.api.authz import require_permission
from app.api.tenant_context import resolve_tenant_id
from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, error_response, http_error
from app.api.services.fx_service import (
    get_rate, calculate_fx_difference, revalue_open_items, build_fx_journal_entry,
)
import logging

router = APIRouter(prefix="/fx", tags=["fx"])
log = logging.getLogger(__name__)


class FXCalcRequest(BaseModel):
    currency: str
    amount: float
    original_rate: float
    revalue_date: Optional[str] = None   # YYYY-MM-DD, default today


class FXRevaluationRequest(BaseModel):
    revalue_date: Optional[str] = None
    post_entries: bool = False


@router.post("/calculate")
async def calculate_fx(body: FXCalcRequest, request: Request):
    """Calculate FX gain/loss for a single foreign-currency amount."""
    require_permission(request, "reports:read")

    revalue_date = date.fromisoformat(body.revalue_date) if body.revalue_date else date.today()
    current_rate = await get_rate(body.currency, revalue_date)
    if not current_rate:
        return http_error(404, f"No NBG rate for {body.currency} on {revalue_date}", "RATE_NOT_FOUND")

    fx = calculate_fx_difference(
        Decimal(str(body.amount)),
        body.currency,
        Decimal(str(body.original_rate)),
        current_rate,
    )
    return ok_response("FX calculation", {**fx, "revalue_date": revalue_date.isoformat()})


@router.get("/rates/{currency}")
async def get_currency_rate(currency: str, request: Request,
                            rate_date: Optional[str] = Query(None)):
    """Get NBG rate for a currency on a given date."""
    require_permission(request, "reports:read")
    d = date.fromisoformat(rate_date) if rate_date else date.today()
    rate = await get_rate(currency.upper(), d)
    if not rate:
        return http_error(404, f"No rate for {currency} on {d}", "RATE_NOT_FOUND")

    return ok_response(f"{currency} rate on {d}", {
        "currency": currency.upper(),
        "date": d.isoformat(),
        "rate_gel": float(rate),
    })


@router.post("/revalue")
async def revalue_positions(body: FXRevaluationRequest, request: Request):
    """
    Re-measure all open foreign-currency items at current NBG rates.
    Returns FX journal entries. Optionally posts them to journal_drafts.
    """
    require_permission(request, "posting:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    revalue_date = date.fromisoformat(body.revalue_date) if body.revalue_date else date.today()

    try:
        fx_results = await revalue_open_items(tenant_id, revalue_date)
        journal_entries = [build_fx_journal_entry(r, tenant_id, revalue_date) for r in fx_results]

        posted_count = 0
        if body.post_entries and journal_entries:
            async with get_conn() as conn:
                for entry in journal_entries:
                    try:
                        await conn.execute(_q("""
                            INSERT INTO journal_drafts
                                (tenant_id, description, amount, currency, status,
                                 source_type, account_code, created_at)
                            VALUES (%s, %s, %s, 'GEL', 'auto_approved',
                                    'fx_revaluation', %s, NOW())
                        """),
                            tenant_id,
                            entry["description"],
                            entry["lines"][0]["debit"] or entry["lines"][1]["credit"],
                            entry["lines"][0]["account_code"],
                        )
                        posted_count += 1
                    except Exception as e:
                        log.warning("FX draft insert failed: %s", e)

    except Exception as e:
        return error_response("Revaluation failed", "FX_ERROR", str(e))

    total_gain = sum(r["difference_gel"] for r in fx_results if r["is_gain"])
    total_loss = sum(abs(r["difference_gel"]) for r in fx_results if not r["is_gain"])

    return ok_response("FX revaluation complete", {
        "revalue_date": revalue_date.isoformat(),
        "items_processed": len(fx_results),
        "total_fx_gain_gel": round(total_gain, 2),
        "total_fx_loss_gel": round(total_loss, 2),
        "net_gel": round(total_gain - total_loss, 2),
        "entries": journal_entries,
        "posted_count": posted_count,
    })


@router.get("/exposure")
async def get_fx_exposure(request: Request,
                          currency: Optional[str] = Query(None)):
    """Summary of all open foreign-currency positions (unpaid invoices, payables)."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    params: list = [tenant_id]
    cond = ""
    if currency:
        cond = "AND currency = %s"
        params.append(currency.upper())

    async with get_conn() as conn:
        rows = [dict(r) for r in await conn.fetch(_q(f"""
            SELECT currency,
                   COUNT(*) AS invoice_count,
                   SUM(total) AS total_foreign,
                   SUM(CASE WHEN original_rate > 0 THEN total * original_rate ELSE 0 END) AS booked_gel
            FROM invoices
            WHERE tenant_id = %s
              AND currency != 'GEL'
              AND status NOT IN ('paid', 'cancelled') {cond}
            GROUP BY currency
            ORDER BY booked_gel DESC
        """), *params)]
    for r in rows:
        for k in ("total_foreign", "booked_gel"):
            if r[k]:
                r[k] = float(r[k])

    return ok_response("FX exposure", {"positions": rows, "count": len(rows)})
