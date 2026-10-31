"""FIN-05: functional GEL totals and original posting FX must be trustworthy."""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("currency,rate,lines,code", [
    ("GEL", "2", [{"account_code": "1120", "debit": ".02"}, {"account_code": "6110", "credit": ".02"}], "FX_RATE_INVALID"),
    ("USD", ".5", [{"account_code": "1120", "debit": ".02"}, {"account_code": "6110", "credit": ".01"}, {"account_code": "6120", "credit": ".01"}], "LEDGER_FUNCTIONAL_UNBALANCED"),
])
async def test_writer_rejects_false_gel_rate_and_rounded_functional_imbalance(currency, rate, lines, code):
    from app.api.services.posting_service import _write_ledger_entries
    conn = AsyncMock()
    conn.is_in_transaction = lambda: True
    conn.fetchval.side_effect = [None, uuid4()]
    draft = {"id": "fin05-synthetic", "date": "2026-10-29", "currency": currency, "lines": lines}
    with pytest.raises(ValueError, match=code):
        await _write_ledger_entries(conn, draft, {"exchange_rate": rate}, "t_alpha", "test", "hash")
    assert not any("INSERT" in call.args[0] for call in conn.fetchval.call_args_list)
    assert not any("INSERT" in call.args[0] for call in conn.execute.call_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("reader", ["pnl", "balance", "cashflow", "trial", "asof"])
async def test_invalid_functional_basis_never_publishes_partial_official_totals(monkeypatch, reader):
    from app.api.services import financial_statements_service as finance, ledger_service as ledger
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1")
    bad_row = {"account_code": "1120", "account_type": "asset", "total_debit": 100, "total_credit": 0,
               "debit": 100, "credit": 0, "cashflow_category": "operating", "description": "private",
               "line_id": "line", "header_id": "header", "fx_invalid_count": 1}
    @asynccontextmanager
    async def connection():
        conn = AsyncMock()
        conn.fetch.return_value = [bad_row]
        yield conn
    monkeypatch.setattr(finance, "get_conn", connection)
    monkeypatch.setattr(ledger, "get_conn", connection)
    if reader == "asof":
        with pytest.raises(ValueError, match="POSTED_LEDGER_FX_INVALID"):
            await finance._get_posted_trial_balance_as_of("t_alpha", None)
    else:
        result = await {"pnl": finance.build_profit_and_loss, "balance": finance.build_balance_sheet,
                        "cashflow": finance.build_cashflow_statement, "trial": ledger.get_trial_balance}[reader]("t_alpha")
        code = result.get("error") if reader == "trial" else result["error"]["code"]
        assert code == "POSTED_LEDGER_FX_INVALID"
        assert "private" not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("reader", ["pnl", "balance", "trial", "account", "counterparty", "payroll"])
async def test_legacy_foreign_amounts_are_unavailable_without_booked_fx(monkeypatch, reader):
    from app.api.services import financial_statements_service as finance, ledger_service as ledger
    monkeypatch.delenv("POSTED_LEDGER_REPORTS_ENABLED", raising=False)
    bad_row = {"account_code": "1120", "side": "debit", "total": 100, "bucket": "period",
               "dr": "1120", "cr": "6110", "amount": 100, "fx_invalid_count": 1}
    @asynccontextmanager
    async def connection():
        conn = AsyncMock()
        conn.fetch.return_value = [bad_row]
        yield conn
    monkeypatch.setattr(finance, "get_conn", connection)
    monkeypatch.setattr(ledger, "get_conn", connection)
    args = ("t_alpha", "1120") if reader == "account" else (("t_alpha", "test-inn") if reader == "counterparty" else ("t_alpha",))
    result = await {"pnl": finance.build_profit_and_loss, "balance": finance.build_balance_sheet,
                    "trial": ledger.get_trial_balance, "account": ledger.get_account_ledger,
                    "counterparty": ledger.get_counterparty_ledger, "payroll": ledger.get_payroll_ledger}[reader](*args)
    code = result["error"]["code"] if reader in {"pnl", "balance"} else result["error"]
    assert code == "LEGACY_FX_UNAVAILABLE"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing", "outage", "invalid"])
async def test_posting_payload_never_uses_static_rate_fallback(monkeypatch, failure):
    from app.api.services import currency_service as currency, posting_service as posting
    @asynccontextmanager
    async def connection():
        if failure == "outage":
            raise RuntimeError("synthetic DB unavailable")
        conn = AsyncMock()
        conn.fetchrow.return_value = {"rate": "NaN"} if failure == "invalid" else None
        yield conn
    monkeypatch.setattr(currency, "get_conn", connection)
    draft={"id": "synthetic-fx", "currency":"USD", "amount":"100", "date":"2026-10-29", "lines":[]}
    with pytest.raises(posting.FxRateMissingError):
        await posting._draft_to_posting_payload(draft)


@pytest.mark.asyncio
async def test_payload_requests_nonestimated_rate_and_preserves_eight_decimal_places(monkeypatch):
    from decimal import Decimal
    from app.api.services import currency_service as currency, posting_service as posting
    quote=AsyncMock(return_value=Decimal("2.12345678"))
    monkeypatch.setattr(currency,"get_rate_async",quote)
    payload=await posting._draft_to_posting_payload({"id":"fx181","date":"2026-10-29",
        "currency":"USD","amount":"100","lines":[]})
    quote.assert_awaited_once_with("USD","GEL","2026-10-29",allow_fallback=False)
    assert payload["exchange_rate_exact"]=="2.12345678"
    assert payload["exchange_rate"]==2.12345678 and payload["amount_gel"]==212.35


@pytest.mark.asyncio
@pytest.mark.parametrize("day", [None,"not-a-date","2026-02-30"])
async def test_strict_quote_rejects_missing_or_invalid_date_before_io(monkeypatch,day):
    from unittest.mock import Mock
    from app.api.services import currency_service as currency
    opened=Mock(side_effect=AssertionError("must validate date before DB"))
    monkeypatch.setattr(currency,"get_conn",opened)
    with pytest.raises(currency.CurrencyRateNotFound):
        await currency.get_rate_async("USD","GEL",day,allow_fallback=False)
    opened.assert_not_called()
