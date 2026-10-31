"""FIN-05: reviewed, as-of dated NBG quote evidence for financial operations.

Legacy exchange_rates is a mutable latest-snapshot/preview cache; it does not
prove original publication date or approval. Posting and revaluation must not
accept that cache as official accounting evidence. This uses a separate,
unregistered Draft migration; without reviewed quotes it fails CLOSED.
The source hash is reviewer-attested, not independently provider-verified here.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal, DecimalException, ROUND_HALF_UP, localcontext
from uuid import UUID

from app.api.db import _q, get_conn

MAX_QUOTE_AGE_DAYS = 7
_RATE_MAX = Decimal("9999999999.99999999")
_RATE_SCALE = Decimal("0.00000001")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class FxQuoteUnverified(ValueError):
    """No complete and uniquely reviewed NBG evidence for the requested date."""


def _reject() -> None:
    raise FxQuoteUnverified("FX_QUOTE_UNVERIFIED")


def _booking_date(value) -> date:
    if isinstance(value, datetime):
        _reject()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or len(value) != 10:
        _reject()
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        _reject()


def _decimal(value) -> Decimal:
    try:
        result = Decimal(str(value))
        if not result.is_finite() or not (Decimal(0) < result <= _RATE_MAX):
            _reject()
        return result
    except (DecimalException, TypeError, ValueError):
        _reject()


def _validated_quote(row, currency: str, booked: date) -> dict:
    try:
        data = dict(row)
        quote_id = UUID(str(data["id"]))
        effective = data["effective_date"]
        published = data["published_date"]
        approved = data["approved_at"]
        retrieved = data["retrieved_at"]
        if (
            data["currency"] != currency or data["base_currency"] != "GEL"
            or data["source_provider"] != "NBG"
            or not isinstance(effective, date) or isinstance(effective, datetime)
            or not isinstance(published, date) or isinstance(published, datetime)
            or not isinstance(approved, datetime) or approved.tzinfo is None
            or not isinstance(retrieved, datetime) or retrieved.tzinfo is None
            or not (booked - timedelta(days=MAX_QUOTE_AGE_DAYS) <= effective <= booked)
            or not (published <= effective <= published + timedelta(days=7))
            or retrieved.date() < published
            or approved < retrieved
            or not isinstance(data.get("approved_by"), str) or not data["approved_by"].strip()
            or not isinstance(data.get("source_revision"), str) or not data["source_revision"].strip()
            or not isinstance(data.get("source_payload_sha256"), str)
            or not _SHA256.fullmatch(data["source_payload_sha256"])
        ):
            _reject()
        raw = _decimal(data["raw_rate"])
        quantity = _decimal(data["quantity"])
        rate = _decimal(data["rate_to_gel"])
        if quantity != quantity.to_integral_value():
            _reject()
        with localcontext() as ctx:
            ctx.prec = 50
            if (raw / quantity).quantize(_RATE_SCALE, ROUND_HALF_UP) != rate:
                _reject()
        return {
            "quote_id": str(quote_id), "rate": rate,
            "currency": currency, "source_provider": "NBG",
            "source_revision": data["source_revision"],
            "source_payload_sha256": data["source_payload_sha256"],
            "effective_date": effective, "published_date": published,
        }
    except (KeyError, TypeError, AttributeError, DecimalException):
        _reject()


async def get_verified_quote_on_conn(conn, currency: str, for_date) -> dict:
    """Read the latest valid-dated quote; refuse all ambiguous latest revisions.

    The query does NOT filter out bad/unapproved latest rows to avoid silently
    substituting an older approved rate for an invalid latest publication.
    """
    booked = _booking_date(for_date)
    if not isinstance(currency, str):
        _reject()
    code = currency.strip().upper()
    if not _CURRENCY.fullmatch(code) or code == "GEL":
        _reject()
    try:
        rows = await conn.fetch(_q("""
            SELECT id, currency, base_currency, source_provider,
                   source_revision, source_payload_sha256, effective_date,
                   published_date, retrieved_at, approved_by, approved_at,
                   raw_rate, quantity, rate_to_gel
              FROM fx_verified_quotes
             WHERE currency = %s AND effective_date <= %s
               AND effective_date >= %s
             ORDER BY effective_date DESC, id
             LIMIT 2
        """), code, booked, booked - timedelta(days=MAX_QUOTE_AGE_DAYS))
    except Exception:
        _reject()
    if not rows:
        _reject()
    try:
        if len(rows) > 1 and rows[0]["effective_date"] == rows[1]["effective_date"]:
            _reject()
    except (KeyError, TypeError, AttributeError):
        _reject()
    return _validated_quote(rows[0], code, booked)


async def get_verified_quote_async(currency: str, for_date) -> dict:
    """Fetch only reviewed quote evidence; never make a provider/network call."""
    booked = _booking_date(for_date)  # Validate BEFORE DB access.
    try:
        async with get_conn() as conn:
            return await get_verified_quote_on_conn(conn, currency, booked)
    except FxQuoteUnverified:
        raise
    except Exception:
        _reject()
