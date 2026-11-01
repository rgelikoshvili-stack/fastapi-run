"""Chat184 FIN-05 source/date gate: record regressions before implementation.

All fixtures are synthetic; no live NBG/network/Cloud SQL or Production.
"""
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest


def sample_quote(**changes):
    row = {
        "id": "00000000-0000-0000-0000-000000000184",
        "currency": "USD", "base_currency": "GEL",
        "source_provider": "NBG", "source_revision": "synthetic-publication",
        "source_payload_sha256": "a" * 64, "effective_date": date(2026, 10, 15),
        "published_date": date(2026, 10, 14),
        "retrieved_at": datetime(2026, 10, 14, 14, tzinfo=timezone.utc),
        "approved_by": "independent-reviewer",
        "approved_at": datetime(2026, 10, 15, 8, tzinfo=timezone.utc),
        "raw_rate": Decimal("2.12345678"), "quantity": Decimal("1"),
        "rate_to_gel": Decimal("2.12345678"),
    }
    row.update(changes)
    return row


@pytest.mark.asyncio
async def test_strict_posting_rejects_legacy_rate_without_verifiable_provenance(monkeypatch):
    from app.api.services import currency_service as currency
    conn = AsyncMock()
    conn.fetchrow.return_value = {"rate": Decimal("2.72")}
    conn.fetch.return_value = []
    @asynccontextmanager
    async def scoped():
        yield conn
    monkeypatch.setattr(currency, "get_conn", scoped)
    with pytest.raises(currency.CurrencyRateNotFound):
        await currency.get_rate_async("USD", "GEL", "2026-10-15", allow_fallback=False)


@pytest.mark.asyncio
async def test_verified_quote_has_original_source_date_and_exact_decimal(monkeypatch):
    from app.api.services.verified_fx_quote_service import get_verified_quote_async
    from app.api.services import verified_fx_quote_service as svc
    conn = AsyncMock()
    conn.fetch.return_value = [sample_quote()]
    @asynccontextmanager
    async def scoped():
        yield conn
    monkeypatch.setattr(svc, "get_conn", scoped)
    quote = await get_verified_quote_async("USD", "2026-10-15")
    assert quote["rate"] == Decimal("2.12345678")
    assert quote["source_provider"] == "NBG"
    assert quote["effective_date"] == date(2026, 10, 15)
    assert quote["source_payload_sha256"] == "a" * 64
    assert "fx_verified_quotes" in conn.fetch.call_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("rows", [
    [], [sample_quote(source_provider="manual")],
    [sample_quote(source_payload_sha256="no-evidence")],
    [sample_quote(approved_at=None)],
    [sample_quote(approved_by="")],
    [sample_quote(effective_date=date(2026, 10, 16))],
    [sample_quote(effective_date=date(2026, 10, 6), published_date=date(2026, 10, 5))],
    [sample_quote(published_date=date(2026, 10, 16))],
    [sample_quote(rate_to_gel=Decimal("NaN"))],
    [sample_quote(rate_to_gel=Decimal("2.20"))],
    [sample_quote(), sample_quote(id="00000000-0000-0000-0000-000000000185",
                                  source_revision="other-synthetic")],
])
async def test_missing_unverified_stale_ambiguous_or_bad_quote_never_posts(monkeypatch, rows):
    from app.api.services import verified_fx_quote_service as svc
    conn = AsyncMock()
    conn.fetch.return_value = rows
    @asynccontextmanager
    async def scoped():
        yield conn
    monkeypatch.setattr(svc, "get_conn", scoped)
    with pytest.raises(svc.FxQuoteUnverified):
        await svc.get_verified_quote_async("USD", "2026-10-15")


@pytest.mark.asyncio
async def test_revaluation_rate_is_asof_date_not_latest_unbounded_row():
    from app.api.services import fx_service
    conn = AsyncMock()
    conn.fetchrow.return_value = {"rate": Decimal("2.72")}
    conn.fetch.return_value = []
    with pytest.raises(Exception):
        await fx_service._get_rate_conn(conn, "USD", date(2026, 10, 15))


@pytest.mark.asyncio
async def test_missing_quote_fails_entire_revaluation_instead_of_partial_report(monkeypatch):
    from app.api.services import fx_service
    conn = AsyncMock()
    conn.fetch.return_value = [{
        "id": 17, "currency": "USD", "total": Decimal("100"),
        "original_rate": Decimal("2.50"), "account_code": "1120",
    }]
    @asynccontextmanager
    async def scoped():
        yield conn
    monkeypatch.setattr(fx_service, "get_conn", scoped)
    monkeypatch.setattr(fx_service, "_get_rate_conn", AsyncMock(return_value=None))
    with pytest.raises(Exception):
        await fx_service.revalue_open_items("t_alpha", date(2026, 10, 15))
