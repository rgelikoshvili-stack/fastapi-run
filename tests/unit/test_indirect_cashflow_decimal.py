"""Small indirect cashflows must survive offsetting large adjustments."""
from copy import deepcopy
from decimal import Decimal, localcontext
from itertools import permutations
import json

import pytest

from app.api.services.cashflow_classification_service import build_cashflow_indirect


@pytest.mark.parametrize("order", list(permutations(range(3))))
def test_working_capital_is_order_independent(order):
    values = (1_000_000_000_000_000.0, 0.01, -1_000_000_000_000_000.0)
    changes = {f"adjustment_{i}": values[i] for i in order}
    original = deepcopy(changes)
    result = build_cashflow_indirect(0, working_capital_changes=changes)
    assert result["operating_activities"]["working_capital_changes"]["total"] == 0.01
    assert result["operating_activities"]["net"] == 0.01
    assert result["net_change_in_cash"] == 0.01
    assert changes == original


@pytest.mark.parametrize("cent", [0.01, -0.01])
def test_operating_adjustments_keep_profit_residual(cent):
    result = build_cashflow_indirect(
        1_000_000_000_000_000.0, depreciation=cent,
        working_capital_changes={"change": -1_000_000_000_000_000.0},
    )
    assert result["operating_activities"]["net"] == cent
    assert result["net_change_in_cash"] == cent


@pytest.mark.parametrize("cent", [0.01, -0.01])
def test_activity_totals_keep_cash_change_residual(cent):
    result = build_cashflow_indirect(
        1_000_000_000_000_000.0, investing_net=cent,
        financing_net=-1_000_000_000_000_000.0,
    )
    assert result["net_change_in_cash"] == cent


def test_database_decimals_work_with_optional_defaults_and_json_response():
    result = build_cashflow_indirect(Decimal("10.01"), working_capital_changes={"receivables": Decimal("-10")})
    assert result["net_change_in_cash"] == 0.01
    assert json.loads(json.dumps(result))["net_change_in_cash"] == 0.01


def test_low_caller_precision_cannot_round_away_a_booked_cent():
    with localcontext() as context:
        context.prec = 8
        result = build_cashflow_indirect(
            Decimal("9007199254740992.01"),
            investing_net=Decimal("-9007199254740992.00"),
        )
    assert result["net_change_in_cash"] == 0.01
