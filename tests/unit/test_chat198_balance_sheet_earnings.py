"""FIN-08: unclosed income/expense belongs in equity, without a ledger plug."""
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.api.services import financial_statements_service as finance


def grouped(code, kind, debit=0, credit=0):
    return {"account_code": code, "account_type": kind,
            "total_debit": Decimal(str(debit)), "total_credit": Decimal(str(credit)),
            "fx_invalid_count": 0, "classification_invalid_count": 0}


@pytest.mark.asyncio
@pytest.mark.parametrize("posted", [True, False], ids=["posted-ledger", "legacy-gel"])
@pytest.mark.parametrize("revenue,expense,booked,assets,result", [
    (100, 30, 90, 160, 70),
    (20, 80, 90, 30, -60),
    (20, 20, 90, 90, 0),
    (0, 0, 160, 160, 0),  # already closed into retained earnings
    (60, 10, 130, 180, 50),  # partially closed: only remaining P&L added
])
async def test_unclosed_result_reconciles_equity_without_double_counting(
    monkeypatch, posted, revenue, expense, booked, assets, result,
):
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1" if posted else "0")
    rows = [grouped("1120", "asset", assets),
            grouped("4110", "equity", credit=50),
            grouped("4210", "equity", credit=booked - 50),
            grouped("6110", "income", credit=revenue),
            grouped("7210", "expense", debit=expense)]
    original = deepcopy(rows)
    conn = AsyncMock()
    conn.fetch.return_value = rows

    @asynccontextmanager
    async def connection():
        yield conn

    monkeypatch.setattr(finance, "get_conn", connection)
    monkeypatch.setattr(finance, "_get_trial_balance", AsyncMock(return_value={
        "1120": assets, "4110": -50, "4210": -(booked - 50),
        "6110": -revenue, "7210": expense,
    }))
    report = await finance.build_balance_sheet("t_alpha", "2026-10-31")
    assert report["ok"], report
    data = report["data"]
    assert data["assets"]["total"] == assets
    assert data["equity"]["total"] == assets
    assert data["equity"]["unclosed_result"] == result
    assert data["total_liabilities_and_equity"] == assets
    assert data["balanced"] is True
    derived = [line for line in data["equity"]["lines"] if line.get("derived")]
    assert len(derived) == bool(result)
    if derived:
        assert derived[0]["amount"] == result
        assert derived[0]["account_code"] is None  # presentation, no invented GL account
        assert derived[0]["line_type"] == "unclosed_result"
    assert rows == original
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("posted", [True, False])
async def test_one_cent_imbalance_is_exposed_and_never_used_as_profit(monkeypatch, posted):
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1" if posted else "0")
    conn = AsyncMock()
    conn.fetch.return_value = [grouped("1120", "asset", 100),
                              grouped("4110", "equity", credit=50),
                              grouped("6110", "income", credit="49.99")]

    @asynccontextmanager
    async def connection():
        yield conn

    monkeypatch.setattr(finance, "get_conn", connection)
    monkeypatch.setattr(finance, "_get_trial_balance", AsyncMock(return_value={
        "1120": 100, "4110": -50, "6110": -49.99,
    }))
    report = await finance.build_balance_sheet("t_alpha", "2026-10-31")
    assert report["ok"], report
    assert report["data"]["equity"]["unclosed_result"] == 49.99
    assert report["data"]["equity"]["total"] == 99.99
    assert report["data"]["balanced"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("posted", [True, False])
async def test_default_asof_bounds_the_same_date_shown_in_the_report(monkeypatch, posted):
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1" if posted else "0")
    conn = AsyncMock()
    conn.fetch.return_value = []

    @asynccontextmanager
    async def connection():
        yield conn

    legacy = AsyncMock(return_value={})
    monkeypatch.setattr(finance, "get_conn", connection)
    monkeypatch.setattr(finance, "_get_trial_balance", legacy)
    report = await finance.build_balance_sheet("t_alpha")
    assert report["ok"], report
    displayed = report["data"]["as_of"]
    if posted:
        assert conn.fetch.await_args.args[-1] == date.fromisoformat(displayed)
        assert "jeh.entry_date <= $3" in conn.fetch.await_args.args[0]
    else:
        legacy.assert_awaited_once_with("t_alpha", None, displayed)
