"""
tests/unit/test_georgia_pack.py
Georgia Pack — unit tests for tax calculators.
No DB required — pure math, all in-process.

API reference (app/policy/localization/georgia_pack.py):
  extract_vat(amount_with_vat) -> {base, vat, total}        -- VAT inclusive
  add_vat(base_amount)         -> {base, vat, total}        -- VAT exclusive
  calculate_payg(gross_salary) -> {gross, payg, net}
  calculate_cit(distributed_profit) -> {distributed_profit, tax_base, cit, net_dividend}
  calculate_withholding(amount, payment_type, is_resident) -> {amount, rate_pct, tax, net}
  calculate_dividend(gross_profit, recipient_is_resident) -> {cit, net_to_shareholder, total_tax, ...}
"""
import pytest
from decimal import Decimal
from app.policy.localization.georgia_pack import (
    calculate_cit,
    calculate_withholding,
    calculate_dividend,
    extract_vat,
    add_vat,
    calculate_payg,
)


# ──────────────────────────────────────────────
# CIT (Estonian model — 15% on grossed-up profit)
# ──────────────────────────────────────────────
class TestCIT:
    def test_cit_known_values(self):
        # distributed_profit=10000 → tax_base=10000/0.85≈11764.71, cit≈1764.71
        result = calculate_cit(Decimal("10000"))
        assert result["tax_base"] == pytest.approx(11764.71, abs=0.1)
        assert result["cit"] == pytest.approx(1764.71, abs=0.1)
        assert result["net_dividend"] == pytest.approx(8235.29, abs=0.1)

    def test_cit_8500(self):
        # distributed_profit=8500 → tax_base≈10000, cit=1500
        result = calculate_cit(Decimal("8500"))
        assert result["tax_base"] == pytest.approx(10000.0, abs=0.5)
        assert result["cit"] == pytest.approx(1500.0, abs=0.5)

    def test_cit_net_plus_cit_equals_tax_base_times_rate(self):
        result = calculate_cit(Decimal("5000"))
        # net_dividend = distributed_profit - cit
        expected_net = result["distributed_profit"] - result["cit"]
        assert result["net_dividend"] == pytest.approx(expected_net, abs=0.02)

    def test_cit_has_required_keys(self):
        result = calculate_cit(Decimal("1000"))
        for key in ("distributed_profit", "tax_base", "cit", "net_dividend"):
            assert key in result, f"Missing key: {key}"

    def test_cit_zero(self):
        result = calculate_cit(Decimal("0"))
        assert result["cit"] == pytest.approx(0.0, abs=0.01)


# ──────────────────────────────────────────────
# VAT (18%)
# ──────────────────────────────────────────────
class TestVAT:
    def test_extract_vat_5900(self):
        # 5900 with VAT → net=5000, vat=900
        result = extract_vat(Decimal("5900"))
        assert result["base"] == pytest.approx(5000.0, abs=1.0)
        assert result["vat"] == pytest.approx(900.0, abs=1.0)
        assert result["total"] == pytest.approx(5900.0, abs=0.01)

    def test_extract_vat_118(self):
        result = extract_vat(Decimal("118"))
        assert result["base"] == pytest.approx(100.0, abs=0.5)
        assert result["vat"] == pytest.approx(18.0, abs=0.5)

    def test_add_vat_1000(self):
        result = add_vat(Decimal("1000"))
        assert result["base"] == pytest.approx(1000.0, abs=0.01)
        assert result["vat"] == pytest.approx(180.0, abs=0.01)
        assert result["total"] == pytest.approx(1180.0, abs=0.01)

    def test_add_vat_10000(self):
        result = add_vat(Decimal("10000"))
        assert result["vat"] == pytest.approx(1800.0, abs=0.01)
        assert result["total"] == pytest.approx(11800.0, abs=0.01)

    def test_vat_total_equals_base_plus_vat(self):
        result = add_vat(Decimal("2500"))
        assert abs(result["base"] + result["vat"] - result["total"]) < 0.02

    def test_extract_vat_roundtrip(self):
        # extract_vat(add_vat(1000).total) should recover base=1000
        added = add_vat(Decimal("1000"))
        extracted = extract_vat(Decimal(str(added["total"])))
        assert extracted["base"] == pytest.approx(1000.0, abs=0.5)


