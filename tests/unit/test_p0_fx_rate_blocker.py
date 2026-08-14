"""tests/unit/test_p0_fx_rate_blocker.py
P0-4: Non-GEL posting must be blocked when FX rate is missing.
Tests are pure unit tests — DB and connector calls are mocked.
"""
import asyncio
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch


def run_sync(coro):
    return asyncio.run(coro)


def _make_draft(currency="USD", amount=1000.0, date="2026-08-14"):
    return {
        "id": 1,
        "tenant_id": "tenant1",
        "date": date,
        "description": "Test USD invoice",
        "partner": "Vendor A",
        "amount": amount,
        "currency": currency,
        "status": "approved",
        "lines_json": "[]",
        "lines": [],
    }


# ── _draft_to_posting_payload tests ──────────────────────────────────────────

def test_gel_draft_uses_1_0_rate():
    from app.api.services.posting_service import _draft_to_posting_payload
    draft = _make_draft(currency="GEL", amount=500.0)
    result = run_sync(_draft_to_posting_payload(draft))
    assert result["exchange_rate"] == 1.0
    assert result["amount_gel"] == 500.0


def test_non_gel_with_valid_rate_succeeds():
    from app.api.services.posting_service import _draft_to_posting_payload
    draft = _make_draft(currency="USD", amount=100.0)
    with patch("app.api.services.posting_service.get_rate_async" if False else
               "app.api.services.currency_service.get_rate_async",
               new=AsyncMock(return_value=Decimal("2.72"))):
        # patch within the module where it's imported lazily
        with patch("app.api.services.currency_service.get_rate_async",
                   new=AsyncMock(return_value=Decimal("2.72"))):
            result = run_sync(_draft_to_posting_payload(draft))
            assert result["exchange_rate"] == pytest.approx(2.72, rel=1e-4)
            assert result["amount_gel"] == pytest.approx(272.0, rel=1e-2)


def test_non_gel_missing_rate_raises_fx_error():
    from app.api.services.posting_service import _draft_to_posting_payload, FxRateMissingError
    draft = _make_draft(currency="USD", amount=100.0)
    with patch("app.api.services.currency_service.get_rate_async",
               new=AsyncMock(side_effect=Exception("rate not found in DB"))):
        with pytest.raises(FxRateMissingError) as exc_info:
            run_sync(_draft_to_posting_payload(draft))
        assert "USD" in str(exc_info.value)
        assert "GEL" in str(exc_info.value)


def test_eur_missing_rate_raises_fx_error():
    from app.api.services.posting_service import _draft_to_posting_payload, FxRateMissingError
    draft = _make_draft(currency="EUR", amount=200.0)
    with patch("app.api.services.currency_service.get_rate_async",
               new=AsyncMock(side_effect=ValueError("no rate"))):
        with pytest.raises(FxRateMissingError):
            run_sync(_draft_to_posting_payload(draft))


# ── apply_posting_service tests ───────────────────────────────────────────────

def _mock_conn_ctx(draft_row):
    """Returns a mock async context manager that yields a mock connection.
    fetchrow returns draft_row only for the initial draft fetch query;
    all other fetchrow calls (dup-check, posting_logs) return None.
    """
    mock_conn = AsyncMock()
    _call_count = [0]

    async def _smart_fetchrow(query, *args, **kwargs):
        q = str(query).lower()
        # The initial draft fetch selects specific columns; dup-check uses "id <>"
        if "id <>" in q or "posting_logs" in q:
            return None
        _call_count[0] += 1
        return draft_row

    mock_conn.fetchrow = _smart_fetchrow
    mock_conn.fetchval = AsyncMock(return_value=None)
    mock_conn.execute = AsyncMock()
    mock_tr = AsyncMock()
    mock_conn.transaction = MagicMock(return_value=mock_tr)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


_VALID_LINES_JSON = '[{"account_code":"1310","debit":500,"credit":0},{"account_code":"5210","debit":0,"credit":500}]'


def test_apply_posting_returns_fx_rate_missing_for_non_gel():
    from app.api.services.posting_service import apply_posting_service

    class _FakeRow:
        def __getitem__(self, k):
            data = {"id": 1, "tenant_id": "t1", "date": "2026-08-14",
                    "description": "USD test", "partner": "Corp",
                    "amount": 500.0, "status": "approved", "currency": "USD",
                    "lines_json": _VALID_LINES_JSON}
            return data[k]
        def __iter__(self):
            return iter({"id": 1, "tenant_id": "t1", "date": "2026-08-14",
                         "description": "USD test", "partner": "Corp",
                         "amount": 500.0, "status": "approved", "currency": "USD",
                         "lines_json": _VALID_LINES_JSON}.items())

    fake_row = _FakeRow()
    ctx = _mock_conn_ctx(fake_row)

    with patch("app.api.services.posting_service.get_conn", return_value=ctx), \
         patch("app.api.services.currency_service.get_rate_async",
               new=AsyncMock(side_effect=Exception("no FX rate"))):
        result = run_sync(apply_posting_service(1, "mock", tenant_id="t1"))

    assert result.get("ok") is False
    assert result.get("error", {}).get("code") == "FX_RATE_MISSING"


def test_apply_posting_does_not_call_connector_when_fx_missing():
    from app.api.services.posting_service import apply_posting_service

    class _FakeRow:
        def __getitem__(self, k):
            return {"id": 1, "tenant_id": "t1", "date": "2026-08-14",
                    "description": "EUR test", "partner": "Euro Corp",
                    "amount": 300.0, "status": "approved", "currency": "EUR",
                    "lines_json": _VALID_LINES_JSON}[k]

    ctx = _mock_conn_ctx(_FakeRow())

    connector_called = []

    def _fake_post_connector(target, payload, tenant_id):
        connector_called.append(True)
        return {"success": True}

    with patch("app.api.services.posting_service.get_conn", return_value=ctx), \
         patch("app.api.services.posting_service._post_via_connector", side_effect=_fake_post_connector), \
         patch("app.api.services.currency_service.get_rate_async",
               new=AsyncMock(side_effect=Exception("no EUR rate"))):
        run_sync(apply_posting_service(1, "mock", tenant_id="t1"))

    assert not connector_called, "Connector must not be called when FX rate is missing"


# ── FxRateMissingError class ──────────────────────────────────────────────────

def test_fx_rate_missing_error_is_value_error():
    from app.api.services.posting_service import FxRateMissingError
    assert issubclass(FxRateMissingError, ValueError)


def test_fx_rate_missing_error_message_contains_currency():
    from app.api.services.posting_service import FxRateMissingError
    err = FxRateMissingError("USD→GEL not found")
    assert "USD" in str(err)
