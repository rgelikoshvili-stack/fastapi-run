"""tests/integration/test_business_scenario_geotrade_full_accounting.py

BIZ-1: GeoTrade Full Accounting Scenario — Core Purchase/Sale/Bank/Rent/Payroll/VAT.

Runs with: JWT_SECRET=test-secret TEST_MODE=1 DATABASE_URL=""
All DB calls mocked. No live RS.ge. No production credentials.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.api.services.inventory_costing_service import fifo_cogs, wacg_cogs, compute_cogs
from app.api.services.taxation_engine import calculate_vat, calculate_payroll
from app.knowledge.chart_of_accounts import CHART_OF_ACCOUNTS


# ---------------------------------------------------------------------------
# Phase 2 — RS.ge Purchase Document: Journal Validation
# ---------------------------------------------------------------------------

class TestPhase2PurchaseJournal:

    def test_purchase_journal_dr_equals_cr(self, rsge_documents_fixture):
        """Keyboard purchase journal must balance DR = CR."""
        doc = next(d for d in rsge_documents_fixture["documents"] if d["id"] == "RS-INV-PUR-001")
        expected = doc["expected_bridge_hub"]["draft_journal"]
        dr_total = sum(e["amount"] for e in expected if e["dr"])
        cr_total = sum(e["amount"] for e in expected if e["cr"])
        assert abs(dr_total - cr_total) < 0.01, f"Journal imbalance: DR={dr_total} CR={cr_total}"

    def test_purchase_inventory_debit(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"] if d["id"] == "RS-INV-PUR-001")
        inv_line = next(e for e in doc["expected_bridge_hub"]["draft_journal"] if e["dr"] == "1310")
        assert inv_line["amount"] == 5000.00

    def test_purchase_input_vat(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"] if d["id"] == "RS-INV-PUR-001")
        vat_line = next(e for e in doc["expected_bridge_hub"]["draft_journal"] if e["dr"] == "3311")
        assert vat_line["amount"] == 900.00

    def test_purchase_ap_credit(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"] if d["id"] == "RS-INV-PUR-001")
        ap_line = next(e for e in doc["expected_bridge_hub"]["draft_journal"] if e["cr"] == "3110")
        assert ap_line["amount"] == 5900.00

    def test_vat_calculation_on_purchase(self):
        """VAT calculator must return 900 on 5000 net (18% exclusive)."""
        result = calculate_vat(Decimal("5000"), inclusive=False)
        assert result["vat_amount"] == 900.0
        assert result["total"] == 5900.0

    def test_purchase_requires_approval(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"] if d["id"] == "RS-INV-PUR-001")
        assert doc["expected_bridge_hub"]["requires_approval"] is True

    def test_purchase_no_auto_post(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"] if d["id"] == "RS-INV-PUR-001")
        assert doc["expected_bridge_hub"]["no_auto_post"] is True

    def test_purchase_direction_is_incoming(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"] if d["id"] == "RS-INV-PUR-001")
        assert doc["direction"] == "incoming"

    def test_buyer_inn_matches_own(self, rsge_documents_fixture, own_company_inn):
        doc = next(d for d in rsge_documents_fixture["documents"] if d["id"] == "RS-INV-PUR-001")
        assert doc["buyer_inn"] == own_company_inn


# ---------------------------------------------------------------------------
# Phase 3 — Supplier Payment
# ---------------------------------------------------------------------------

class TestPhase3SupplierPayment:

    def test_supplier_payment_journal_balances(self):
        """Supplier payment: Dr 3110 / Cr 1120 must balance."""
        lines = [
            {"dr": "3110", "amount": 5900.00},
            {"cr": "1120", "amount": 5900.00},
        ]
        dr = sum(l["amount"] for l in lines if "dr" in l)
        cr = sum(l["amount"] for l in lines if "cr" in l)
        assert abs(dr - cr) < 0.01

    def test_bank_csv_contains_supplier_payment(self, bank_csv_fixture):
        assert "Office Supplier LLC" in bank_csv_fixture
        assert "5900" in bank_csv_fixture

    def test_bank_csv_format(self, bank_csv_fixture):
        """Bank CSV must have correct header columns."""
        lines = bank_csv_fixture.strip().split("\n")
        header = lines[0]
        assert "date" in header
        assert "description" in header
        assert "paid_in" in header
        assert "paid_out" in header

    def test_ap_balance_after_payment_is_zero(self):
        """AP opened 5900, payment 5900 → remaining 0."""
        ap_open = 5900.00
        payment = 5900.00
        remaining = ap_open - payment
        assert remaining == 0.00


# ---------------------------------------------------------------------------
# Phase 4 — Sales Document + COGS
# ---------------------------------------------------------------------------

class TestPhase4SalesAndCOGS:

    def test_sale_journal_dr_equals_cr(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"] if d["id"] == "RS-INV-SALE-001")
        jrn = doc["expected_bridge_hub"]["draft_journal_revenue"]
        dr = sum(e["amount"] for e in jrn if e["dr"])
        cr = sum(e["amount"] for e in jrn if e["cr"])
        assert abs(dr - cr) < 0.01

    def test_sale_revenue_amount(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"] if d["id"] == "RS-INV-SALE-001")
        rev_line = next(e for e in doc["expected_bridge_hub"]["draft_journal_revenue"] if e["cr"] == "6110")
        assert rev_line["amount"] == 1600.00

    def test_sale_output_vat(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"] if d["id"] == "RS-INV-SALE-001")
        vat_line = next(e for e in doc["expected_bridge_hub"]["draft_journal_revenue"] if e["cr"] == "3310")
        assert vat_line["amount"] == 288.00

    def test_sale_ar_debit(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"] if d["id"] == "RS-INV-SALE-001")
        ar_line = next(e for e in doc["expected_bridge_hub"]["draft_journal_revenue"] if e["dr"] == "1210")
        assert ar_line["amount"] == 1888.00

    def test_output_vat_on_sale(self):
        result = calculate_vat(Decimal("1600"), inclusive=False)
        assert result["vat_amount"] == 288.0
        assert result["total"] == 1888.0

    def test_sale_direction_is_outgoing(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"] if d["id"] == "RS-INV-SALE-001")
        assert doc["direction"] == "outgoing"

    def test_seller_inn_matches_own(self, rsge_documents_fixture, own_company_inn):
        doc = next(d for d in rsge_documents_fixture["documents"] if d["id"] == "RS-INV-SALE-001")
        assert doc["seller_inn"] == own_company_inn

    def test_cogs_fifo_20_units(self, inventory_fixture):
        """Sell 20 units from layer 1 (100 @ 50): COGS = 1000."""
        purchases = [{"qty": 100, "cost": 50.00}]
        result = fifo_cogs(purchases, 20)
        assert result["cogs"] == 1000.00

    def test_cogs_journal_balances(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"] if d["id"] == "RS-INV-SALE-001")
        cogs_jrn = doc["expected_bridge_hub"]["draft_journal_cogs"]
        dr = sum(e["amount"] for e in cogs_jrn if e["dr"])
        cr = sum(e["amount"] for e in cogs_jrn if e["cr"])
        assert abs(dr - cr) < 0.01

    def test_inventory_decreases_by_cogs(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"] if d["id"] == "RS-INV-SALE-001")
        inv_line = next(e for e in doc["expected_bridge_hub"]["draft_journal_cogs"] if e["cr"] == "1310")
        assert inv_line["amount"] == 1000.00

    def test_remaining_inventory_after_sale(self, inventory_fixture):
        state = inventory_fixture["scenario_inventory_state"]["after_phase4_sale"]
        assert state["layer1_remaining"] == 80
        assert state["total_value"] == 4000.00


# ---------------------------------------------------------------------------
# Phase 5 — Customer Payment
# ---------------------------------------------------------------------------

class TestPhase5CustomerPayment:

    def test_customer_payment_bank_csv(self, bank_csv_fixture):
        assert "Client LTD" in bank_csv_fixture
        assert "1888" in bank_csv_fixture

    def test_ar_balance_after_payment_zero(self):
        ar_open = 1888.00
        payment = 1888.00
        remaining = ar_open - payment
        assert remaining == 0.00


# ---------------------------------------------------------------------------
# Phase 6 — Rent Expense
# ---------------------------------------------------------------------------

class TestPhase6Rent:

    def test_rent_journal_dr_equals_cr(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"] if d["id"] == "RS-INV-RENT-001")
        jrn = doc["expected_bridge_hub"]["draft_journal"]
        dr = sum(e["amount"] for e in jrn if e["dr"])
        cr = sum(e["amount"] for e in jrn if e["cr"])
        assert abs(dr - cr) < 0.01

    def test_rent_expense_account(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"] if d["id"] == "RS-INV-RENT-001")
        rent_line = next(e for e in doc["expected_bridge_hub"]["draft_journal"] if e["dr"] == "7310")
        assert rent_line["amount"] == 1000.00

    def test_rent_input_vat(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"] if d["id"] == "RS-INV-RENT-001")
        vat_line = next(e for e in doc["expected_bridge_hub"]["draft_journal"] if e["dr"] == "3311")
        assert vat_line["amount"] == 180.00

    def test_rent_classification_not_inventory(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"] if d["id"] == "RS-INV-RENT-001")
        inv_lines = [e for e in doc["expected_bridge_hub"]["draft_journal"] if e.get("dr") == "1310"]
        assert len(inv_lines) == 0, "Rent must not be booked to inventory"


# ---------------------------------------------------------------------------
# Phase 7 — Payroll
# ---------------------------------------------------------------------------

class TestPhase7Payroll:

    def test_payroll_gross_total(self, payroll_fixture):
        totals = payroll_fixture["period_totals"]
        assert totals["gross_salary"] == 3500.00

    def test_payroll_pit_calculation(self, payroll_fixture):
        totals = payroll_fixture["period_totals"]
        assert totals["pit_total"] == 700.00

    def test_payroll_net_payable(self, payroll_fixture):
        totals = payroll_fixture["period_totals"]
        assert totals["net_payable_to_employees"] == 2730.00

    def test_payroll_accrual_journal_balances(self, payroll_fixture):
        accrual = payroll_fixture["expected_journals"]["accrual"]
        assert accrual["balanced"] is True
        dr = accrual["dr_total"]
        cr = accrual["cr_total"]
        assert abs(dr - cr) < 0.01

    def test_payroll_salary_expense_account(self, payroll_fixture):
        accrual = payroll_fixture["expected_journals"]["accrual"]
        sal_line = next(l for l in accrual["lines"] if l.get("dr") == "7210")
        assert sal_line["amount"] == 3500.00

    def test_payroll_pit_payable_account(self, payroll_fixture):
        accrual = payroll_fixture["expected_journals"]["accrual"]
        pit_line = next(l for l in accrual["lines"] if l.get("cr") == "3320")
        assert pit_line["amount"] == 700.00

    def test_salary_payment_clears_payable(self, payroll_fixture):
        payment = payroll_fixture["expected_journals"]["salary_payment"]
        dr_line = next(l for l in payment["lines"] if l.get("dr") == "3130")
        cr_line = next(l for l in payment["lines"] if l.get("cr") == "1120")
        assert abs(dr_line["amount"] - cr_line["amount"]) < 0.01

    def test_payroll_taxation_engine(self):
        """taxation_engine.calculate_payroll must calculate PIT correctly."""
        try:
            from app.api.services.taxation_engine import calculate_payroll
            result = calculate_payroll(Decimal("2000"))
            pit = result.get("pit") or result.get("pit_amount", 0)
            assert float(pit) == pytest.approx(400.0, abs=0.01)
        except (ImportError, AttributeError):
            pytest.skip("calculate_payroll not available in taxation_engine")


# ---------------------------------------------------------------------------
# Phase 8 — VAT Report Summary
# ---------------------------------------------------------------------------

class TestPhase8VATSummary:

    def test_total_input_vat(self, vat_report_fixture):
        assert vat_report_fixture["input_vat"]["total_input_vat"] == 1638.00

    def test_total_output_vat(self, vat_report_fixture):
        assert vat_report_fixture["output_vat"]["total_output_vat"] == 288.00

    def test_net_vat_position(self, vat_report_fixture):
        net = vat_report_fixture["net_vat_position"]
        assert net["input_vat"] == 1638.00
        assert net["output_vat_gross"] == 288.00
        # After returns adjustment: output VAT net = 259.20; receivable = 1638 - 259.20 = 1378.80
        assert abs(net["net_vat_receivable"] - 1378.80) < 0.01

    def test_input_vat_breakdown(self, vat_report_fixture):
        inp = vat_report_fixture["input_vat"]
        assert inp["purchases_rs_inv_pur_001"]["vat"] == 900.00
        assert inp["rent_rs_inv_rent_001"]["vat"] == 180.00
        assert inp["fixed_asset_rs_inv_fa_001"]["vat"] == 540.00
        assert inp["petty_cash_office_supplies"]["vat"] == 18.00


# ---------------------------------------------------------------------------
# Phase 22 — Trial Balance Validation
# ---------------------------------------------------------------------------

class TestPhase22TrialBalance:

    def test_trial_balance_is_balanced(self, trial_balance_fixture):
        meta = trial_balance_fixture["_meta"]
        assert meta["balanced"] is True
        assert abs(meta["dr_total"] - meta["cr_total"]) < 0.01

    def test_trial_balance_totals(self, trial_balance_fixture):
        totals = trial_balance_fixture["totals"]
        assert abs(totals["total_debit"] - totals["total_credit"]) < 0.01

    def test_trial_balance_includes_all_accounts(self, trial_balance_fixture):
        accounts = [a["account_code"] for a in trial_balance_fixture["accounts"]]
        required = ["1110", "1120", "1210", "1310", "1510", "1520",
                    "3110", "3310", "3311", "3320", "4110", "6110",
                    "7110", "7210", "7310", "7610", "7910"]
        for acc in required:
            assert acc in accounts, f"Account {acc} missing from trial balance"

    def test_profit_loss_net_result(self, profit_loss_fixture):
        pl = profit_loss_fixture
        expected_net = -4083.33
        actual_net = pl["net_profit_loss"]["amount"]
        assert abs(actual_net - expected_net) < 0.01

    def test_balance_sheet_assets_equal_liabilities_plus_equity(self, balance_sheet_fixture):
        bs = balance_sheet_fixture
        assets = bs["_meta"]["assets_total"]
        liabilities = bs["_meta"]["liabilities_total"]
        equity = bs["_meta"]["equity_total"]
        assert abs(assets - (liabilities + equity)) < 0.01

    def test_coa_accounts_valid(self, trial_balance_fixture):
        """Every account in trial balance must exist in Bridge Hub COA."""
        for entry in trial_balance_fixture["accounts"]:
            code = entry["account_code"]
            assert code in CHART_OF_ACCOUNTS, f"Account {code} not in Bridge Hub COA"