# ──────────────────────────────────────────────
# PAYG (საპენსიო 2%)
# ──────────────────────────────────────────────
class TestPayg:
    def test_payg_3000(self):
        result = calculate_payg(Decimal("3000"))
        assert result["payg"] == pytest.approx(60.0, abs=0.01)
        assert result["net"] == pytest.approx(2940.0, abs=0.01)
        assert result["gross"] == pytest.approx(3000.0, abs=0.01)

    def test_payg_rate_2pct(self):
        result = calculate_payg(Decimal("5000"))
        assert result["payg"] == pytest.approx(100.0, abs=0.01)

    def test_payg_keys(self):
        result = calculate_payg(Decimal("1000"))
        for key in ("gross", "payg", "net"):
            assert key in result


# ──────────────────────────────────────────────
# Withholding
# ──────────────────────────────────────────────
class TestWithholding:
    def test_dividend_resident_zero_rate(self):
        # Resident dividend: no withholding per Georgian tax code
        result = calculate_withholding(Decimal("1000"), payment_type="dividend", is_resident=True)
        assert result["rate_pct"] == 0
        assert result["tax"] == pytest.approx(0.0, abs=0.01)
        assert result["net"] == pytest.approx(1000.0, abs=0.01)

    def test_dividend_nonresident_5pct(self):
        result = calculate_withholding(Decimal("1000"), payment_type="dividend", is_resident=False)
        assert result["rate_pct"] == 5
        assert result["tax"] == pytest.approx(50.0, abs=0.01)
        assert result["net"] == pytest.approx(950.0, abs=0.01)

    def test_royalty_10pct(self):
        result = calculate_withholding(Decimal("2000"), payment_type="royalty", is_resident=True)
        assert result["rate_pct"] == 10
        assert result["tax"] == pytest.approx(200.0, abs=0.01)
        assert result["net"] == pytest.approx(1800.0, abs=0.01)

    def test_services_nonresident_10pct(self):
        result = calculate_withholding(Decimal("5000"), payment_type="services", is_resident=False)
        assert result["rate_pct"] == 10
        assert result["tax"] == pytest.approx(500.0, abs=0.01)

    def test_interest_nonresident_5pct(self):
        result = calculate_withholding(Decimal("1000"), payment_type="interest", is_resident=False)
        assert result["rate_pct"] == 5
        assert result["tax"] == pytest.approx(50.0, abs=0.01)

    def test_withholding_keys(self):
        result = calculate_withholding(Decimal("1000"), "dividend", False)
        for key in ("amount", "rate_pct", "tax", "net"):
            assert key in result


# ──────────────────────────────────────────────
# Dividend (CIT + withholding full flow)
# ──────────────────────────────────────────────
class TestDividend:
    def test_dividend_resident_no_withholding(self):
        # Resident: CIT applied, no withholding on dividend
        result = calculate_dividend(Decimal("10000"), recipient_is_resident=True)
        assert result["withholding_tax"] == pytest.approx(0.0, abs=0.01)
        assert result["cit"] == pytest.approx(1764.71, abs=0.5)
        assert result["net_to_shareholder"] == pytest.approx(8235.29, abs=0.5)

    def test_dividend_nonresident_cit_plus_withholding(self):
        # Non-resident: CIT + 5% withholding on net_after_cit
        result = calculate_dividend(Decimal("10000"), recipient_is_resident=False)
        # net_after_cit ≈ 8235.29, withholding = 8235.29 * 0.05 ≈ 411.76
        assert result["withholding_tax"] == pytest.approx(411.76, abs=1.0)
        assert result["net_to_shareholder"] < result["net_after_cit"]

    def test_dividend_total_tax(self):
        result = calculate_dividend(Decimal("10000"))
        assert result["total_tax"] == pytest.approx(
            result["cit"] + result["withholding_tax"], abs=0.02
        )

    def test_dividend_has_required_keys(self):
        result = calculate_dividend(Decimal("5000"))
        for key in ("cit", "net_after_cit", "withholding_tax", "net_to_shareholder", "total_tax"):
            assert key in result, f"Missing key: {key}"

    def test_dividend_zero(self):
        result = calculate_dividend(Decimal("0"))
        assert result["total_tax"] == pytest.approx(0.0, abs=0.01)
