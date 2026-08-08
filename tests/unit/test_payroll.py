"""Unit tests for Georgian payroll / tax calculations (no DB required)."""
import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
import os
from unittest.mock import AsyncMock, MagicMock

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

def _mock_request(role: str = "admin"):
    req = MagicMock()
    req.state.tenant_id = "tenant_a"
    req.state.role = role
    req.state.permissions = ["reports:read"]
    return req


def test_tax_salary_endpoint_uses_2pct_employee_and_2pct_employer_pension():
    from app.api.routes_tax import SalaryRequest, calculate_salary

    result = calculate_salary(SalaryRequest(gross_salary=3000, include_pension=True), _mock_request())
    data = result["data"]

    assert data["income_tax_20pct"] == 600
    assert data["pension_employee_2pct"] == 60
    assert data["pension_employee_2pct_alias"] == 60  # renamed: was pension_employee_4pct (misleading), value is 2%
    assert data["pension_employer_2pct"] == 60
    assert data["net_salary"] == 2340
    assert data["total_employer_cost"] == 3060


def test_tax_corporate_endpoint_uses_georgian_gross_up():
    from app.api.routes_tax import CorporateRequest, calculate_corporate

    result = calculate_corporate(CorporateRequest(profit=100000, distributed=True), _mock_request())
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


def test_payroll_service_gross_1000_net_780_with_employee_pension():
    from app.api.services.payroll_service import calculate_employee_payroll

    result = calculate_employee_payroll(1000, "Nino", employee_id="01001001001", period="2026-05")

    assert result["pit_20pct"] == 200.0
    assert result["payg_2pct"] == 20.0
    assert result["employer_pension_2pct"] == 20.0
    assert result["net_salary"] == 780.0
    assert result["total_employer_cost"] == 1020.0


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


def _make_payroll_conn():
    inserted = []
    _next_id = [0]

    async def _fetchrow(sql, *args):
        _next_id[0] += 1
        row = dict(zip(
            ["date", "description", "partner", "amount",
             "debit_account", "credit_account", "account_code",
             "reason", "confidence", "status", "source_type", "tenant_id"],
            args,
        ))
        row["id"] = _next_id[0]
        inserted.append(row)
        return row

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(side_effect=_fetchrow)
    conn._inserted = inserted

    @asynccontextmanager
    async def _tx():
        yield conn

    conn.transaction = MagicMock(return_value=_tx())

    @asynccontextmanager
    async def _ctx():
        yield conn

    return _ctx, conn


def test_generate_payroll_drafts_creates_employer_pension_entry(monkeypatch):
    from app.api.services import payroll_service

    ctx, conn = _make_payroll_conn()
    monkeypatch.setattr(payroll_service, "get_conn", ctx)
    payroll = payroll_service.calculate_payroll([{"gross_salary": 3000, "name": "Nino"}], period="2026-05")

    result = asyncio.run(payroll_service.generate_payroll_drafts(payroll, tenant_id="tenant-a"))

    assert result["ok"] is True
    assert result["drafts_created"] == 4
    reasons = [r["reason"] for r in conn._inserted]
    assert "payroll_employer_pension" in reasons
    pension = next(r for r in conn._inserted if r["reason"] == "payroll_employer_pension")
    assert pension["amount"] == 60.0
    assert pension["debit_account"] == "7220"
    assert pension["credit_account"] == "3335"


def test_payroll_run_queries_are_tenant_scoped():
    from pathlib import Path

    source = Path("app/api/services/payroll_service.py").read_text(encoding="utf-8")

    assert "FROM employees" in source
    assert "WHERE tenant_id = %s AND status = 'active'" in source
    assert "FROM payroll_runs" in source
    assert "WHERE id = %s AND tenant_id = %s" in source
    assert "JOIN payroll_runs pr" in source
    assert "pr.id = line.run_id AND pr.tenant_id = line.tenant_id" in source


def _payroll_run(status="draft", draft_ids=None):
    return {
        "id": 7,
        "tenant_id": "tenant-a",
        "period": "2026-05",
        "status": status,
        "draft_ids": draft_ids or [],
        "lines": [
            {
                "employee_name": "Nino",
                "employee_id": "EMP-1",
                "personal_number": "01001001001",
                "gross_salary": 1000,
                "pit_20pct": 200,
                "employee_pension_2pct": 20,
                "employer_pension_2pct": 20,
                "net_salary": 780,
                "total_employer_cost": 1020,
            }
        ],
    }


def _make_finalize_conn(claimed_id=7):
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetchval = AsyncMock(return_value=claimed_id)

    @asynccontextmanager
    async def _ctx():
        yield conn

    return _ctx, conn


