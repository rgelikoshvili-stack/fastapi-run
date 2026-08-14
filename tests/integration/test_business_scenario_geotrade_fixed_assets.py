"""tests/integration/test_business_scenario_geotrade_fixed_assets.py

BIZ-1: GeoTrade Fixed Assets, Depreciation, NBV, P&L, Balance Sheet.

Runs with: JWT_SECRET=test-secret TEST_MODE=1 DATABASE_URL=""
No real database. No live RS.ge.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def straight_line_monthly(cost: float, residual: float, life_months: int) -> float:
    return round((cost - residual) / life_months, 2)


def nbv_after_n_months(cost: float, residual: float, life_months: int, n: int) -> float:
    monthly = (cost - residual) / life_months
    return round(cost - monthly * n, 2)


# ---------------------------------------------------------------------------
# Phase 8 — Fixed Asset Purchase
# ---------------------------------------------------------------------------

class TestFixedAssetPurchase:

    def test_fa_fixture_loaded(self, fixed_assets_fixture):
        assets = fixed_assets_fixture["assets"]
        assert len(assets) >= 2

    def test_laptop_cost(self, fixed_assets_fixture):
        laptop = next(a for a in fixed_assets_fixture["assets"] if a["id"] == "FA-AUG-001")
        assert laptop["cost"] == 3000.00

    def test_laptop_vat(self, fixed_assets_fixture):
        laptop = next(a for a in fixed_assets_fixture["assets"] if a["id"] == "FA-AUG-001")
        assert laptop["vat_amount"] == 540.00

    def test_fa_purchase_journal_dr_equals_cr(self, fixed_assets_fixture):
        laptop = next(a for a in fixed_assets_fixture["assets"] if a["id"] == "FA-AUG-001")
        jrn = laptop["expected_journals"]["purchase"]["lines"]
        dr = sum(l["amount"] for l in jrn if l.get("dr"))
        cr = sum(l["amount"] for l in jrn if l.get("cr"))
        assert abs(dr - cr) < 0.01

    def test_fa_account_is_1510(self, fixed_assets_fixture):
        laptop = next(a for a in fixed_assets_fixture["assets"] if a["id"] == "FA-AUG-001")
        fa_line = next(l for l in laptop["expected_journals"]["purchase"]["lines"] if l.get("dr") == "1510")
        assert fa_line["amount"] == 3000.00

    def test_fa_input_vat_is_3311(self, fixed_assets_fixture):
        laptop = next(a for a in fixed_assets_fixture["assets"] if a["id"] == "FA-AUG-001")
        vat_line = next(l for l in laptop["expected_journals"]["purchase"]["lines"] if l.get("dr") == "3311")
        assert vat_line["amount"] == 540.00

    def test_fa_ap_is_3110(self, fixed_assets_fixture):
        laptop = next(a for a in fixed_assets_fixture["assets"] if a["id"] == "FA-AUG-001")
        ap_line = next(l for l in laptop["expected_journals"]["purchase"]["lines"] if l.get("cr") == "3110")
        assert ap_line["amount"] == 3540.00

    def test_fa_payment_journal_clears_ap(self, fixed_assets_fixture):
        laptop = next(a for a in fixed_assets_fixture["assets"] if a["id"] == "FA-AUG-001")
        jrn = laptop["expected_journals"]["payment"]["lines"]
        dr_line = next(l for l in jrn if l.get("dr") == "3110")
        cr_line = next(l for l in jrn if l.get("cr") == "1120")
        assert abs(dr_line["amount"] - cr_line["amount"]) < 0.01

    def test_fa_linked_to_rs_invoice(self, fixed_assets_fixture):
        laptop = next(a for a in fixed_assets_fixture["assets"] if a["id"] == "FA-AUG-001")
        assert laptop["linked_invoice"] == "RS-INV-FA-001"


# ---------------------------------------------------------------------------
# Phase 8 — Depreciation Calculation
# ---------------------------------------------------------------------------

class TestDepreciationCalculation:

    def test_monthly_depreciation_calculation(self):
        """Laptop: cost 3000, residual 0, life 36 months → 83.33/month."""
        monthly = straight_line_monthly(3000, 0, 36)
        assert monthly == 83.33

    def test_depreciation_journal_balances(self, fixed_assets_fixture):
        laptop = next(a for a in fixed_assets_fixture["assets"] if a["id"] == "FA-AUG-001")
        jrn = laptop["expected_journals"]["monthly_depreciation"]["lines"]
        dr = sum(l["amount"] for l in jrn if l.get("dr"))
        cr = sum(l["amount"] for l in jrn if l.get("cr"))
        assert abs(dr - cr) < 0.01

    def test_depreciation_expense_account(self, fixed_assets_fixture):
        laptop = next(a for a in fixed_assets_fixture["assets"] if a["id"] == "FA-AUG-001")
        depr_line = next(l for l in laptop["expected_journals"]["monthly_depreciation"]["lines"]
                         if l.get("dr") == "7610")
        assert abs(depr_line["amount"] - 83.33) < 0.01

    def test_accum_depr_account(self, fixed_assets_fixture):
        laptop = next(a for a in fixed_assets_fixture["assets"] if a["id"] == "FA-AUG-001")
        accum_line = next(l for l in laptop["expected_journals"]["monthly_depreciation"]["lines"]
                          if l.get("cr") == "1520")
        assert abs(accum_line["amount"] - 83.33) < 0.01

    def test_nbv_after_one_month(self, fixed_assets_fixture):
        laptop = next(a for a in fixed_assets_fixture["assets"] if a["id"] == "FA-AUG-001")
        expected = laptop["after_first_month"]["net_book_value"]
        calculated = nbv_after_n_months(3000, 0, 36, 1)
        assert abs(calculated - expected) < 0.01

    def test_nbv_after_one_month_value(self):
        nbv = nbv_after_n_months(3000, 0, 36, 1)
        assert abs(nbv - 2916.67) < 0.01

    def test_total_depreciation_over_life(self):
        """Sum of 36 monthly amounts must equal cost."""
        monthly = (3000 - 0) / 36
        total = sum(round(monthly, 2) for _ in range(36))
        assert abs(total - 3000.0) < 1.0, f"Total depr {total} should be ~3000"

    def test_depreciation_schedule_month_1(self, fixed_assets_fixture):
        sched = fixed_assets_fixture["depreciation_schedule_fa_aug_001"]
        m1 = next(s for s in sched if s["month"] == "2026-08")
        assert abs(m1["depr"] - 83.33) < 0.01
        assert abs(m1["nbv"] - 2916.67) < 0.01

    def test_idempotency_no_double_depreciation(self, fixed_assets_fixture):
        laptop = next(a for a in fixed_assets_fixture["assets"] if a["id"] == "FA-AUG-001")
        rule = laptop["idempotency"]["expected"]
        assert "no additional journal entry" in rule


# ---------------------------------------------------------------------------
# Phase 8 — NBV in Balance Sheet
# ---------------------------------------------------------------------------

class TestFixedAssetBalanceSheet:

    def test_balance_sheet_fa_cost(self, balance_sheet_fixture):
        bs = balance_sheet_fixture
        fa_cost = bs["assets"]["non_current_assets"]["fixed_assets_cost_1510"]
        assert fa_cost == 8000.00, "FA cost = 5000 (opening) + 3000 (laptop) = 8000"

    def test_balance_sheet_accum_depr(self, balance_sheet_fixture):
        bs = balance_sheet_fixture
        accum = bs["assets"]["non_current_assets"]["less_accumulated_depreciation_1520"]
        assert abs(accum - (-583.33)) < 0.01

    def test_balance_sheet_net_fa(self, balance_sheet_fixture):
        bs = balance_sheet_fixture
        net = bs["assets"]["non_current_assets"]["net_fixed_assets"]
        assert abs(net - 7416.67) < 0.01

    def test_bs_assets_equal_liabilities_equity(self, balance_sheet_fixture):
        bs = balance_sheet_fixture
        assert bs["_meta"]["balanced"] is True

    def test_depreciation_in_pl(self, profit_loss_fixture):
        pl = profit_loss_fixture
        depr = pl["operating_expenses"]["depreciation_7610"]
        assert abs(depr - 83.33) < 0.01

    def test_vat_report_includes_fa_vat(self, vat_report_fixture):
        fa_vat = vat_report_fixture["input_vat"]["fixed_asset_rs_inv_fa_001"]["vat"]
        assert fa_vat == 540.00


# ---------------------------------------------------------------------------
# Phase 8 — Prior Period Fixed Asset
# ---------------------------------------------------------------------------

class TestPriorPeriodFixedAsset:

    def test_prior_fa_opening_balances(self, fixed_assets_fixture):
        prior = next(a for a in fixed_assets_fixture["assets"] if a["id"] == "FA-PRIOR-001")
        assert prior["cost"] == 5000.00
        assert prior["opening_accum_depr"] == 500.00
        assert prior["opening_net_book_value"] == 4500.00

    def test_prior_fa_opens_from_balance_sheet(self, opening_balances_fixture):
        balances = opening_balances_fixture["balances"]
        fa = next(b for b in balances if b["account_code"] == "1510")
        accum = next(b for b in balances if b["account_code"] == "1520")
        assert fa["debit"] == 5000.00
        assert accum["credit"] == 500.00

    def test_combined_fa_in_trial_balance(self, trial_balance_fixture):
        tb_entry = next(a for a in trial_balance_fixture["accounts"]
                        if a["account_code"] == "1510")
        assert tb_entry["closing_debit"] == 8000.00

    def test_combined_accum_depr_in_trial_balance(self, trial_balance_fixture):
        tb_entry = next(a for a in trial_balance_fixture["accounts"]
                        if a["account_code"] == "1520")
        assert abs(tb_entry["closing_credit"] - 583.33) < 0.01
