"""Unit tests for Georgian payroll / tax calculations (no DB required)."""
from decimal import Decimal
import os

os.environ.setdefault("TEST_MODE", "1")
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("JWT_SECRET", "test-secret-for-ci")

from app.policy.localization.georgia_pack import (
    calculate_payg,
    calculate_cit,
    calculate_withholding,
    extract_vat,
    add_vat,
    PIT_RATE,
    PAYG_RATE,
    VAT_RATE,
)


# ── PIT (Personal Income Tax 20%) ─────────────────────────────────────────────

def test_pit_rate_is_20_percent():
    assert PIT_RATE == Decimal("0.20")


def test_pit_calculation_gross_250():
    gross = Decimal("250")
    pit   = (gross * PIT_RATE).quantize(Decimal("0.01"))
    payg  = (gross * PAYG_RATE).quantize(Decimal("0.01"))
    assert pit  == Decimal("50.00")
    assert payg == Decimal("5.00")
    net = gross - pit - payg
    assert net == Decimal("195.00")


def test_pit_calculation_gross_1000():
    gross = Decimal("1000")
    pit   = (gross * PIT_RATE).quantize(Decimal("0.01"))
    assert pit == Decimal("200.00")


# ── Gross-up (net → gross) ────────────────────────────────────────────────────

def test_gross_up_net_150():
    """net = gross * (1 - PIT - PAYG) = gross * 0.78"""
    net   = Decimal("150")
    rate  = 1 - float(PIT_RATE) - float(PAYG_RATE)  # 0.78
    gross = (net / Decimal(str(rate))).quantize(Decimal("0.01"))
    pit   = (gross * PIT_RATE).quantize(Decimal("0.01"))
    payg  = (gross * PAYG_RATE).quantize(Decimal("0.01"))
    # verify round-trip: gross - pit - payg ≈ net (rounding tolerance ±0.02)
    calc_net = gross - pit - payg
    assert abs(float(calc_net) - float(net)) < 0.02


def test_gross_up_proportional():
    """doubling net should double gross"""
    def gross_from_net(n):
        d = Decimal(str(n))
        rate = 1 - float(PIT_RATE) - float(PAYG_RATE)
        return float((d / Decimal(str(rate))).quantize(Decimal("0.01")))

    assert abs(gross_from_net(300) - 2 * gross_from_net(150)) < 0.05


# ── Individual Entrepreneur (ი.მ) — no PIT withholding ──────────────────────

def test_sole_trader_withholding_resident_zero():
    """Resident ი.მ: withholding = 0 for dividend/interest/services"""
    for ptype in ("dividend", "interest", "services"):
        r = calculate_withholding(Decimal("150"), payment_type=ptype, is_resident=True)
        assert r["tax"] == 0.0, f"Expected 0 withholding for resident {ptype}"
        assert r["net"] == 150.0


def test_sole_trader_royalty_resident_10pct():
    """Resident royalty: 10% withholding still applies"""
    r = calculate_withholding(Decimal("100"), payment_type="royalty", is_resident=True)
    assert r["tax"] == 10.0
    assert r["net"] == 90.0


def test_nonresident_dividend_5pct():
    r = calculate_withholding(Decimal("200"), payment_type="dividend", is_resident=False)
    assert r["tax"] == 10.0
    assert r["net"] == 190.0


# ── PAYG (pension 2%) ────────────────────────────────────────────────────────

def test_payg_rate_is_2_percent():
    assert PAYG_RATE == Decimal("0.02")


def test_payg_calculation():
    r = calculate_payg(Decimal("500"))
    assert r["payg"] == 10.0
    assert r["net"]  == 490.0
    assert r["gross"] == 500.0


# ── VAT ──────────────────────────────────────────────────────────────────────

def test_vat_rate_is_18_percent():
    assert VAT_RATE == Decimal("0.18")


def test_extract_vat_from_118():
    r = extract_vat(Decimal("118"))
    assert r["base"]  == 100.0
    assert r["vat"]   == 18.0
    assert r["total"] == 118.0


def test_add_vat_to_100():
    r = add_vat(Decimal("100"))
    assert r["base"]  == 100.0
    assert r["vat"]   == 18.0
    assert r["total"] == 118.0


def test_vat_round_trip():
    base = Decimal("250")
    added   = add_vat(base)
    extracted = extract_vat(Decimal(str(added["total"])))
    assert abs(extracted["base"] - float(base)) < 0.01


# ── CIT (15% Estonian model) ─────────────────────────────────────────────────

def test_cit_distributed_profit_1000():
    r = calculate_cit(Decimal("1000"))
    assert r["distributed_profit"] == 1000.0
    # tax_base = 1000 / 0.85 ≈ 1176.47; cit = 1176.47 * 0.15 ≈ 176.47
    assert abs(r["tax_base"] - 1176.47) < 0.01
    assert abs(r["cit"] - 176.47) < 0.01
    assert r["net_dividend"] == round(1000 - r["cit"], 2)


def test_cit_journal_entries_present():
    r = calculate_cit(Decimal("500"))
    assert r["journal_step1"]["debit"]  == "4210"
    assert r["journal_step1"]["credit"] == "3370"
    assert len(r["journal_step2"]) == 2
