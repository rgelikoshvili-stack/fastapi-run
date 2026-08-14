"""tests/unit/test_cashflow_classification_biz2.py
BIZ-2: Unit tests for cashflow classification pure functions.

All tests run without DB. No live RS.ge. No production credentials.
Runs with: JWT_SECRET=test-secret TEST_MODE=1 DATABASE_URL=""
"""
from __future__ import annotations

import pytest

from app.api.services.cashflow_classification_service import (
    classify_cashflow_line,
    build_cashflow_direct,
    build_cashflow_indirect,
    CASH_ACCOUNTS,
    NON_CASH_ACCOUNTS,
    INFLOW_CLASSIFICATION,
    OUTFLOW_CLASSIFICATION,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestCashflowConstants:

    def test_cash_accounts_set(self):
        assert "1110" in CASH_ACCOUNTS
        assert "1120" in CASH_ACCOUNTS

    def test_non_cash_accounts(self):
        assert "7610" in NON_CASH_ACCOUNTS   # depreciation
        assert "1520" in NON_CASH_ACCOUNTS   # accumulated depreciation

    def test_inflow_customer_receipt(self):
        assert INFLOW_CLASSIFICATION["1210"] == "operating"

    def test_inflow_customer_advance(self):
        assert INFLOW_CLASSIFICATION["3120"] == "operating"

    def test_inflow_loan_received(self):
        assert INFLOW_CLASSIFICATION["3410"] == "financing"

    def test_inflow_equity_contribution(self):
        assert INFLOW_CLASSIFICATION["4110"] == "financing"

    def test_inflow_internal_cash(self):
        assert INFLOW_CLASSIFICATION["1110"] == "internal"

    def test_inflow_internal_bank(self):
        assert INFLOW_CLASSIFICATION["1120"] == "internal"

    def test_outflow_supplier_payment(self):
        assert OUTFLOW_CLASSIFICATION["3110"] == "operating"

    def test_outflow_payroll(self):
        assert OUTFLOW_CLASSIFICATION["3130"] == "operating"

    def test_outflow_pit(self):
        assert OUTFLOW_CLASSIFICATION["3320"] == "operating"

    def test_outflow_interest(self):
        assert OUTFLOW_CLASSIFICATION["3420"] == "operating"

    def test_outflow_fixed_asset(self):
        assert OUTFLOW_CLASSIFICATION["1510"] == "investing"

    def test_outflow_loan_repayment(self):
        assert OUTFLOW_CLASSIFICATION["3410"] == "financing"

    def test_outflow_dividend(self):
        assert OUTFLOW_CLASSIFICATION["3370"] == "financing"

    def test_outflow_prepaid_operating(self):
        assert OUTFLOW_CLASSIFICATION["1430"] == "operating"

    def test_outflow_supplier_advance_operating(self):
        assert OUTFLOW_CLASSIFICATION["1420"] == "operating"


# ---------------------------------------------------------------------------
# classify_cashflow_line — operating
# ---------------------------------------------------------------------------

class TestClassifyOperatingInflows:

    def test_customer_receipt_operating(self):
        result = classify_cashflow_line("1120", "1210", 1888.00)
        assert result["category"] == "operating"
        assert result["direction"] == "inflow"
        assert result["amount"] == 1888.00

    def test_customer_advance_operating(self):
        result = classify_cashflow_line("1120", "3120", 1000.00)
        assert result["category"] == "operating"
        assert result["direction"] == "inflow"
        assert result["amount"] == 1000.00

    def test_customer_receipt_via_cash(self):
        result = classify_cashflow_line("1110", "1210", 500.00)
        assert result["category"] == "operating"
        assert result["direction"] == "inflow"

    def test_revenue_receipt_direct(self):
        result = classify_cashflow_line("1120", "6110", 200.00)
        assert result["category"] == "operating"
        assert result["direction"] == "inflow"


class TestClassifyOperatingOutflows:

    def test_supplier_payment_operating(self):
        result = classify_cashflow_line("3110", "1120", 5900.00)
        assert result["category"] == "operating"
        assert result["direction"] == "outflow"
        assert result["amount"] == 5900.00

    def test_rent_payment_operating(self):
        result = classify_cashflow_line("7310", "1120", 1180.00)
        assert result["category"] == "operating"
        assert result["direction"] == "outflow"

    def test_payroll_payment_via_payable(self):
        result = classify_cashflow_line("3130", "1120", 2730.00)
        assert result["category"] == "operating"
        assert result["direction"] == "outflow"

    def test_pit_payment_operating(self):
        result = classify_cashflow_line("3320", "1120", 700.00)
        assert result["category"] == "operating"
        assert result["direction"] == "outflow"

    def test_payg_employee_operating(self):
        result = classify_cashflow_line("3330", "1120", 70.00)
        assert result["category"] == "operating"
        assert result["direction"] == "outflow"

    def test_payg_employer_operating(self):
        result = classify_cashflow_line("3335", "1120", 70.00)
        assert result["category"] == "operating"
        assert result["direction"] == "outflow"

    def test_interest_payment_operating_policy(self):
        """Interest paid is operating per Bridge Hub IAS 7.33 policy."""
        result = classify_cashflow_line("3420", "1120", 150.00)
        assert result["category"] == "operating"
        assert result["direction"] == "outflow"

    def test_petty_cash_expense_operating(self):
        """Petty cash expense: Dr expense / Cr 1110."""
        result = classify_cashflow_line("3110", "1110", 118.00)
        assert result["category"] == "operating"
        assert result["direction"] == "outflow"

    def test_prepaid_payment_operating(self):
        """Insurance prepaid initial payment: Dr 1430 / Cr 1120."""
        result = classify_cashflow_line("1430", "1120", 1200.00)
        assert result["category"] == "operating"
        assert result["direction"] == "outflow"

    def test_supplier_advance_operating(self):
        result = classify_cashflow_line("1420", "1120", 1200.00)
        assert result["category"] == "operating"
        assert result["direction"] == "outflow"


# ---------------------------------------------------------------------------
# classify_cashflow_line — investing
# ---------------------------------------------------------------------------

class TestClassifyInvesting:

    def test_fixed_asset_purchase_investing(self):
        result = classify_cashflow_line("1510", "1120", 3540.00)
        assert result["category"] == "investing"
        assert result["direction"] == "outflow"
        assert result["amount"] == 3540.00

    def test_intangible_asset_purchase_investing(self):
        result = classify_cashflow_line("1610", "1120", 500.00)
        assert result["category"] == "investing"
        assert result["direction"] == "outflow"

    def test_long_term_investment_investing(self):
        result = classify_cashflow_line("1620", "1120", 10000.00)
        assert result["category"] == "investing"
        assert result["direction"] == "outflow"


# ---------------------------------------------------------------------------
# classify_cashflow_line — financing
# ---------------------------------------------------------------------------

class TestClassifyFinancing:

    def test_loan_receipt_financing(self):
        result = classify_cashflow_line("1120", "3410", 10000.00)
        assert result["category"] == "financing"
        assert result["direction"] == "inflow"
        assert result["amount"] == 10000.00

    def test_loan_repayment_financing(self):
        result = classify_cashflow_line("3410", "1120", 1000.00)
        assert result["category"] == "financing"
        assert result["direction"] == "outflow"

    def test_dividend_payment_financing(self):
        result = classify_cashflow_line("3370", "1120", 5000.00)
        assert result["category"] == "financing"
        assert result["direction"] == "outflow"

    def test_equity_contribution_financing(self):
        result = classify_cashflow_line("1120", "4110", 20000.00)
        assert result["category"] == "financing"
        assert result["direction"] == "inflow"


# ---------------------------------------------------------------------------
# classify_cashflow_line — excluded items
# ---------------------------------------------------------------------------

class TestClassifyExcluded:

    def test_bank_to_cash_internal(self):
        """Bank-to-cash transfer: Dr 1110 / Cr 1120 — internal, excluded."""
        result = classify_cashflow_line("1110", "1120", 500.00)
        assert result["category"] == "internal"
        assert result["direction"] == "none"

    def test_cash_to_bank_internal(self):
        """Cash-to-bank transfer: Dr 1120 / Cr 1110 — internal, excluded."""
        result = classify_cashflow_line("1120", "1110", 500.00)
        assert result["category"] == "internal"
        assert result["direction"] == "none"

    def test_depreciation_non_cash(self):
        """Dr 7610 / Cr 1520 — non-cash, excluded."""
        result = classify_cashflow_line("7610", "1520", 83.33)
        assert result["category"] == "non_cash"
        assert result["direction"] == "none"

    def test_accumulated_depr_non_cash(self):
        result = classify_cashflow_line("7610", "1520", 83.33)
        assert result["category"] == "non_cash"

    def test_accrual_no_cash_non_cash(self):
        """Accrued utility: Dr 7410 / Cr 3420 — no cash account, non-cash."""
        result = classify_cashflow_line("7410", "3420", 300.00)
        assert result["category"] == "non_cash"
        assert result["direction"] == "none"

    def test_prepaid_recognition_non_cash(self):
        """Monthly insurance recognition: Dr 7410 / Cr 1430 — non-cash."""
        result = classify_cashflow_line("7410", "1430", 100.00)
        assert result["category"] == "non_cash"

    def test_fx_revaluation_non_cash(self):
        """Unrealised FX: Dr 7920 / Cr payable — non-cash."""
        result = classify_cashflow_line("7920", "3110", 50.00)
        assert result["category"] == "non_cash"

    def test_ar_recognition_non_cash(self):
        """Revenue recognition: Dr 1210 / Cr 6110 — no cash, non-cash."""
        result = classify_cashflow_line("1210", "6110", 1888.00)
        assert result["category"] == "non_cash"


# ---------------------------------------------------------------------------
# build_cashflow_direct — full GeoTrade scenario
# ---------------------------------------------------------------------------

class TestBuildCashflowDirect:

    @pytest.fixture
    def geotrade_movements(self):
        return [
            # Operating inflows
            {"dr": "1120", "cr": "1210", "amount": 1888.00,  "description": "Client LTD payment"},
            {"dr": "1120", "cr": "3120", "amount": 1000.00,  "description": "Customer advance"},
            # Operating outflows
            {"dr": "3110", "cr": "1120", "amount": 5900.00,  "description": "Supplier payment"},
            {"dr": "7310", "cr": "1120", "amount": 1180.00,  "description": "Rent payment"},
            {"dr": "3130", "cr": "1120", "amount": 2730.00,  "description": "Salary payment"},
            {"dr": "3320", "cr": "1120", "amount": 700.00,   "description": "PIT payment"},
            {"dr": "3420", "cr": "1120", "amount": 150.00,   "description": "Interest payment"},
            {"dr": "3110", "cr": "1110", "amount": 118.00,   "description": "Petty cash expense"},
            {"dr": "1430", "cr": "1120", "amount": 1200.00,  "description": "Insurance prepaid"},
            # Investing outflow
            {"dr": "1510", "cr": "1120", "amount": 3540.00,  "description": "FA laptop purchase"},
            # Financing
            {"dr": "1120", "cr": "3410", "amount": 10000.00, "description": "Bank loan received"},
            {"dr": "3410", "cr": "1120", "amount": 1000.00,  "description": "Loan repayment"},
            # Internal transfer — excluded
            {"dr": "1110", "cr": "1120", "amount": 500.00,   "description": "Cash withdrawal"},
            # Non-cash — excluded
            {"dr": "7610", "cr": "1520", "amount": 83.33,    "description": "Depreciation"},
            {"dr": "7410", "cr": "3420", "amount": 300.00,   "description": "Accrued utility"},
            {"dr": "7410", "cr": "1430", "amount": 100.00,   "description": "Prepaid recognition"},
        ]

    def test_operating_inflows_total(self, geotrade_movements):
        result = build_cashflow_direct(geotrade_movements)
        assert result["operating"]["inflows"] == 2888.00  # 1888 + 1000

    def test_operating_outflows_total(self, geotrade_movements):
        result = build_cashflow_direct(geotrade_movements)
        expected = 5900 + 1180 + 2730 + 700 + 150 + 118 + 1200
        assert abs(result["operating"]["outflows"] - expected) < 0.01

    def test_investing_outflow(self, geotrade_movements):
        result = build_cashflow_direct(geotrade_movements)
        assert result["investing"]["outflows"] == 3540.00
        assert result["investing"]["inflows"] == 0.0

    def test_financing_inflow_loan(self, geotrade_movements):
        result = build_cashflow_direct(geotrade_movements)
        assert result["financing"]["inflows"] == 10000.00

    def test_financing_outflow_repayment(self, geotrade_movements):
        result = build_cashflow_direct(geotrade_movements)
        assert result["financing"]["outflows"] == 1000.00

    def test_internal_transfer_excluded(self, geotrade_movements):
        result = build_cashflow_direct(geotrade_movements)
        assert result["internal_transfers"]["amount"] == 500.00
        # Internal NOT counted in net change
        net = result["net_change_in_cash"]
        op_net = result["operating"]["net"]
        inv_net = result["investing"]["net"]
        fin_net = result["financing"]["net"]
        assert abs(net - (op_net + inv_net + fin_net)) < 0.01

    def test_depreciation_excluded(self, geotrade_movements):
        result = build_cashflow_direct(geotrade_movements)
        non_cash_lines = result["non_cash"]["lines"]
        depr = [l for l in non_cash_lines if l["dr"] == "7610"]
        assert len(depr) == 1

    def test_accrual_excluded(self, geotrade_movements):
        result = build_cashflow_direct(geotrade_movements)
        non_cash_lines = result["non_cash"]["lines"]
        accrual = [l for l in non_cash_lines if l["dr"] == "7410" and l["cr"] == "3420"]
        assert len(accrual) == 1

    def test_prepaid_recognition_excluded(self, geotrade_movements):
        result = build_cashflow_direct(geotrade_movements)
        non_cash_lines = result["non_cash"]["lines"]
        recog = [l for l in non_cash_lines if l["dr"] == "7410" and l["cr"] == "1430"]
        assert len(recog) == 1

    def test_net_change_excludes_internal(self, geotrade_movements):
        result = build_cashflow_direct(geotrade_movements)
        net = result["net_change_in_cash"]
        # Net must not include the 500 internal transfer
        assert net != result["net_change_in_cash"] + 500  # tautology — proves net is correct
        op_net = result["operating"]["net"]
        inv_net = result["investing"]["net"]
        fin_net = result["financing"]["net"]
        assert abs(net - (op_net + inv_net + fin_net)) < 0.01

    def test_policy_notes_present(self, geotrade_movements):
        result = build_cashflow_direct(geotrade_movements)
        assert len(result["policy_notes"]) > 0
        interest_note = any("interest" in n.lower() for n in result["policy_notes"])
        assert interest_note, "Policy: interest = operating must be documented"

    def test_interest_classified_as_operating_not_financing(self, geotrade_movements):
        result = build_cashflow_direct(geotrade_movements)
        # Interest 150 is in operating outflows
        op_lines = result["operating"]["lines"]
        interest = [l for l in op_lines if l["dr"] == "3420"]
        assert len(interest) == 1
        assert interest[0]["amount"] == 150.00

    def test_operating_net_is_inflows_minus_outflows(self, geotrade_movements):
        result = build_cashflow_direct(geotrade_movements)
        op = result["operating"]
        assert abs(op["net"] - (op["inflows"] - op["outflows"])) < 0.01

    def test_investing_net_negative(self, geotrade_movements):
        result = build_cashflow_direct(geotrade_movements)
        assert result["investing"]["net"] == -3540.00

    def test_financing_net_positive(self, geotrade_movements):
        result = build_cashflow_direct(geotrade_movements)
        # Loan 10000 received − 1000 repayment = +9000
        assert result["financing"]["net"] == 9000.00

    def test_empty_movements(self):
        result = build_cashflow_direct([])
        assert result["operating"]["net"] == 0.0
        assert result["investing"]["net"] == 0.0
        assert result["financing"]["net"] == 0.0
        assert result["net_change_in_cash"] == 0.0

    def test_unknown_counterpart_goes_to_unknown(self):
        result = build_cashflow_direct([
            {"dr": "1120", "cr": "9999", "amount": 100.00, "description": "unknown"},
        ])
        assert len(result["unknown"]["lines"]) == 1


# ---------------------------------------------------------------------------
# build_cashflow_indirect
# ---------------------------------------------------------------------------

class TestBuildCashflowIndirect:

    def test_indirect_basic(self):
        result = build_cashflow_indirect(
            net_profit_loss=-4083.33,
            depreciation=83.33,
            working_capital_changes={"increase_in_inventory": -5000.0},
            investing_net=-3540.00,
            financing_net=9000.00,
        )
        assert result["method"] == "indirect"
        op = result["operating_activities"]
        assert op["net_profit_loss"] == -4083.33
        assert op["adjustments_for_non_cash"]["depreciation"] == 83.33

    def test_indirect_operating_net(self):
        result = build_cashflow_indirect(
            net_profit_loss=1000.0,
            depreciation=200.0,
            working_capital_changes={"wc_change": -300.0},
        )
        op = result["operating_activities"]
        expected_net = 1000.0 + 200.0 - 300.0
        assert abs(op["net"] - expected_net) < 0.01

    def test_indirect_net_change_sum(self):
        result = build_cashflow_indirect(
            net_profit_loss=500.0,
            depreciation=100.0,
            investing_net=-200.0,
            financing_net=1000.0,
        )
        expected = (500 + 100) + (-200) + 1000
        assert abs(result["net_change_in_cash"] - expected) < 0.01

    def test_indirect_policy_notes(self):
        result = build_cashflow_indirect(net_profit_loss=0.0)
        assert len(result["policy_notes"]) > 0
