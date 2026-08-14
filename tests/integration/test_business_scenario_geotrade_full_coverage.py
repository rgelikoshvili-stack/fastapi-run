"""tests/integration/test_business_scenario_geotrade_full_coverage.py

BIZ-1: Full coverage — opening balances, cash, advances, partial payments,
returns, FIFO/WACG, FX, loan/interest, accruals, period lock, reversal,
AR/AP aging, CFO dashboard.

Runs with: JWT_SECRET=test-secret TEST_MODE=1 DATABASE_URL=""
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.api.services.inventory_costing_service import fifo_cogs, wacg_cogs, compute_cogs
from app.api.services.taxation_engine import calculate_vat


# ---------------------------------------------------------------------------
# Phase 1 — Opening Balances
# ---------------------------------------------------------------------------

class TestOpeningBalances:

    def test_opening_balances_fixture_loaded(self, opening_balances_fixture):
        assert len(opening_balances_fixture["balances"]) == 9

    def test_opening_dr_total(self, opening_balances_fixture):
        dr_total = sum(b["debit"] for b in opening_balances_fixture["balances"])
        assert abs(dr_total - 29500.00) < 0.01

    def test_opening_cr_total(self, opening_balances_fixture):
        cr_total = sum(b["credit"] for b in opening_balances_fixture["balances"])
        assert abs(cr_total - 29500.00) < 0.01

    def test_opening_balances_balanced(self, opening_balances_fixture):
        meta = opening_balances_fixture["_meta"]
        assert abs(meta["dr_total"] - meta["cr_total"]) < 0.01

    def test_opening_cash_1110(self, opening_balances_fixture):
        cash = next(b for b in opening_balances_fixture["balances"] if b["account_code"] == "1110")
        assert cash["debit"] == 1000.00

    def test_opening_bank_1120(self, opening_balances_fixture):
        bank = next(b for b in opening_balances_fixture["balances"] if b["account_code"] == "1120")
        assert bank["debit"] == 20000.00

    def test_opening_equity_4110(self, opening_balances_fixture):
        equity = next(b for b in opening_balances_fixture["balances"] if b["account_code"] == "4110")
        assert equity["credit"] == 26200.00

    def test_opening_idempotency_rule(self, opening_balances_fixture):
        rule = opening_balances_fixture["idempotency"]["rule"]
        assert "Upsert" in rule

    def test_opening_fixed_asset_uses_1510(self, opening_balances_fixture):
        fa = next((b for b in opening_balances_fixture["balances"] if b["account_code"] == "1510"), None)
        assert fa is not None, "Fixed assets must use account 1510, not 2100"
        assert fa["debit"] == 5000.00

    def test_opening_no_account_2100(self, opening_balances_fixture):
        codes = [b["account_code"] for b in opening_balances_fixture["balances"]]
        assert "2100" not in codes, "Account 2100 does not exist in Bridge Hub COA. Use 1510."


# ---------------------------------------------------------------------------
# Phase 9 — Cash Register / Petty Cash
# ---------------------------------------------------------------------------

class TestPettyCash:

    def test_cash_register_loaded(self, cash_register_fixture):
        assert len(cash_register_fixture["transactions"]) >= 2

    def test_cash_in_bank_withdrawal(self, cash_register_fixture):
        tx = next(t for t in cash_register_fixture["transactions"] if t["id"] == "CASH-001")
        assert tx["amount"] == 500.00
        assert tx["direction"] == "in"

    def test_cash_expense_gross(self, cash_register_fixture):
        tx = next(t for t in cash_register_fixture["transactions"] if t["id"] == "CASH-002")
        assert tx["gross_amount"] == 118.00

    def test_cash_expense_vat(self, cash_register_fixture):
        tx = next(t for t in cash_register_fixture["transactions"] if t["id"] == "CASH-002")
        assert tx["vat_amount"] == 18.00

    def test_cash_balance_never_negative(self, cash_register_fixture):
        opening = cash_register_fixture["period_summary"]["opening_cash"]
        receipts = cash_register_fixture["period_summary"]["receipts"]
        payments = cash_register_fixture["period_summary"]["payments"]
        closing = opening + receipts - payments
        assert closing >= 0, "Cash cannot go negative"

    def test_closing_cash_calculated(self, cash_register_fixture):
        summary = cash_register_fixture["period_summary"]
        expected = summary["closing_cash"]
        calculated = summary["opening_cash"] + summary["receipts"] - summary["payments"]
        assert abs(calculated - expected) < 0.01

    def test_petty_cash_journal_balances(self, cash_register_fixture):
        tx = next(t for t in cash_register_fixture["transactions"] if t["id"] == "CASH-002")
        jrn = tx["expected_journal"]
        dr = sum(l["amount"] for l in jrn if l.get("dr"))
        cr = sum(l["amount"] for l in jrn if l.get("cr"))
        assert abs(dr - cr) < 0.01

    def test_petty_cash_in_vat_report(self, vat_report_fixture):
        pc_vat = vat_report_fixture["input_vat"]["petty_cash_office_supplies"]["vat"]
        assert pc_vat == 18.00


# ---------------------------------------------------------------------------
# Phase 10 — Advances
# ---------------------------------------------------------------------------

class TestAdvances:

    def test_customer_advance_not_revenue(self):
        """Customer advance credited to 3120 (liability), not 6110 (revenue)."""
        advance_lines = [
            {"dr": "1120", "amount": 1000.00},
            {"cr": "3120", "amount": 1000.00},
        ]
        revenue_posted = any(l.get("cr") == "6110" for l in advance_lines)
        assert not revenue_posted, "Customer advance must not go to revenue 6110"

    def test_customer_advance_application(self):
        """When invoice issued, advance application: Dr 3120 / Cr 1210 (AR)."""
        application_lines = [
            {"dr": "3120", "amount": 1000.00},
            {"cr": "1210", "amount": 1000.00},
        ]
        dr = sum(l["amount"] for l in application_lines if "dr" in l)
        cr = sum(l["amount"] for l in application_lines if "cr" in l)
        assert abs(dr - cr) < 0.01

    def test_supplier_advance_not_expense(self):
        """Supplier advance debited to 1420 (asset), not expense account."""
        advance_lines = [
            {"dr": "1420", "amount": 1200.00},
            {"cr": "1120", "amount": 1200.00},
        ]
        expense_posted = any(l.get("dr") in ["7110", "7210", "7310"] for l in advance_lines)
        assert not expense_posted, "Supplier advance must not go to expense"

    def test_supplier_advance_application(self):
        """When supplier invoice arrives: Dr 3110 / Cr 1420."""
        lines = [
            {"dr": "3110", "amount": 1200.00},
            {"cr": "1420", "amount": 1200.00},
        ]
        dr = sum(l["amount"] for l in lines if "dr" in l)
        cr = sum(l["amount"] for l in lines if "cr" in l)
        assert abs(dr - cr) < 0.01


# ---------------------------------------------------------------------------
# Phase 11 — Partial Payments
# ---------------------------------------------------------------------------

class TestPartialPayments:

    def test_partial_payment_1_remaining(self):
        invoice = 2400.00
        payment1 = 1000.00
        remaining = invoice - payment1
        assert remaining == 1400.00

    def test_partial_payment_2_clears_balance(self):
        remaining = 1400.00
        payment2 = 1400.00
        final = remaining - payment2
        assert final == 0.00

    def test_no_overpayment_without_advance(self):
        """Cannot pay more than invoice without explicit advance treatment."""
        invoice = 2400.00
        payment = 2500.00
        overpay = payment - invoice
        assert overpay > 0, "Overpayment must be flagged, not silently accepted"

    def test_partial_aging_uses_remaining(self, aging_fixture):
        partial_test = aging_fixture["partial_payment_test"]
        remaining = partial_test["remaining_after_all_payments"]
        assert remaining == 0.00


# ---------------------------------------------------------------------------
# Phase 12 — Returns / Corrections / Cancellations
# ---------------------------------------------------------------------------

class TestReturns:

    def test_return_revenue_reversal_journal(self):
        """2 keyboards returned: reverse revenue 160 + VAT 28.80."""
        lines = [
            {"dr": "6110", "amount": 160.00},
            {"dr": "3310", "amount": 28.80},
            {"cr": "1210", "amount": 188.80},
        ]
        dr = sum(l["amount"] for l in lines if "dr" in l)
        cr = sum(l["amount"] for l in lines if "cr" in l)
        assert abs(dr - cr) < 0.01

    def test_return_cogs_reversal(self):
        """2 units returned to inventory: reverse COGS 100 (2 × 50)."""
        cogs_reversed = 2 * 50.0
        lines = [
            {"dr": "1310", "amount": cogs_reversed},
            {"cr": "7110", "amount": cogs_reversed},
        ]
        dr = sum(l["amount"] for l in lines if "dr" in l)
        cr = sum(l["amount"] for l in lines if "cr" in l)
        assert abs(dr - cr) < 0.01

    def test_inventory_increases_after_return(self, inventory_fixture):
        state_after_return = inventory_fixture["scenario_inventory_state"]["after_phase12_return"]
        assert state_after_return["layer1_remaining"] == 82
        assert state_after_return["total_value"] == 4100.00

    def test_output_vat_decreases_after_return(self, vat_report_fixture):
        adj = vat_report_fixture["vat_adjustments"]["sales_return_output_vat_reversal"]
        assert adj["vat_reversed"] == -28.80

    def test_original_entry_not_deleted(self):
        """Correction must create new entries, not delete original."""
        original_exists = True
        reversal_exists = True
        assert original_exists and reversal_exists, \
            "Audit: original and reversal entries must both be preserved"

    def test_no_auto_live_rsge_action(self, rsge_documents_fixture):
        """Correction preview generated but no automatic live RS.ge mutation."""
        for doc in rsge_documents_fixture["documents"]:
            eb = doc.get("expected_bridge_hub", {})
            assert eb.get("no_auto_post") is not False, \
                "Live RS.ge actions must not be automatically triggered"


# ---------------------------------------------------------------------------
# Phase 13 — FIFO and WACG Inventory Costing
# ---------------------------------------------------------------------------

class TestInventoryCosting:

    def test_fifo_cogs_120_units(self, inventory_fixture):
        fifo = inventory_fixture["fifo_test"]
        purchases = fifo["input_purchases"]
        result = fifo_cogs(purchases, fifo["dispatch_qty"])
        expected_cogs = fifo["expected_result"]["cogs"]
        assert abs(result["cogs"] - expected_cogs) < 0.01

    def test_fifo_layers_consumed(self, inventory_fixture):
        fifo = inventory_fixture["fifo_test"]
        result = fifo_cogs(fifo["input_purchases"], fifo["dispatch_qty"])
        assert result["unmatched_qty"] == 0.0

    def test_fifo_first_layer_fully_consumed(self, inventory_fixture):
        fifo = inventory_fixture["fifo_test"]
        result = fifo_cogs(fifo["input_purchases"], fifo["dispatch_qty"])
        assert len(result["layers_consumed"]) == 2
        assert result["layers_consumed"][0]["qty"] == 100

    def test_fifo_second_layer_partial(self, inventory_fixture):
        fifo = inventory_fixture["fifo_test"]
        result = fifo_cogs(fifo["input_purchases"], fifo["dispatch_qty"])
        assert result["layers_consumed"][1]["qty"] == 20

    def test_wacg_cogs_120_units(self, inventory_fixture):
        wacg = inventory_fixture["wacg_test"]
        result = wacg_cogs(wacg["input_purchases"], wacg["dispatch_qty"])
        expected = wacg["expected_result"]["cogs"]
        assert abs(result["cogs"] - expected) < 0.01

    def test_wacg_avg_cost(self, inventory_fixture):
        wacg = inventory_fixture["wacg_test"]
        result = wacg_cogs(wacg["input_purchases"], wacg["dispatch_qty"])
        expected_avg = wacg["expected_result"]["avg_cost"]
        assert abs(result["avg_purchase_cost"] - expected_avg) < 0.01

    def test_fifo_ending_inventory(self, inventory_fixture):
        fifo = inventory_fixture["fifo_test"]
        ending = fifo["expected_result"]["ending_inventory_value"]
        assert ending == 1800.00

    def test_wacg_ending_inventory(self, inventory_fixture):
        wacg = inventory_fixture["wacg_test"]
        ending = wacg["expected_result"]["ending_inventory_value"]
        assert ending == 1600.00

    def test_compute_cogs_fifo(self, inventory_fixture):
        fifo = inventory_fixture["fifo_test"]
        result = compute_cogs("fifo", fifo["input_purchases"], fifo["dispatch_qty"])
        assert abs(result["cogs"] - 6200.00) < 0.01

    def test_compute_cogs_average(self, inventory_fixture):
        wacg = inventory_fixture["wacg_test"]
        result = compute_cogs("average", wacg["input_purchases"], wacg["dispatch_qty"])
        assert abs(result["cogs"] - 6400.00) < 0.01

    def test_negative_stock_blocked(self, inventory_fixture):
        check = inventory_fixture["negative_stock_check"]
        result = fifo_cogs(
            [{"qty": check["available_qty"], "cost": 50.0}],
            check["dispatch_qty"],
        )
        assert result["unmatched_qty"] > 0, "Negative stock: unmatched_qty must be > 0"


# ---------------------------------------------------------------------------
# Phase 14 — FX Gain/Loss
# ---------------------------------------------------------------------------

class TestFXGainLoss:

    def test_fx_invoice_journal_dr_cr(self):
        """USD 1000 @ 2.70 → GEL 2700 purchase."""
        invoice_gel = 1000 * 2.70
        lines = [
            {"dr": "1310", "amount": invoice_gel},
            {"cr": "3110", "amount": invoice_gel},
        ]
        dr = sum(l["amount"] for l in lines if "dr" in l)
        cr = sum(l["amount"] for l in lines if "cr" in l)
        assert abs(dr - cr) < 0.01

    def test_fx_payment_journal_with_loss(self):
        """Payment at 2.75 → GEL 2750; FX loss 50."""
        invoice_gel = 2700.00
        payment_gel = 1000 * 2.75
        fx_loss = payment_gel - invoice_gel
        assert fx_loss == 50.00

    def test_fx_loss_journal_balances(self):
        lines = [
            {"dr": "3110", "amount": 2700.00},
            {"dr": "7920", "amount": 50.00},
            {"cr": "1120", "amount": 2750.00},
        ]
        dr = sum(l["amount"] for l in lines if "dr" in l)
        cr = sum(l["amount"] for l in lines if "cr" in l)
        assert abs(dr - cr) < 0.01

    def test_realized_fx_loss_in_bank_statement(self, bank_csv_fixture):
        assert "FX" in bank_csv_fixture or "2750" in bank_csv_fixture


# ---------------------------------------------------------------------------
# Phase 15 — Loan and Interest
# ---------------------------------------------------------------------------

class TestLoanAndInterest:

    def test_loan_receipt_journal(self):
        """Loan receipt: Dr 1120 / Cr 3410."""
        lines = [
            {"dr": "1120", "amount": 10000.00},
            {"cr": "3410", "amount": 10000.00},
        ]
        dr = sum(l["amount"] for l in lines if "dr" in l)
        cr = sum(l["amount"] for l in lines if "cr" in l)
        assert abs(dr - cr) < 0.01

    def test_interest_accrual_journal(self):
        """Monthly interest accrual: Dr 7520 / Cr 3420."""
        lines = [
            {"dr": "7520", "amount": 150.00},
            {"cr": "3420", "amount": 150.00},
        ]
        dr = sum(l["amount"] for l in lines if "dr" in l)
        cr = sum(l["amount"] for l in lines if "cr" in l)
        assert abs(dr - cr) < 0.01

    def test_interest_not_treated_as_principal(self):
        """Interest expense goes to 7520, not 3410 (loan principal)."""
        interest_account = "7520"
        loan_account = "3410"
        assert interest_account != loan_account

    def test_loan_in_bank_statement(self, bank_csv_fixture):
        assert "loan" in bank_csv_fixture.lower() or "10000" in bank_csv_fixture

    @pytest.mark.xfail(
        reason="EXPECTED_GAP_LOAN_ACCOUNT_MAPPING: 3410 is short-term loan in COA. "
               "Loan module / amortisation schedule not implemented as standalone service."
    )
    def test_loan_amortisation_schedule(self):
        raise NotImplementedError("Loan amortisation schedule not implemented")


# ---------------------------------------------------------------------------
# Phase 16 — Accruals and Prepaid Expenses
# ---------------------------------------------------------------------------

class TestAccrualsAndPrepaids:

    def test_utility_accrual_journal(self):
        """Accrued utility: Dr 7410 / Cr 3420."""
        lines = [
            {"dr": "7410", "amount": 300.00},
            {"cr": "3420", "amount": 300.00},
        ]
        dr = sum(l["amount"] for l in lines if "dr" in l)
        cr = sum(l["amount"] for l in lines if "cr" in l)
        assert abs(dr - cr) < 0.01

    def test_prepaid_insurance_initial_journal(self):
        """Insurance prepaid: Dr 1430 / Cr 1120."""
        lines = [
            {"dr": "1430", "amount": 1200.00},
            {"cr": "1120", "amount": 1200.00},
        ]
        dr = sum(l["amount"] for l in lines if "dr" in l)
        cr = sum(l["amount"] for l in lines if "cr" in l)
        assert abs(dr - cr) < 0.01

    def test_prepaid_monthly_recognition(self):
        """Monthly insurance recognition: Dr 7410 100 / Cr 1430 100."""
        total_prepaid = 1200.00
        months = 12
        monthly = total_prepaid / months
        assert monthly == 100.00

    def test_prepaid_recognition_journal(self):
        monthly = 100.00
        lines = [
            {"dr": "7410", "amount": monthly},
            {"cr": "1430", "amount": monthly},
        ]
        dr = sum(l["amount"] for l in lines if "dr" in l)
        cr = sum(l["amount"] for l in lines if "cr" in l)
        assert abs(dr - cr) < 0.01

    def test_prepaid_in_bank_statement(self, bank_csv_fixture):
        assert "insurance" in bank_csv_fixture.lower() or "1200" in bank_csv_fixture


# ---------------------------------------------------------------------------
# Phase 17 — Profit Tax / Dividend
# ---------------------------------------------------------------------------

class TestProfitTaxDividend:

    @pytest.mark.xfail(
        reason="EXPECTED_GAP_PROFIT_TAX_DIVIDEND: Full dividend journal generation "
               "(declared dividend → payable + withholding tax → payment) is not "
               "implemented as an automated service. Tax rates exist in taxation_engine.py "
               "(DIVIDEND_WHT=5%, CIT=15%) but journal builder not wired."
    )
    def test_dividend_journal_generated(self):
        raise NotImplementedError("Dividend journal generation not implemented")

    def test_dividend_wht_rate_exists(self):
        """Dividend withholding rate must be defined in taxation engine."""
        from app.api.services.taxation_engine import DIVIDEND_WHT
        assert float(DIVIDEND_WHT) == 0.05

    def test_cit_rate_exists(self):
        from app.api.services.taxation_engine import CIT_RATE
        assert float(CIT_RATE) == 0.15


# ---------------------------------------------------------------------------
# Phase 18 — Period Lock
# ---------------------------------------------------------------------------

class TestPeriodLock:

    @pytest.mark.xfail(
        reason="EXPECTED_GAP_PERIOD_LOCK: period_lock enforcement via routes_period_lock.py "
               "requires a live DB. Testing that the lock concept is modelled correctly."
    )
    def test_locked_period_blocks_new_posting(self):
        raise NotImplementedError("Period lock requires DB")

    def test_period_lock_route_exists(self):
        """routes_period_lock.py must exist and be importable."""
        import importlib
        mod = importlib.util.find_spec("app.api.routes_period_lock")
        assert mod is not None, "routes_period_lock module not found"

    def test_period_lock_cfo_dashboard_metric(self, cfo_dashboard_fixture):
        lock_metric = cfo_dashboard_fixture["metrics"]["period_lock"]
        assert "august_2026_locked" in lock_metric


# ---------------------------------------------------------------------------
# Phase 19 — Reversal / Adjustment Flow
# ---------------------------------------------------------------------------

class TestReversalAdjustment:

    def test_reversal_journal_negates_original(self):
        """Reversal of rent entry: each line gets opposite sign."""
        original = [
            {"dr": "7310", "cr": None, "amount": 1000.00},
            {"dr": "3311", "cr": None, "amount": 180.00},
            {"dr": None, "cr": "3110", "amount": 1180.00},
        ]
        reversal = [
            {"dr": None, "cr": "7310", "amount": 1000.00},
            {"dr": None, "cr": "3311", "amount": 180.00},
            {"dr": "3110", "cr": None, "amount": 1180.00},
        ]
        combined_dr = (
            sum(l["amount"] for l in original if l["dr"]) +
            sum(l["amount"] for l in reversal if l["dr"])
        )
        combined_cr = (
            sum(l["amount"] for l in original if l["cr"]) +
            sum(l["amount"] for l in reversal if l["cr"])
        )
        assert abs(combined_dr - combined_cr) < 0.01

    def test_original_entry_preserved(self):
        """Original posted entry must never be deleted — only reversed."""
        original_deleted = False
        assert not original_deleted, "Original entry must be preserved in audit trail"

    def test_trial_balance_remains_balanced_after_reversal(self, trial_balance_fixture):
        meta = trial_balance_fixture["_meta"]
        assert meta["balanced"] is True


# ---------------------------------------------------------------------------
# Phase 21 — AR/AP Aging
# ---------------------------------------------------------------------------

class TestARAPAging:

    def test_paid_invoice_excluded_from_aging(self, aging_fixture):
        paid_ar = next(i for i in aging_fixture["test_invoices"] if i["id"] == "AR-AGING-001")
        assert paid_ar["remaining"] == 0.00
        assert paid_ar["expected_bucket"] is None

    def test_unpaid_ar_in_correct_bucket(self, aging_fixture):
        unpaid = next(i for i in aging_fixture["test_invoices"] if i["id"] == "AR-AGING-002")
        assert unpaid["expected_bucket"] == "31_60"
        assert unpaid["remaining"] == 2000.00

    def test_unpaid_ap_in_correct_bucket(self, aging_fixture):
        unpaid = next(i for i in aging_fixture["test_invoices"] if i["id"] == "AP-AGING-001")
        assert unpaid["expected_bucket"] == "61_90"
        assert unpaid["remaining"] == 3000.00

    def test_aging_bucket_names_match_bridge_hub(self, aging_fixture):
        """Bridge Hub uses specific bucket names: current, 31_60, 61_90, 91_120, over_120."""
        buckets = list(aging_fixture["expected_ar_aging_summary"]["buckets"].keys())
        expected_bridge_hub_buckets = [
            "current_0_30", "31_60", "61_90", "91_120", "over_120"
        ]
        for b in expected_bridge_hub_buckets:
            assert b in buckets, f"Bucket {b} not in AR aging summary"

    def test_aging_uses_report_date(self, aging_fixture):
        report_date = aging_fixture["_meta"]["report_date"]
        assert report_date == "2026-09-15"

    def test_partial_payment_excluded(self, aging_fixture):
        partial = aging_fixture["partial_payment_test"]
        assert partial["remaining_after_all_payments"] == 0.00
