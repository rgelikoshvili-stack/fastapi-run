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

# --- API-level tax endpoint regression tests ---

def test_tax_salary_endpoint_uses_2pct_employee_and_2pct_employer_pension():
    from app.api.routes_tax import SalaryRequest, calculate_salary

    result = calculate_salary(SalaryRequest(gross_salary=3000, include_pension=True))
    data = result["data"]

    assert data["income_tax_20pct"] == 600
    assert data["pension_employee_2pct"] == 60
    assert data["pension_employee_4pct"] == 60  # compatibility alias, value is now 2%
    assert data["pension_employer_2pct"] == 60
    assert data["net_salary"] == 2340
    assert data["total_employer_cost"] == 3060


def test_tax_corporate_endpoint_uses_georgian_gross_up():
    from app.api.routes_tax import CorporateRequest, calculate_corporate

    result = calculate_corporate(CorporateRequest(profit=100000, distributed=True))
    data = result["data"]

    assert data["tax_base"] == 117647.06
    assert data["corporate_tax"] == 17647.06
    assert data["net_after_tax"] == 82352.94
    assert data["calculation_method"] == "georgian_estonian_model_gross_up"


def test_payroll_service_includes_employer_pension_in_totals():
    from app.api.services.payroll_service import calculate_payroll

    result = calculate_payroll([{"gross_salary": 3000, "name": "Nino"}], period="2026-05")
    emp = result["employees"][0]

    assert emp["payg_2pct"] == 60.0
    assert emp["pit_20pct"] == 600.0
    assert emp["employer_pension_2pct"] == 60.0
    assert emp["net_salary"] == 2340.0
    assert emp["total_employer_cost"] == 3060.0
    assert result["totals"]["employer_pension"] == 60.0
    assert result["totals"]["total_employer_cost"] == 3060.0


class _FakePayrollCursor:
    def __init__(self):
        self.calls = []
        self.next_id = 0

    def execute(self, sql, params=None):
        self.calls.append((sql, params or ()))

    def fetchone(self):
        self.next_id += 1
        return {"id": self.next_id}

    def close(self):
        pass


class _FakePayrollConn:
    def __init__(self):
        self.cursor_obj = _FakePayrollCursor()
        self.committed = False
        self.rolled_back = False

    def cursor(self, *args, **kwargs):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def test_generate_payroll_drafts_creates_employer_pension_entry(monkeypatch):
    from app.api.services import payroll_service

    fake_conn = _FakePayrollConn()
    monkeypatch.setattr(payroll_service, "get_db", lambda: fake_conn)
    payroll = payroll_service.calculate_payroll([{"gross_salary": 3000, "name": "Nino"}], period="2026-05")

    result = payroll_service.generate_payroll_drafts(payroll, tenant_id="tenant-a")

    assert result["ok"] is True
    assert result["drafts_created"] == 4
    assert fake_conn.committed is True
    reasons = [params[7] for _, params in fake_conn.cursor_obj.calls]
    assert "payroll_employer_pension" in reasons
    employer_params = [params for _, params in fake_conn.cursor_obj.calls if params[7] == "payroll_employer_pension"][0]
    assert employer_params[3] == 60.0
    assert employer_params[4] == "7220"
    assert employer_params[5] == "3335"


def test_payroll_journal_entries_each_balanced(monkeypatch):
    """Each payroll draft must have a positive amount with distinct Dr/Cr accounts (balanced entry)."""
    from app.api.services import payroll_service

    fake_conn = _FakePayrollConn()
    monkeypatch.setattr(payroll_service, "get_db", lambda: fake_conn)
    payroll = payroll_service.calculate_payroll([{"gross_salary": 3000, "name": "Nino"}], period="2026-05")
    payroll_service.generate_payroll_drafts(payroll, tenant_id="tenant-a")

    # Each INSERT: (date, desc, partner, amount, dr_account, cr_account, account_code, reason, ...)
    for _, params in fake_conn.cursor_obj.calls:
        amount, dr_account, cr_account = params[3], params[4], params[5]
        assert amount > 0, f"Draft amount must be positive, got {amount}"
        assert dr_account != cr_account, f"Dr and Cr must differ; both were '{dr_account}'"

    # Amounts must cover all four components of the payroll
    amounts = sorted(params[3] for _, params in fake_conn.cursor_obj.calls)
    assert amounts == sorted([3000.0, 60.0, 600.0, 60.0]), (
        f"Expected [60, 60, 600, 3000], got {amounts}"
    )
