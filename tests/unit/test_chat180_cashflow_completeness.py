"""Incomplete official cashflow must not become an apparently complete zero."""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from app.api.services import financial_statements_service as statements
from app.api.services.cfo_dashboard_service import build_cfo_dashboard_from_data


@pytest.mark.asyncio
@pytest.mark.parametrize("category,complete", [(None, False), ("operating", True)])
async def test_unknown_cash_movement_does_not_publish_partial_official_total(monkeypatch, category, complete):
    rows = [{"line_id": "cash", "header_id": "header", "account_code": "1120", "account_type": "asset",
             "cashflow_category": category, "debit": 7, "credit": 0, "description": "private cash detail"},
            {"line_id": "counterpart", "header_id": "header", "account_code": "9999", "account_type": None,
             "cashflow_category": None, "debit": 0, "credit": 7, "description": "private counterpart"}]

    @asynccontextmanager
    async def connection():
        yield type("Connection", (), {"fetch": AsyncMock(return_value=rows)})()

    monkeypatch.setattr(statements, "get_conn", connection)
    result = await statements.build_cashflow_statement("t_alpha")
    assert result["ok"] is complete
    if complete:
        assert result["data"]["complete"] is True
        assert result["data"]["source"] == "posted_ledger"
        assert result["data"]["net_change_in_cash"] == 7
    else:
        assert result["data"] is None
        assert result["error"]["code"] == "CASHFLOW_CLASSIFICATION_INCOMPLETE"
        assert result["error"]["details"]["unclassified_cash_movements"] == 1
        assert "private" not in str(result)


def cashflow(value=0):
    return {"operating": {"net": value}, "investing": {"net": 0}, "financing": {"net": 0},
            "net_change_in_cash": value, "complete": True}


@pytest.mark.parametrize("payload", [None, {}, {"operating": {"net": 7}}, dict(cashflow(7), complete=False)])
def test_missing_or_incomplete_cashflow_has_null_kpis(payload):
    result = build_cfo_dashboard_from_data({"1120": 10}, {}, cashflow=payload)["cash_position"]
    assert result["available"] is True and result["total_liquid"] == 10
    assert result["cashflow_available"] is False
    for key in ["net_cashflow", "operating_cf", "investing_cf", "financing_cf"]:
        assert result[key] is None


@pytest.mark.parametrize("value", [True, "bad", float("nan"), float("inf"), None])
def test_invalid_cashflow_values_are_unavailable(value):
    result = build_cfo_dashboard_from_data({}, {}, cashflow=cashflow(value))["cash_position"]
    assert result["cashflow_available"] is False and result["net_cashflow"] is None


def test_complete_zero_cashflow_is_a_verified_zero():
    result = build_cfo_dashboard_from_data({}, {}, cashflow=cashflow())["cash_position"]
    assert result["cashflow_available"] is True and result["net_cashflow"] == 0
