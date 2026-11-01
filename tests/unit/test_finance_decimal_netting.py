"""Reported cents must survive large, offsetting booked turnovers.

Public JSON numbers stay compatible. This tests arithmetic before serialization,
not exact representation of an arbitrarily large final JSON float.
"""
from contextlib import asynccontextmanager
from decimal import Decimal, localcontext
from unittest.mock import AsyncMock

import pytest

from app.api.services import financial_statements_service as finance
from app.api.services import ledger_service as ledger


def row(code, kind, debit="0", credit="0"):
    return dict(account_code=code, account_type=kind,
                total_debit=Decimal(debit), total_credit=Decimal(credit),
                fx_invalid_count=0, classification_invalid_count=0)


def use_rows(monkeypatch, rows):
    conn = AsyncMock()
    conn.fetch.return_value = rows

    @asynccontextmanager
    async def connection():
        yield conn

    monkeypatch.setattr(finance, "get_conn", connection)
    monkeypatch.setattr(ledger, "get_conn", connection)
    return conn


@pytest.mark.parametrize("posted", [True, False])
@pytest.mark.parametrize("net", ["0.01", "-0.01", "7.13"])
async def test_small_net_survives_large_turnovers_in_pnl_and_equity(monkeypatch, posted, net):
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1" if posted else "0")
    base = Decimal("9007199254740992.00")
    end = base + Decimal(net)
    if posted:
        rows = [row("1120", "asset", str(end), str(base)),
                row("6110", "income", str(base), str(end))]
    else:
        rows = [dict(account_code=code, side=side, total=amount, fx_invalid_count=0)
                for code, side, amount in [("1120", "debit", end), ("1120", "credit", base),
                                           ("6110", "debit", base), ("6110", "credit", end)]]
    conn = use_rows(monkeypatch, rows)
    pnl = await finance.build_profit_and_loss("t_alpha", None, "2026-10-31")
    bs = await finance.build_balance_sheet("t_alpha", "2026-10-31")
    assert pnl["ok"] and bs["ok"]
    assert pnl["data"]["ebit"] == float(net)
    assert bs["data"]["assets"]["total"] == float(net)
    assert bs["data"]["equity"]["unclosed_result"] == float(net)
    assert bs["data"]["balanced"] is True
    conn.execute.assert_not_awaited()


async def test_cfo_trial_balance_nets_numeric_before_float(monkeypatch):
    use_rows(monkeypatch, [row("1120", "asset", "9007199254740992.01", "9007199254740992.00")])
    balances = await finance._get_posted_trial_balance_as_of("t_alpha", "2026-10-31")
    assert balances == {"1120": 0.01}


@pytest.mark.parametrize("posted", [True, False])
async def test_trial_balance_retains_net_and_exposes_one_cent_difference(monkeypatch, posted):
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1" if posted else "0")
    if posted:
        rows = [row("1120", "asset", "9007199254740992.01", "9007199254740992.00")]
    else:
        rows = [dict(account_code="1120", side=side, bucket="period", total=Decimal(amount),
                     fx_invalid_count=0)
                for side, amount in [("debit", "9007199254740992.01"),
                                     ("credit", "9007199254740992.00")]]
    use_rows(monkeypatch, rows)
    result = await ledger.get_trial_balance("t_alpha", None, "2026-10-31")
    assert result["accounts"][0]["net"] == 0.01
    assert result["accounts"][0]["closing_balance"] == 0.01
    assert result["closing_total"] == 0.01
    assert result["balanced"] is False


async def test_pnl_keeps_small_profit_after_large_revenue_minus_cost(monkeypatch):
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1")
    use_rows(monkeypatch, [row("6110", "income", credit="9007199254740992.01"),
                          row("7110", "expense", debit="9007199254740992.00")])
    result = await finance.build_profit_and_loss("t_alpha")
    assert result["ok"]
    assert result["data"]["gross_profit"] == 0.01
    assert result["data"]["ebit"] == 0.01


async def test_balance_sheet_uses_exact_equation_before_json_numbers(monkeypatch):
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1")
    use_rows(monkeypatch, [row("1120", "asset", debit="9007199254740992.01"),
                          row("4110", "equity", credit="9007199254740992.00")])
    result = await finance.build_balance_sheet("t_alpha", "2026-10-31")
    assert result["ok"]
    assert result["data"]["balanced"] is False


@pytest.mark.parametrize("reverse_order", [False, True])
async def test_offsetting_asset_lines_sum_without_float_or_context_loss(monkeypatch, reverse_order):
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1")
    rows = [row("1110", "asset", debit="9007199254740992.01"),
            row("1120", "asset", credit="9007199254740992.00"),
            row("4110", "equity", credit="0.01")]
    use_rows(monkeypatch, list(reversed(rows)) if reverse_order else rows)
    with localcontext() as context:
        context.prec = 8
        result = await finance.build_balance_sheet("t_alpha", "2026-10-31")
    assert result["ok"]
    assert result["data"]["assets"]["total"] == 0.01
    assert result["data"]["balanced"] is True


@pytest.mark.parametrize("expense_account", ["7210", "1510"])
@pytest.mark.parametrize("net", ["0.01", "-0.01"])
def test_direct_cashflow_retains_net_across_categories(expense_account, net):
    from app.api.services.cashflow_classification_service import build_cashflow_direct

    base = Decimal("9007199254740992.00")
    result = build_cashflow_direct([
        {"dr": "1120", "cr": "6110", "amount": base + Decimal(net)},
        {"dr": expense_account, "cr": "1120", "amount": base},
    ])
    assert result["net_change_in_cash"] == float(net)


def test_posted_cashflow_does_not_hide_a_cent_as_internal_transfer():
    from app.api.services.cashflow_classification_service import build_cashflow_from_posted_ledger_rows

    result = build_cashflow_from_posted_ledger_rows([
        dict(header_id="a", account_code="1110", account_type="asset",
             debit=Decimal("9007199254740992.01"), credit=0),
        dict(header_id="a", account_code="1120", account_type="asset",
             debit=0, credit=Decimal("9007199254740992.00")),
    ])
    assert result["unknown"]["lines"]
    assert result["internal_transfers"]["amount"] == 0