def test_payroll_run_finalization_creates_journal_drafts_only(monkeypatch):
    from app.api.services import payroll_service

    draft_run = _payroll_run("draft")
    updated_run = _payroll_run("pending_approval", draft_ids=[101, 102, 103, 104])
    get_run = AsyncMock(side_effect=[draft_run, updated_run])
    generate = AsyncMock(return_value={"ok": True, "draft_ids": [101, 102, 103, 104]})
    ctx, conn = _make_finalize_conn()
    monkeypatch.setattr(payroll_service, "get_payroll_run", get_run)
    monkeypatch.setattr(payroll_service, "generate_payroll_drafts", generate)
    monkeypatch.setattr(payroll_service, "get_conn", ctx)

    result = asyncio.run(payroll_service.finalize_payroll_run("tenant-a", 7))

    assert result["status"] == "pending_approval"
    assert result["drafts"]["draft_ids"] == [101, 102, 103, 104]
    generate.assert_awaited_once()
    executed_sql = "\n".join(str(call.args[0]) for call in conn.execute.await_args_list)
    assert "UPDATE payroll_runs" in executed_sql
    assert conn.fetchval.await_args.args[1:] == (7, "tenant-a")


def test_payroll_run_repeated_finalization_does_not_duplicate_drafts(monkeypatch):
    from app.api.services import payroll_service

    finalized_run = _payroll_run("pending_approval", draft_ids=[101, 102, 103, 104])
    get_run = AsyncMock(return_value=finalized_run)
    generate = AsyncMock(return_value={"ok": True, "draft_ids": [201, 202, 203, 204]})
    monkeypatch.setattr(payroll_service, "get_payroll_run", get_run)
    monkeypatch.setattr(payroll_service, "generate_payroll_drafts", generate)

    result = asyncio.run(payroll_service.finalize_payroll_run("tenant-a", 7))

    assert result["status"] == "pending_approval"
    assert result["already_finalized"] is True
    assert result["drafts"]["drafts_created"] == 0
    assert result["drafts"]["draft_ids"] == [101, 102, 103, 104]
    generate.assert_not_awaited()


def test_payroll_run_concurrent_finalization_loser_does_not_create_drafts(monkeypatch):
    from app.api.services import payroll_service

    draft_run = _payroll_run("draft")
    finalizing_run = _payroll_run("finalizing")
    get_run = AsyncMock(side_effect=[draft_run, finalizing_run])
    generate = AsyncMock(return_value={"ok": True, "draft_ids": [201, 202, 203, 204]})
    ctx, conn = _make_finalize_conn(claimed_id=None)
    monkeypatch.setattr(payroll_service, "get_payroll_run", get_run)
    monkeypatch.setattr(payroll_service, "generate_payroll_drafts", generate)
    monkeypatch.setattr(payroll_service, "get_conn", ctx)

    try:
        asyncio.run(payroll_service.finalize_payroll_run("tenant-a", 7))
    except ValueError as exc:
        assert str(exc) == "PAYROLL_RUN_FINALIZATION_IN_PROGRESS"
    else:
        raise AssertionError("Expected concurrent finalize loser to be rejected")

    conn.fetchval.assert_awaited_once()
    generate.assert_not_awaited()


def test_payroll_journal_entries_each_balanced(monkeypatch):
    """Each payroll draft must have a positive amount with distinct Dr/Cr accounts (balanced entry)."""
    from app.api.services import payroll_service

    ctx, conn = _make_payroll_conn()
    monkeypatch.setattr(payroll_service, "get_conn", ctx)
    payroll = payroll_service.calculate_payroll([{"gross_salary": 3000, "name": "Nino"}], period="2026-05")
    asyncio.run(payroll_service.generate_payroll_drafts(payroll, tenant_id="tenant-a"))

    for row in conn._inserted:
        assert row["amount"] > 0, f"Draft amount must be positive, got {row['amount']}"
        assert row["debit_account"] != row["credit_account"], \
            f"Dr and Cr must differ; both were '{row['debit_account']}'"

    amounts = sorted(r["amount"] for r in conn._inserted)
    assert amounts == sorted([3000.0, 60.0, 600.0, 60.0]), \
        f"Expected [60, 60, 600, 3000], got {amounts}"


def test_rsge_xml_escapes_employee_identity_fields():
    from app.api.services.payroll_service import generate_rsge_xml

    xml = generate_rsge_xml({
        "period": "2026-05",
        "employees": [{
            "employee_name": "Nino & <Partner>",
            "employee_id": "ID&123",
            "gross_salary": 1000,
            "payg_2pct": 20,
            "pit_20pct": 200,
            "net_salary": 780,
        }],
        "totals": {
            "gross": 1000,
            "payg": 20,
            "pit": 200,
            "employer_pension": 20,
            "net": 780,
        },
    })

    assert "Nino &amp; &lt;Partner&gt;" in xml
    assert "ID&amp;123" in xml
    assert "<Name>Nino & <Partner></Name>" not in xml
