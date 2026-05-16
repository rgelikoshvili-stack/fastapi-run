"""
11C-H26 — Synthetic Fixture Expected Totals Contract Tests

Validates H25 synthetic posted-ledger fixture expected totals using pure local
JSON calculations. No DB, no network, no subprocess, no SQL, no migrations.
All assertions are read-only fixture JSON calculations using Decimal arithmetic.
"""

import ast
import json
import pathlib
import re
from collections import defaultdict
from decimal import Decimal

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ROOT    = pathlib.Path(__file__).parents[2]
_DOC     = _ROOT / "docs" / "synthetic-fixture-expected-totals-validation.md"
_FIXTURE = _ROOT / "tests" / "fixtures" / "posted_ledger" / "synthetic_posted_ledger_fixture_pack.json"
_THIS    = pathlib.Path(__file__)

STANDARD_NET = {"posted", "correction"}
EXCLUDED_NET = {"reversed", "voided"}
INVALID_STATUSES = {"draft", "approved", "auto_approved", "simulated_success"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load():
    assert _FIXTURE.exists(), f"Fixture missing: {_FIXTURE}"
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _doc_text():
    assert _DOC.exists(), f"H26 doc missing: {_DOC}"
    return _DOC.read_text(encoding="utf-8")


def _alpha_net_headers(data):
    return [
        h for h in data["journal_entry_headers"]
        if h["tenant_id"] == "tenant_alpha" and h["status"] in STANDARD_NET
    ]


def _alpha_net_ids(data):
    return {h["id"] for h in _alpha_net_headers(data)}


def _alpha_net_lines(data):
    ids = _alpha_net_ids(data)
    return [l for l in data["journal_entry_lines"] if l["journal_entry_id"] in ids]


def _account_totals(lines):
    dr = defaultdict(Decimal)
    cr = defaultdict(Decimal)
    for l in lines:
        dr[l["account_code"]] += Decimal(str(l["debit"]))
        cr[l["account_code"]] += Decimal(str(l["credit"]))
    return dr, cr


def _d(val):
    return Decimal(str(val))


# ---------------------------------------------------------------------------
# Test 1: doc exists
# ---------------------------------------------------------------------------


def test_h26_doc_exists():
    assert _DOC.exists(), f"Missing: {_DOC}"
    assert _DOC.stat().st_size > 0, "H26 doc is empty"


# ---------------------------------------------------------------------------
# Test 2: non-action statement present
# ---------------------------------------------------------------------------


def test_h26_non_action_statement_present():
    raw  = _doc_text()
    text = raw.lower().replace("**", "").replace("*", "")
    assert "does not create a db" in text or "does not create db" in text or "does not create a db." in text or "does not create" in text, \
        "H26 must state it does not create a DB"
    assert "does not connect" in text, "H26 must state it does not connect to a DB"
    assert "does not execute sql" in text, "H26 must state it does not execute SQL"
    assert "does not run migrations" in text, "H26 must state it does not run migrations"
    assert "does not load" in text, "H26 must state it does not load fixtures into DB"
    assert "does not modify runtime" in text or "does not modify runtime report" in text, \
        "H26 must state it does not modify runtime behavior"


# ---------------------------------------------------------------------------
# Test 3: fixture loads and has expected_reports
# ---------------------------------------------------------------------------


def test_fixture_loads_and_has_expected_reports():
    data = _load()
    assert "expected_reports" in data, "expected_reports section missing"
    assert "tenant_alpha" in data["expected_reports"], "tenant_alpha section missing"
    tenant_alpha = data["expected_reports"]["tenant_alpha"]
    required = [
        "trial_balance", "pl_summary", "pl_detail",
        "balance_sheet_summary", "balance_sheet_detail",
        "vat_register", "account_ledger", "counterparty_ledger",
        "payroll_ledger", "journal_entries_list", "cashflow",
    ]
    for r in required:
        assert r in tenant_alpha, f"expected_reports.tenant_alpha.{r} missing"


# ---------------------------------------------------------------------------
# Test 4: standard net status set is documented
# ---------------------------------------------------------------------------


def test_standard_net_status_set_is_documented():
    text = _doc_text().lower()
    assert "posted" in text,     "standard net status 'posted' must be documented"
    assert "correction" in text, "standard net status 'correction' must be documented"
    assert "reversed" in text,   "excluded status 'reversed' must be documented"
    assert "voided" in text,     "excluded status 'voided' must be documented"
    assert "standard net" in text, "standard net filter concept must be documented"


# ---------------------------------------------------------------------------
# Test 5: posted and correction headers balance
# ---------------------------------------------------------------------------


def test_posted_and_correction_headers_balance():
    data = _load()
    net_headers = _alpha_net_headers(data)
    assert len(net_headers) > 0, "No standard-net headers found"
    for h in net_headers:
        dr = _d(h["total_debit"])
        cr = _d(h["total_credit"])
        assert dr == cr, (
            f"Header {h.get('metadata_json',{}).get('fixture','?')} "
            f"id={h['id']} not balanced: DR={dr} CR={cr}"
        )


# ---------------------------------------------------------------------------
# Test 6: reversed and voided excluded from standard net
# ---------------------------------------------------------------------------


def test_reversed_and_voided_excluded_from_standard_net():
    data = _load()
    alpha_headers = [h for h in data["journal_entry_headers"] if h["tenant_id"] == "tenant_alpha"]
    reversed_ids = {h["id"] for h in alpha_headers if h["status"] == "reversed"}
    voided_ids   = {h["id"] for h in alpha_headers if h["status"] == "voided"}
    net_ids      = _alpha_net_ids(data)
    assert not (reversed_ids & net_ids), "Reversed headers must not be in standard net"
    assert not (voided_ids  & net_ids), "Voided headers must not be in standard net"
    expected_count = data["expected_reports"]["tenant_alpha"]["standard_net_entry_count"]
    assert len(_alpha_net_headers(data)) == expected_count, (
        f"Standard net count: expected {expected_count}, got {len(_alpha_net_headers(data))}"
    )


# ---------------------------------------------------------------------------
# Test 7: tenant_alpha excludes tenant_beta rows
# ---------------------------------------------------------------------------


def test_tenant_alpha_excludes_tenant_beta_rows():
    data  = _load()
    lines = _alpha_net_lines(data)
    tenant_ids = {l["tenant_id"] for l in lines}
    assert "tenant_beta" not in tenant_ids, "tenant_beta lines must not appear in tenant_alpha standard net"
    # Also verify tenant_beta's 9999 amount is absent from trial balance totals
    dr, cr = _account_totals(lines)
    all_values = list(dr.values()) + list(cr.values())
    assert _d("9999") not in all_values, "tenant_beta amount 9999 must not appear in tenant_alpha totals"


# ---------------------------------------------------------------------------
# Test 8: trial balance expected totals match calculated
# ---------------------------------------------------------------------------


def test_trial_balance_expected_totals_match_calculated():
    data  = _load()
    lines = _alpha_net_lines(data)
    dr, cr = _account_totals(lines)
    tb = data["expected_reports"]["tenant_alpha"]["trial_balance"]["accounts"]

    account_expected = {
        "1010": ("net_dr", _d("4475")),
        "1200": ("net_dr", _d("1300")),
        "1211": ("net_dr", _d("180")),
        "1500": ("net_dr", _d("5000")),
        "2100": ("net_cr", _d("0")),
        "2200": ("net_cr", _d("180")),
        "2300": ("net_cr", _d("1600")),
        "2310": ("net_cr", _d("400")),
        "3000": ("net_cr", _d("10000")),
        "4100": ("net_cr", _d("1800")),
        "4200": ("net_cr", _d("500")),
        "5100": ("net_dr", _d("1500")),
        "5200": ("net_dr", _d("2000")),
        "5300": ("net_dr", _d("25")),
    }
    for acct, (direction, expected_net) in account_expected.items():
        if direction == "net_dr":
            calculated = dr[acct] - cr[acct]
        else:
            calculated = cr[acct] - dr[acct]
        assert calculated == expected_net, (
            f"Account {acct} {direction}: calculated={calculated}, expected={expected_net}"
        )
        # Also verify expected_reports fixture value matches
        acct_key = [k for k in tb.keys() if k.startswith(acct)]
        if acct_key:
            fixture_val = _d(tb[acct_key[0]][direction])
            assert fixture_val == expected_net, (
                f"Account {acct} fixture {direction}={fixture_val} disagrees with calculated={expected_net}"
            )


# ---------------------------------------------------------------------------
# Test 9: trial balance debits equal credits
# ---------------------------------------------------------------------------


def test_trial_balance_debits_equal_credits():
    data  = _load()
    lines = _alpha_net_lines(data)
    dr, cr = _account_totals(lines)
    all_accounts = set(dr.keys()) | set(cr.keys())
    net_dr_sum = sum(max(dr[a] - cr[a], Decimal(0)) for a in all_accounts)
    net_cr_sum = sum(max(cr[a] - dr[a], Decimal(0)) for a in all_accounts)
    assert net_dr_sum == net_cr_sum, f"Trial balance out of balance: DR={net_dr_sum} CR={net_cr_sum}"
    assert net_dr_sum == _d("14480"), f"Trial balance total expected 14480, got {net_dr_sum}"
    fixture_tb = data["expected_reports"]["tenant_alpha"]["trial_balance"]
    assert _d(fixture_tb["total_dr"]) == _d("14480"), "Fixture trial_balance.total_dr must be 14480"
    assert _d(fixture_tb["total_cr"]) == _d("14480"), "Fixture trial_balance.total_cr must be 14480"


# ---------------------------------------------------------------------------
# Test 10: P&L summary matches calculated revenue, expenses, net income
# ---------------------------------------------------------------------------


def test_pl_summary_matches_calculated_revenue_expenses_net_income():
    data  = _load()
    lines = _alpha_net_lines(data)
    dr, cr = _account_totals(lines)
    income_accounts  = ["4100", "4200"]
    expense_accounts = ["5100", "5200", "5300"]
    total_income  = sum(max(cr[a] - dr[a], Decimal(0)) for a in income_accounts)
    total_expense = sum(max(dr[a] - cr[a], Decimal(0)) for a in expense_accounts)
    net_pl = total_income - total_expense
    assert total_income  == _d("2300"),   f"total_income: {total_income}"
    assert total_expense == _d("3525"),   f"total_expense: {total_expense}"
    assert net_pl        == _d("-1225"),  f"net_profit_loss: {net_pl}"
    pl = data["expected_reports"]["tenant_alpha"]["pl_summary"]
    assert _d(pl["total_income"])    == _d("2300"),  "Fixture pl_summary.total_income mismatch"
    assert _d(pl["total_expense"])   == _d("3525"),  "Fixture pl_summary.total_expense mismatch"
    assert _d(pl["net_profit_loss"]) == _d("-1225"), "Fixture pl_summary.net_profit_loss mismatch"


# ---------------------------------------------------------------------------
# Test 11: P&L detail rolls up to summary
# ---------------------------------------------------------------------------


def test_pl_detail_rolls_up_to_summary():
    data = _load()
    pl_detail  = data["expected_reports"]["tenant_alpha"]["pl_detail"]
    pl_summary = data["expected_reports"]["tenant_alpha"]["pl_summary"]
    income_sum  = sum(_d(v) for v in pl_detail["income"].values())
    expense_sum = sum(_d(v) for v in pl_detail["expense"].values())
    assert income_sum  == _d(pl_summary["total_income"]),  f"P&L detail income {income_sum} != summary {pl_summary['total_income']}"
    assert expense_sum == _d(pl_summary["total_expense"]), f"P&L detail expense {expense_sum} != summary {pl_summary['total_expense']}"
    assert _d(pl_detail["net_profit_loss"]) == _d(pl_summary["net_profit_loss"]), "P&L detail net != summary net"


# ---------------------------------------------------------------------------
# Test 12: balance sheet summary matches calculated assets, liabilities, equity
# ---------------------------------------------------------------------------


def test_balance_sheet_summary_matches_calculated_assets_liabilities_equity():
    data  = _load()
    lines = _alpha_net_lines(data)
    dr, cr = _account_totals(lines)
    asset_accounts = ["1010", "1200", "1211", "1500"]
    liab_accounts  = ["2100", "2200", "2300", "2310"]
    total_assets = sum(max(dr[a] - cr[a], Decimal(0)) for a in asset_accounts)
    total_liab   = sum(max(cr[a] - dr[a], Decimal(0)) for a in liab_accounts)
    equity_cap   = max(cr["3000"] - dr["3000"], Decimal(0))
    net_pl       = max(cr["4100"]-dr["4100"], Decimal(0)) + max(cr["4200"]-dr["4200"], Decimal(0)) \
                 - max(dr["5100"]-cr["5100"], Decimal(0)) - max(dr["5200"]-cr["5200"], Decimal(0)) \
                 - max(dr["5300"]-cr["5300"], Decimal(0))
    total_equity = equity_cap + net_pl
    assert total_assets == _d("10955"),  f"Assets: {total_assets}"
    assert total_liab   == _d("2180"),   f"Liabilities: {total_liab}"
    assert total_equity == _d("8775"),   f"Equity: {total_equity}"
    assert total_assets == total_liab + total_equity, "Balance sheet equation violated"
    bs = data["expected_reports"]["tenant_alpha"]["balance_sheet_summary"]
    assert _d(bs["total_assets"])      == _d("10955"), "Fixture bs_summary.total_assets mismatch"
    assert _d(bs["total_liabilities"]) == _d("2180"),  "Fixture bs_summary.total_liabilities mismatch"
    assert _d(bs["total_equity"])      == _d("8775"),  "Fixture bs_summary.total_equity mismatch"


# ---------------------------------------------------------------------------
# Test 13: balance sheet detail rolls up to summary
# ---------------------------------------------------------------------------


def test_balance_sheet_detail_rolls_up_to_summary():
    data = _load()
    bsd = data["expected_reports"]["tenant_alpha"]["balance_sheet_detail"]
    bss = data["expected_reports"]["tenant_alpha"]["balance_sheet_summary"]
    asset_sum = sum(_d(v) for k, v in bsd["assets"].items() if k != "total")
    liab_sum  = sum(_d(v) for k, v in bsd["liabilities"].items() if k != "total")
    equity_sum = sum(_d(v) for k, v in bsd["equity"].items() if k != "total")
    assert asset_sum  == _d(bsd["assets"]["total"]),      "BS detail assets sum != total"
    assert liab_sum   == _d(bsd["liabilities"]["total"]), "BS detail liabilities sum != total"
    assert equity_sum == _d(bsd["equity"]["total"]),      "BS detail equity sum != total"
    assert _d(bsd["assets"]["total"])      == _d(bss["total_assets"]),      "BS detail assets != summary"
    assert _d(bsd["liabilities"]["total"]) == _d(bss["total_liabilities"]), "BS detail liabilities != summary"
    assert _d(bsd["equity"]["total"])      == _d(bss["total_equity"]),      "BS detail equity != summary"


# ---------------------------------------------------------------------------
# Test 14: VAT register matches calculated input/output/net
# ---------------------------------------------------------------------------


def test_vat_register_matches_calculated_input_output_net():
    data  = _load()
    lines = _alpha_net_lines(data)
    dr, cr = _account_totals(lines)
    vat_input  = max(dr["1211"] - cr["1211"], Decimal(0))
    vat_output = max(cr["2200"] - dr["2200"], Decimal(0))
    net_vat    = vat_output - vat_input
    assert vat_input  == _d("180"), f"VAT input: {vat_input}"
    assert vat_output == _d("180"), f"VAT output: {vat_output}"
    assert net_vat    == _d("0"),   f"Net VAT: {net_vat}"
    vr = data["expected_reports"]["tenant_alpha"]["vat_register"]
    assert _d(vr["vat_input_reclaimable"]) == _d("180"), "Fixture vat_input_reclaimable mismatch"
    assert _d(vr["vat_output_payable"])    == _d("180"), "Fixture vat_output_payable mismatch"
    assert _d(vr["net_vat_position"])      == _d("0"),   "Fixture net_vat_position mismatch"


# ---------------------------------------------------------------------------
# Test 15: account ledger expected accounts match fixture accounts
# ---------------------------------------------------------------------------


def test_account_ledger_expected_accounts_match_fixture_accounts():
    data  = _load()
    lines = _alpha_net_lines(data)
    dr, cr = _account_totals(lines)

    calc_1010_dr  = dr["1010"]
    calc_1010_cr  = cr["1010"]
    calc_1010_net = calc_1010_dr - calc_1010_cr

    calc_1200_dr  = dr["1200"]
    calc_1200_cr  = cr["1200"]
    calc_1200_net = calc_1200_dr - calc_1200_cr

    assert calc_1010_dr  == _d("11180"), f"1010 total_dr: {calc_1010_dr}"
    assert calc_1010_cr  == _d("6705"),  f"1010 total_cr: {calc_1010_cr}"
    assert calc_1010_net == _d("4475"),  f"1010 net: {calc_1010_net}"

    assert calc_1200_dr  == _d("2680"),  f"1200 total_dr: {calc_1200_dr}"
    assert calc_1200_cr  == _d("1380"),  f"1200 total_cr: {calc_1200_cr}"
    assert calc_1200_net == _d("1300"),  f"1200 net: {calc_1200_net}"

    al = data["expected_reports"]["tenant_alpha"]["account_ledger"]
    assert _d(al["1010_bank"]["total_dr"])       == _d("11180"), "Fixture 1010 total_dr mismatch"
    assert _d(al["1010_bank"]["total_cr"])       == _d("6705"),  "Fixture 1010 total_cr mismatch"
    assert _d(al["1010_bank"]["net_balance_dr"]) == _d("4475"),  "Fixture 1010 net_balance_dr mismatch"
    assert _d(al["1200_ar"]["total_dr"])         == _d("2680"),  "Fixture 1200 total_dr mismatch"
    assert _d(al["1200_ar"]["total_cr"])         == _d("1380"),  "Fixture 1200 total_cr mismatch"
    assert _d(al["1200_ar"]["net_balance_dr"])   == _d("1300"),  "Fixture 1200 net_balance_dr mismatch"


# ---------------------------------------------------------------------------
# Test 16: counterparty ledger expected counterparties match fixture
# ---------------------------------------------------------------------------


def test_counterparty_ledger_expected_counterparties_match_fixture():
    data    = _load()
    headers = data["journal_entry_headers"]
    net_ids = _alpha_net_ids(data)
    net_h   = [h for h in headers if h["id"] in net_ids]

    def _cp_headers(cp_id, source_types):
        return [
            h for h in net_h
            if h.get("metadata_json", {}).get("counterparty_id") == cp_id
            and h.get("source_type") in source_types
        ]

    customer_invoiced = sum(_d(h["total_debit"]) for h in _cp_headers("synthetic_customer_alpha", {"invoice"}))
    customer_received = sum(_d(h["total_debit"]) for h in _cp_headers("synthetic_customer_alpha", {"bank_receipt"}))
    supplier_purchased = sum(_d(h["total_debit"]) for h in _cp_headers("synthetic_supplier_alpha", {"purchase_invoice"}))
    supplier_paid      = sum(_d(h["total_debit"]) for h in _cp_headers("synthetic_supplier_alpha", {"bank_payment"}))

    assert customer_invoiced  == _d("1680"), f"Customer invoiced: {customer_invoiced}"
    assert customer_received  == _d("1180"), f"Customer received: {customer_received}"
    assert supplier_purchased == _d("1180"), f"Supplier purchased: {supplier_purchased}"
    assert supplier_paid      == _d("1180"), f"Supplier paid: {supplier_paid}"

    cl = data["expected_reports"]["tenant_alpha"]["counterparty_ledger"]
    assert _d(cl["synthetic_customer_alpha"]["total_invoiced"])  == _d("1680"), "Fixture customer invoiced mismatch"
    assert _d(cl["synthetic_customer_alpha"]["total_received"])  == _d("1180"), "Fixture customer received mismatch"
    assert _d(cl["synthetic_customer_alpha"]["net_outstanding"]) == _d("500"),  "Fixture customer net outstanding mismatch"
    assert _d(cl["synthetic_supplier_alpha"]["total_purchased"]) == _d("1180"), "Fixture supplier purchased mismatch"
    assert _d(cl["synthetic_supplier_alpha"]["total_paid"])      == _d("1180"), "Fixture supplier paid mismatch"
    assert _d(cl["synthetic_supplier_alpha"]["net_outstanding"]) == _d("0"),    "Fixture supplier net outstanding mismatch"


# ---------------------------------------------------------------------------
# Test 17: payroll ledger matches payroll-related entries
# ---------------------------------------------------------------------------


def test_payroll_ledger_matches_payroll_related_entries():
    data  = _load()
    net_ids = _alpha_net_ids(data)
    payroll_headers = [
        h for h in data["journal_entry_headers"]
        if h["id"] in net_ids and h.get("source_type") == "payroll"
    ]
    assert len(payroll_headers) >= 1, "No payroll headers in standard net"
    payroll_ids = {h["id"] for h in payroll_headers}
    payroll_lines = [l for l in data["journal_entry_lines"] if l["journal_entry_id"] in payroll_ids]

    gross_salary = sum(_d(l["debit"]) for l in payroll_lines if l["account_code"] == "5200")
    net_payable  = sum(_d(l["credit"]) for l in payroll_lines if l["account_code"] == "2300")
    income_tax   = sum(_d(l["credit"]) for l in payroll_lines if l["account_code"] == "2310")

    assert gross_salary == _d("2000"), f"Gross salary: {gross_salary}"
    assert net_payable  == _d("1600"), f"Net payable: {net_payable}"
    assert income_tax   == _d("400"),  f"Income tax: {income_tax}"

    pl = data["expected_reports"]["tenant_alpha"]["payroll_ledger"]
    assert _d(pl["gross_salary_expense"]) == _d("2000"), "Fixture gross_salary_expense mismatch"
    assert _d(pl["net_salary_payable"])   == _d("1600"), "Fixture net_salary_payable mismatch"
    assert _d(pl["income_tax_payg"])      == _d("400"),  "Fixture income_tax_payg mismatch"


# ---------------------------------------------------------------------------
# Test 18: journal entries list matches standard net headers
# ---------------------------------------------------------------------------


def test_journal_entries_list_matches_standard_net_headers():
    data    = _load()
    net_h   = _alpha_net_headers(data)
    vol_dr  = sum(_d(h["total_debit"]) for h in net_h)
    vol_cr  = sum(_d(h["total_credit"]) for h in net_h)
    assert vol_dr == vol_cr, "Journal entries list volume DR must equal CR"
    assert vol_dr == _d("23945"), f"Journal entries total volume: {vol_dr}"
    jel = data["expected_reports"]["tenant_alpha"]["journal_entries_list"]
    assert jel["standard_net_count"] == len(net_h), "Fixture standard_net_count mismatch"
    assert _d(jel["total_volume_dr"]) == _d("23945"), "Fixture total_volume_dr mismatch"
    assert _d(jel["total_volume_cr"]) == _d("23945"), "Fixture total_volume_cr mismatch"
    assert "posted" in jel["statuses_included"]
    assert "correction" in jel["statuses_included"]
    assert "reversed" in jel["statuses_excluded"]
    assert "voided" in jel["statuses_excluded"]


# ---------------------------------------------------------------------------
# Test 19: cashflow matches cash and bank movements
# ---------------------------------------------------------------------------


def test_cashflow_matches_cash_and_bank_movements():
    data  = _load()
    lines = _alpha_net_lines(data)
    bank_lines = [l for l in lines if l["account_code"] == "1010"]
    inflows  = sum(_d(l["debit"])  for l in bank_lines)
    outflows = sum(_d(l["credit"]) for l in bank_lines)
    net_cash = inflows - outflows
    assert inflows  == _d("11180"), f"Cash inflows: {inflows}"
    assert outflows == _d("6705"),  f"Cash outflows: {outflows}"
    assert net_cash == _d("4475"),  f"Net cash: {net_cash}"
    cf = data["expected_reports"]["tenant_alpha"]["cashflow"]
    assert _d(cf["inflows"])                   == _d("11180"), "Fixture cashflow.inflows mismatch"
    assert _d(cf["outflows"])                  == _d("6705"),  "Fixture cashflow.outflows mismatch"
    assert _d(cf["net_cash_movement"])         == _d("4475"),  "Fixture cashflow.net_cash_movement mismatch"
    assert _d(cf["closing_balance_bank_1010"]) == _d("4475"),  "Fixture cashflow.closing_balance mismatch"


# ---------------------------------------------------------------------------
# Test 20: correction links have expected report impact
# ---------------------------------------------------------------------------


def test_correction_links_have_expected_report_impact():
    data    = _load()
    net_ids = _alpha_net_ids(data)
    corrections = [
        h for h in data["journal_entry_headers"]
        if h["status"] == "correction" and h["tenant_id"] == "tenant_alpha"
    ]
    assert len(corrections) >= 1, "No correction entries in fixture"
    for c in corrections:
        assert c["correction_of_entry_id"] is not None, \
            f"Correction {c['id']} missing correction_of_entry_id"
        assert c["id"] in net_ids, \
            f"Correction {c['id']} must be in standard net"
    # H012 correction: reduces 4100 service revenue by 200
    correction_lines = [
        l for l in data["journal_entry_lines"]
        if l["journal_entry_id"] in {c["id"] for c in corrections}
    ]
    revenue_dr_correction = sum(_d(l["debit"]) for l in correction_lines if l["account_code"] == "4100")
    assert revenue_dr_correction == _d("200"), \
        f"Revenue correction DR impact: {revenue_dr_correction}"


# ---------------------------------------------------------------------------
# Test 21: reversal links are excluded from standard net
# ---------------------------------------------------------------------------


def test_reversal_links_are_excluded_from_standard_net():
    data    = _load()
    net_ids = _alpha_net_ids(data)
    reversals = [
        h for h in data["journal_entry_headers"]
        if h["status"] == "reversed" and h["tenant_id"] == "tenant_alpha"
    ]
    assert len(reversals) >= 1, "No reversed entries in fixture"
    for r in reversals:
        assert r["id"] not in net_ids, \
            f"Reversed entry {r['id']} must NOT be in standard net"
    # H013 lines must not contribute to net totals
    reversal_ids = {r["id"] for r in reversals}
    reversal_lines = [l for l in data["journal_entry_lines"] if l["journal_entry_id"] in reversal_ids]
    net_lines = _alpha_net_lines(data)
    net_line_ids = {l["id"] for l in net_lines}
    for l in reversal_lines:
        assert l["id"] not in net_line_ids, \
            f"Reversal line {l['id']} must not appear in standard net lines"


# ---------------------------------------------------------------------------
# Test 22: evidence/posting/source links present in report drilldowns
# ---------------------------------------------------------------------------


def test_evidence_posting_source_links_present_in_report_drilldowns():
    data    = _load()
    net_ids = _alpha_net_ids(data)
    net_h   = [h for h in data["journal_entry_headers"] if h["id"] in net_ids]
    sources = data["journal_entry_sources"]

    # At least some headers have evidence_bundle_id
    evidence_headers = [h for h in net_h if h.get("evidence_bundle_id")]
    assert len(evidence_headers) >= 1, "At least one standard-net header must have evidence_bundle_id"

    # All standard net headers (except reversal source_draft) have posting_log_id
    posting_log_headers = [h for h in net_h if h.get("posting_log_id")]
    assert len(posting_log_headers) >= len(net_h) - 1, \
        "Most standard-net headers must have posting_log_id"

    # Sources table references standard-net headers
    source_entry_ids = {s["journal_entry_id"] for s in sources}
    assert source_entry_ids <= (net_ids | {h["id"] for h in data["journal_entry_headers"]}), \
        "Sources must reference known journal entry IDs"
    assert len([s for s in sources if s["journal_entry_id"] in net_ids]) >= 1, \
        "At least one source must link to a standard-net entry"


# ---------------------------------------------------------------------------
# Test 23: invalid rows are not included in expected reports
# ---------------------------------------------------------------------------


def test_invalid_rows_are_not_included_in_expected_reports():
    data      = _load()
    net_ids   = _alpha_net_ids(data)
    invalid   = data["invalid_rows"]
    invalid_ids = {r["id"] for r in invalid}
    assert not (invalid_ids & net_ids), "Invalid row IDs must not be in standard net headers"
    # invalid_rows contain forbidden statuses or structural violations (e.g. unbalanced posted entry)
    invalid_statuses_found = {r["status"] for r in invalid if "status" in r}
    expected_invalid_statuses = {"draft", "approved", "auto_approved", "posted"}
    assert invalid_statuses_found <= expected_invalid_statuses, \
        f"Unexpected statuses in invalid_rows: {invalid_statuses_found - expected_invalid_statuses}"
    # The unbalanced entry (status=posted) is excluded by ID, not by status
    unbalanced = [r for r in invalid if r.get("status") == "posted"]
    for r in unbalanced:
        assert r["id"] not in net_ids, "Unbalanced posted invalid_row ID must not be in standard net"
    # Verify invalid_rows count
    assert len(invalid) == 4, f"Expected 4 invalid rows, got {len(invalid)}"


# ---------------------------------------------------------------------------
# Test 24: no real PII or tax or bank patterns
# ---------------------------------------------------------------------------


def test_no_real_pii_or_tax_or_bank_patterns():
    text = _FIXTURE.read_text(encoding="utf-8")
    # Georgian personal ID: 11 consecutive digits
    assert not re.search(r"\b\d{11}\b", text), "11-digit pattern found — potential Georgian personal ID"
    # Georgian company ID: exactly 9 digits
    assert not re.search(r"\b\d{9}\b", text), "9-digit pattern found — potential Georgian company ID"
    # IBAN pattern starting with GE
    assert not re.search(r"\bGE\d{2}[A-Z0-9]{16,}\b", text), "GE IBAN pattern found"
    # Real email addresses
    assert not re.search(r"\b[A-Za-z0-9._%+-]+@(gmail|yahoo|hotmail|outlook)\.(com|ge)\b", text), \
        "Real email address pattern found"
    # Real bank names
    for name in ["TBC Bank", "Bank of Georgia", "BOG", "სახალხო ბანკი"]:
        assert name not in text, f"Real bank name {name!r} found"
    # Real LLC/Ltd patterns
    assert not re.search(r"\b(LLC|Ltd\.|Inc\.|GmbH|შპს|სს)\b", text), "Real entity suffix found"


# ---------------------------------------------------------------------------
# Test 25: no DB or network imports in test file
# ---------------------------------------------------------------------------


def test_no_db_or_network_imports_in_test_file():
    source = _THIS.read_text(encoding="utf-8")
    tree   = ast.parse(source)
    forbidden = {"asyncpg", "psycopg2", "sqlalchemy", "httpx", "requests", "aiohttp", "socket"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden, f"Forbidden import: {alias.name!r}"
        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            assert root not in forbidden, f"Forbidden import-from: {node.module!r}"


# ---------------------------------------------------------------------------
# Test 26: no SQL or subprocess in test file
# ---------------------------------------------------------------------------


def test_no_sql_or_subprocess_in_test_file():
    source = _THIS.read_text(encoding="utf-8")
    tree   = ast.parse(source)
    forbidden_calls = {"system", "popen", "Popen", "check_call", "check_output", "run"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fname = ""
            if isinstance(node.func, ast.Attribute):
                fname = node.func.attr
            elif isinstance(node.func, ast.Name):
                fname = node.func.id
            if fname in forbidden_calls:
                parent = getattr(node.func, "value", None)
                parent_name = getattr(parent, "id", "") if parent else ""
                if parent_name in ("subprocess", "os"):
                    raise AssertionError(f"Forbidden subprocess/os call: {fname!r}")
    # SQL keyword fragments (split to avoid self-triggering)
    sql_keywords = [
        "INSERT" + " INTO",
        "UPDATE" + " ",
        "DELETE" + " FROM",
        "CREATE" + " TABLE",
        "ALTER" + " TABLE",
        "DROP" + " TABLE",
    ]
    for kw in sql_keywords:
        assert kw not in source, f"SQL keyword {kw!r} found in test file"


# ---------------------------------------------------------------------------
# Test 27: next task H27 documented
# ---------------------------------------------------------------------------


def test_next_task_h27_documented():
    text = _doc_text().lower()
    assert "h27" in text, "Next task H27 must be referenced in H26 doc"
    assert "next task" in text or "next safe task" in text, "Next task section must be present"
