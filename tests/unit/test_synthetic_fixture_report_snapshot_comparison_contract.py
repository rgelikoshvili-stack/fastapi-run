"""
11C-H27 — Synthetic Fixture Report Snapshot Comparison Contract Tests

Validates that the H25/H26 synthetic fixture expected_reports provide a
complete, shape-correct, link-preserving snapshot base for future old-vs-new
report comparison. No DB, no network, no subprocess, no SQL, no migrations.
All assertions are read-only local fixture and document scans.
"""

import ast
import json
import pathlib
import re
from decimal import Decimal

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ROOT    = pathlib.Path(__file__).parents[2]
_DOC     = _ROOT / "docs" / "synthetic-fixture-report-snapshot-comparison-plan.md"
_FIXTURE = _ROOT / "tests" / "fixtures" / "posted_ledger" / "synthetic_posted_ledger_fixture_pack.json"
_THIS    = pathlib.Path(__file__)

ALL_11_REPORTS = [
    "trial_balance",
    "pl_summary",
    "pl_detail",
    "balance_sheet_summary",
    "balance_sheet_detail",
    "vat_register",
    "account_ledger",
    "counterparty_ledger",
    "payroll_ledger",
    "journal_entries_list",
    "cashflow",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load():
    assert _FIXTURE.exists(), f"Fixture missing: {_FIXTURE}"
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _doc_text():
    assert _DOC.exists(), f"H27 doc missing: {_DOC}"
    return _DOC.read_text(encoding="utf-8")


def _alpha(data):
    return data["expected_reports"]["tenant_alpha"]


def _d(v):
    return Decimal(str(v))


# ---------------------------------------------------------------------------
# Test 1: doc exists
# ---------------------------------------------------------------------------


def test_h27_doc_exists():
    assert _DOC.exists(), f"Missing: {_DOC}"
    assert _DOC.stat().st_size > 0, "H27 doc is empty"


# ---------------------------------------------------------------------------
# Test 2: non-action statement present
# ---------------------------------------------------------------------------


def test_h27_non_action_statement_present():
    raw  = _doc_text()
    text = raw.lower().replace("**", "").replace("*", "")
    assert "does not create" in text,         "H27 must state it does not create a DB"
    assert "does not connect" in text,        "H27 must state it does not connect to a DB"
    assert "does not execute sql" in text,    "H27 must state it does not execute SQL"
    assert "does not run migrations" in text, "H27 must state it does not run migrations"
    assert "does not load" in text,           "H27 must state it does not load fixtures"
    assert "does not call runtime" in text or "does not call live" in text or "does not call report" in text, \
        "H27 must state it does not call runtime/live report APIs"
    assert "does not modify runtime" in text, "H27 must state it does not modify runtime behavior"
    assert "does not enable" in text,         "H27 must state it does not enable feature flags"
    assert "does not activate" in text,       "H27 must state it does not activate Balance.ge"


# ---------------------------------------------------------------------------
# Test 3: all 11 reports in comparison scope
# ---------------------------------------------------------------------------


def test_all_11_reports_in_comparison_scope():
    text = _doc_text().lower()
    # Map fixture keys to how they appear in the doc (lowercase)
    report_doc_names = {
        "trial_balance":         "trial balance",
        "pl_summary":            "p&l summary",
        "pl_detail":             "p&l detail",
        "balance_sheet_summary": "balance sheet summary",
        "balance_sheet_detail":  "balance sheet detail",
        "vat_register":          "vat register",
        "account_ledger":        "account ledger",
        "counterparty_ledger":   "counterparty ledger",
        "payroll_ledger":        "payroll ledger",
        "journal_entries_list":  "journal entries list",
        "cashflow":              "cashflow",
    }
    for report, doc_name in report_doc_names.items():
        assert doc_name in text, f"Report '{doc_name}' must be in H27 comparison scope doc"


# ---------------------------------------------------------------------------
# Test 4: snapshot shape requirements documented
# ---------------------------------------------------------------------------


def test_snapshot_shape_requirements_documented():
    text = _doc_text().lower()
    required_terms = [
        "report_name",
        "tenant",
        "period",
        "currency",
        "totals",
        "stable row keys",
        "status policy",
        "drilldown",
        "comparison tolerance",
    ]
    for term in required_terms:
        assert term in text, f"Snapshot shape requirement '{term}' not documented"


# ---------------------------------------------------------------------------
# Test 5: stable identity keys documented
# ---------------------------------------------------------------------------


def test_stable_identity_keys_documented():
    text = _doc_text().lower()
    required_keys = [
        "account_code",
        "counterparty_id",
        "journal_entry_id",
        "source_draft_id",
        "posting_log_id",
        "evidence_bundle_id",
        "correction_of_id",
        "tenant_id",
        "period",
    ]
    for key in required_keys:
        assert key in text, f"Stable identity key '{key}' not documented"


# ---------------------------------------------------------------------------
# Test 6: comparison rules documented
# ---------------------------------------------------------------------------


def test_comparison_rules_documented():
    text = _doc_text().lower()
    assert "decimal" in text,          "Comparison rules must mention Decimal arithmetic"
    assert "currency" in text,         "Comparison rules must mention currency matching"
    assert "row count" in text,        "Comparison rules must mention row count matching"
    assert "rounding tolerance" in text or "tolerance" in text, \
        "Comparison rules must mention rounding tolerance"
    assert "tenant" in text,           "Comparison rules must mention tenant isolation"
    assert "status policy" in text,    "Comparison rules must mention status policy"


# ---------------------------------------------------------------------------
# Test 7: mismatch classification documented
# ---------------------------------------------------------------------------


def test_mismatch_classification_documented():
    text = _doc_text()
    required_codes = [
        "SNAPSHOT_SHAPE_MISMATCH",
        "REPORT_TOTAL_MISMATCH",
        "ROW_COUNT_MISMATCH",
        "ROW_VALUE_MISMATCH",
        "ROUNDING_ONLY_DIFFERENCE",
        "TENANT_LEAKAGE",
        "STATUS_POLICY_MISMATCH",
        "CORRECTION_REVERSAL_MISMATCH",
        "DRILLDOWN_LINK_MISSING",
        "EVIDENCE_LINK_MISSING",
        "CASHFLOW_CLASSIFICATION_MISMATCH",
        "VAT_CLASSIFICATION_MISMATCH",
        "PAYROLL_CLASSIFICATION_MISMATCH",
    ]
    for code in required_codes:
        assert code in text, f"Mismatch classification code '{code}' not documented"


# ---------------------------------------------------------------------------
# Test 8: standard net status policy documented
# ---------------------------------------------------------------------------


def test_standard_net_status_policy_documented():
    text = _doc_text().lower()
    assert "posted" in text,     "Status 'posted' must be documented"
    assert "correction" in text, "Status 'correction' must be documented"
    assert "reversed" in text,   "Status 'reversed' exclusion must be documented"
    assert "voided" in text,     "Status 'voided' exclusion must be documented"
    assert "draft" in text,      "Status 'draft' forbidden note must be documented"
    assert "standard net" in text, "Standard net concept must be documented"


# ---------------------------------------------------------------------------
# Test 9: report-by-report criteria documented for all 11 reports
# ---------------------------------------------------------------------------


def test_report_by_report_criteria_documented_for_all_11_reports():
    text = _doc_text().lower()
    criteria_sections = [
        "trial balance",
        "p&l summary",
        "p&l detail",
        "balance sheet summary",
        "balance sheet detail",
        "vat register",
        "account ledger",
        "counterparty ledger",
        "payroll ledger",
        "journal entries list",
        "cashflow",
    ]
    for section in criteria_sections:
        assert section in text, f"Report-by-report criteria missing for: '{section}'"


# ---------------------------------------------------------------------------
# Test 10: future old-vs-new runtime comparison plan documented
# ---------------------------------------------------------------------------


def test_future_old_vs_new_runtime_comparison_plan_documented():
    text = _doc_text().lower()
    assert "old" in text and "new" in text, "Old-vs-new comparison plan must be present"
    assert "normalize" in text or "normaliz" in text, "Normalization step must be documented"
    assert "classify" in text or "classif" in text,   "Mismatch classification step must be documented"
    assert "feature flag" in text,         "Feature flag step must be documented in plan"
    assert "non-production" in text or "disposable" in text, \
        "Plan must restrict to non-production/disposable environment"
    assert "accountant" in text,           "Accountant review step must be documented"


# ---------------------------------------------------------------------------
# Test 11: approval gates documented
# ---------------------------------------------------------------------------


def test_approval_gates_documented():
    text = _doc_text()
    required_gates = ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10"]
    for gate in required_gates:
        assert gate in text, f"Approval gate '{gate}' not documented"
    text_lower = text.lower()
    assert "rollback" in text_lower,       "Rollback plan gate must be documented"
    assert "production" in text_lower,     "Production approval gate must be documented"
    assert "monitoring" in text_lower,     "Post-switch monitoring gate must be documented"


# ---------------------------------------------------------------------------
# Test 12: safety rules documented
# ---------------------------------------------------------------------------


def test_safety_rules_documented():
    text = _doc_text().lower()
    assert "no production data" in text,   "Safety rule: no production data"
    assert "no db" in text or "no database" in text or "no db is created" in text or \
        "no db is connected" in text or "does not create a db" in text, \
        "Safety rule: no DB"
    assert "no runtime" in text or "does not call runtime" in text, \
        "Safety rule: no runtime endpoint calls"
    assert "feature flag" in text,         "Safety rule: feature flag stays off"
    assert "balance.ge" in text,           "Safety rule: Balance.ge not activated"
    assert "no connector" in text or "no connector changes" in text, \
        "Safety rule: no connector changes"
    assert "no infrastructure" in text or "no infrastructure changes" in text, \
        "Safety rule: no infrastructure changes"
    assert "no credentials" in text or "no credentials changed" in text, \
        "Safety rule: no credentials"


# ---------------------------------------------------------------------------
# Test 13: fixture expected_reports has all 11 snapshots
# ---------------------------------------------------------------------------


def test_fixture_expected_reports_have_all_11_snapshots():
    data  = _load()
    alpha = _alpha(data)
    for report in ALL_11_REPORTS:
        assert report in alpha, f"expected_reports.tenant_alpha missing: {report}"


# ---------------------------------------------------------------------------
# Test 14: each expected report has comparable shape
# ---------------------------------------------------------------------------


def test_each_expected_report_has_comparable_shape():
    data  = _load()
    alpha = _alpha(data)

    # Minimum required fields per report type
    shape_requirements = {
        "trial_balance":          ["total_dr", "total_cr", "accounts"],
        "pl_summary":             ["total_income", "total_expense", "net_profit_loss"],
        "pl_detail":              ["income", "expense", "net_profit_loss"],
        "balance_sheet_summary":  ["total_assets", "total_liabilities", "total_equity"],
        "balance_sheet_detail":   ["assets", "liabilities", "equity"],
        "vat_register":           ["vat_input_reclaimable", "vat_output_payable", "net_vat_position"],
        "account_ledger":         [],  # checked by content in test 19
        "counterparty_ledger":    [],  # checked by content in test 19
        "payroll_ledger":         ["gross_salary_expense", "net_salary_payable", "income_tax_payg"],
        "journal_entries_list":   ["standard_net_count", "total_volume_dr", "total_volume_cr"],
        "cashflow":               ["inflows", "outflows", "net_cash_movement"],
    }
    for report, fields in shape_requirements.items():
        snapshot = alpha[report]
        assert isinstance(snapshot, dict), f"{report} snapshot must be a dict"
        for field in fields:
            assert field in snapshot, f"{report} snapshot missing required field: {field}"


# ---------------------------------------------------------------------------
# Test 15: trial balance snapshot has totals and rows
# ---------------------------------------------------------------------------


def test_trial_balance_snapshot_has_totals_and_rows():
    data = _load()
    tb   = _alpha(data)["trial_balance"]
    assert "total_dr" in tb, "trial_balance missing total_dr"
    assert "total_cr" in tb, "trial_balance missing total_cr"
    assert "accounts" in tb, "trial_balance missing accounts dict"
    assert isinstance(tb["accounts"], dict), "trial_balance.accounts must be a dict"
    assert len(tb["accounts"]) >= 10, "trial_balance must have at least 10 account rows"
    assert _d(tb["total_dr"]) == _d(tb["total_cr"]), \
        f"trial_balance total_dr != total_cr: {tb['total_dr']} vs {tb['total_cr']}"
    # Each account row must have a net_dr or net_cr key
    for acct_key, row in tb["accounts"].items():
        has_net = "net_dr" in row or "net_cr" in row
        assert has_net, f"trial_balance account {acct_key} missing net_dr or net_cr"


# ---------------------------------------------------------------------------
# Test 16: P&L snapshots have summary and detail
# ---------------------------------------------------------------------------


def test_pl_snapshots_have_summary_and_detail():
    data    = _load()
    alpha   = _alpha(data)
    summary = alpha["pl_summary"]
    detail  = alpha["pl_detail"]

    assert _d(summary["total_income"])  > _d("0"),   "pl_summary total_income must be > 0"
    assert _d(summary["total_expense"]) > _d("0"),   "pl_summary total_expense must be > 0"
    net = _d(summary["total_income"]) - _d(summary["total_expense"])
    assert _d(summary["net_profit_loss"]) == net, \
        f"pl_summary net_profit_loss={summary['net_profit_loss']} but income-expense={net}"

    assert "income" in detail,  "pl_detail missing income breakdown"
    assert "expense" in detail, "pl_detail missing expense breakdown"
    assert isinstance(detail["income"],  dict), "pl_detail.income must be a dict"
    assert isinstance(detail["expense"], dict), "pl_detail.expense must be a dict"

    detail_income  = sum(_d(v) for v in detail["income"].values())
    detail_expense = sum(_d(v) for v in detail["expense"].values())
    assert detail_income  == _d(summary["total_income"]),  "pl_detail income sum != pl_summary total_income"
    assert detail_expense == _d(summary["total_expense"]), "pl_detail expense sum != pl_summary total_expense"


# ---------------------------------------------------------------------------
# Test 17: balance sheet snapshots have summary and detail
# ---------------------------------------------------------------------------


def test_balance_sheet_snapshots_have_summary_and_detail():
    data    = _load()
    alpha   = _alpha(data)
    summary = alpha["balance_sheet_summary"]
    detail  = alpha["balance_sheet_detail"]

    ta = _d(summary["total_assets"])
    tl = _d(summary["total_liabilities"])
    te = _d(summary["total_equity"])
    assert ta == tl + te, f"Balance sheet equation violated: {ta} != {tl} + {te}"

    for section in ("assets", "liabilities", "equity"):
        assert section in detail, f"balance_sheet_detail missing section: {section}"
        assert "total" in detail[section], f"balance_sheet_detail.{section} missing total"

    assert _d(detail["assets"]["total"])      == ta, "BS detail assets total != summary total_assets"
    assert _d(detail["liabilities"]["total"]) == tl, "BS detail liabilities total != summary total_liabilities"
    assert _d(detail["equity"]["total"])      == te, "BS detail equity total != summary total_equity"


# ---------------------------------------------------------------------------
# Test 18: VAT register snapshot has input/output/net
# ---------------------------------------------------------------------------


def test_vat_register_snapshot_has_input_output_net():
    data = _load()
    vr   = _alpha(data)["vat_register"]
    assert "vat_input_reclaimable" in vr,  "vat_register missing vat_input_reclaimable"
    assert "vat_output_payable"    in vr,  "vat_register missing vat_output_payable"
    assert "net_vat_position"      in vr,  "vat_register missing net_vat_position"
    assert "period"                in vr,  "vat_register missing period"
    net = _d(vr["vat_output_payable"]) - _d(vr["vat_input_reclaimable"])
    assert _d(vr["net_vat_position"]) == net, \
        f"vat net_vat_position={vr['net_vat_position']} but output-input={net}"


# ---------------------------------------------------------------------------
# Test 19: ledger snapshots have stable keys
# ---------------------------------------------------------------------------


def test_ledger_snapshots_have_stable_keys():
    data  = _load()
    alpha = _alpha(data)

    # account_ledger: keys must start with a 4-digit account code
    al = alpha["account_ledger"]
    assert isinstance(al, dict), "account_ledger must be a dict"
    assert len(al) >= 2, "account_ledger must have at least 2 entries"
    for key, row in al.items():
        assert re.match(r"^\d{4}", key), f"account_ledger key '{key}' must start with 4-digit account code"
        assert "total_dr"       in row, f"account_ledger[{key}] missing total_dr"
        assert "total_cr"       in row, f"account_ledger[{key}] missing total_cr"
        assert "net_balance_dr" in row, f"account_ledger[{key}] missing net_balance_dr"

    # counterparty_ledger: keys must be counterparty IDs
    cl = alpha["counterparty_ledger"]
    assert isinstance(cl, dict), "counterparty_ledger must be a dict"
    assert len(cl) >= 1, "counterparty_ledger must have at least 1 counterparty"
    fixture_cp_ids = {cp["id"] for cp in data["counterparties"]}
    for cp_id in cl.keys():
        assert cp_id in fixture_cp_ids, \
            f"counterparty_ledger key '{cp_id}' not in fixture counterparties"

    # payroll_ledger: must have period field as stable key
    pl = alpha["payroll_ledger"]
    assert "period" in pl, "payroll_ledger missing period stable key"


# ---------------------------------------------------------------------------
# Test 20: journal entries snapshot has entry IDs and status policy
# ---------------------------------------------------------------------------


def test_journal_entries_snapshot_has_entry_ids_and_status_policy():
    data = _load()
    jel  = _alpha(data)["journal_entries_list"]
    assert "standard_net_count"  in jel, "journal_entries_list missing standard_net_count"
    assert "total_volume_dr"     in jel, "journal_entries_list missing total_volume_dr"
    assert "total_volume_cr"     in jel, "journal_entries_list missing total_volume_cr"
    assert "statuses_included"   in jel, "journal_entries_list missing statuses_included"
    assert "statuses_excluded"   in jel, "journal_entries_list missing statuses_excluded"
    assert _d(jel["total_volume_dr"]) == _d(jel["total_volume_cr"]), \
        "journal_entries_list total_volume_dr must equal total_volume_cr"
    assert "posted"    in jel["statuses_included"], "posted must be in statuses_included"
    assert "correction" in jel["statuses_included"], "correction must be in statuses_included"
    assert "reversed"   in jel["statuses_excluded"], "reversed must be in statuses_excluded"
    assert "voided"     in jel["statuses_excluded"], "voided must be in statuses_excluded"
    # standard_net_count must agree with fixture headers
    net_headers = [
        h for h in data["journal_entry_headers"]
        if h["tenant_id"] == "tenant_alpha" and h["status"] in {"posted", "correction"}
    ]
    assert jel["standard_net_count"] == len(net_headers), \
        f"standard_net_count={jel['standard_net_count']} but fixture has {len(net_headers)} standard-net headers"


# ---------------------------------------------------------------------------
# Test 21: cashflow snapshot has inflows/outflows/net
# ---------------------------------------------------------------------------


def test_cashflow_snapshot_has_inflows_outflows_net():
    data = _load()
    cf   = _alpha(data)["cashflow"]
    assert "inflows"                   in cf, "cashflow missing inflows"
    assert "outflows"                  in cf, "cashflow missing outflows"
    assert "net_cash_movement"         in cf, "cashflow missing net_cash_movement"
    assert "closing_balance_bank_1010" in cf, "cashflow missing closing_balance_bank_1010"
    net = _d(cf["inflows"]) - _d(cf["outflows"])
    assert _d(cf["net_cash_movement"]) == net, \
        f"cashflow net_cash_movement={cf['net_cash_movement']} but inflows-outflows={net}"
    assert _d(cf["closing_balance_bank_1010"]) == net, \
        "cashflow closing_balance must equal net_cash_movement (opening=0)"


# ---------------------------------------------------------------------------
# Test 22: snapshot contract preserves evidence links
# ---------------------------------------------------------------------------


def test_snapshot_contract_preserves_evidence_links():
    data    = _load()
    headers = data["journal_entry_headers"]
    # At least some standard-net alpha headers must have evidence_bundle_id
    evidence_headers = [
        h for h in headers
        if h["tenant_id"] == "tenant_alpha"
        and h["status"] in {"posted", "correction"}
        and h.get("evidence_bundle_id")
    ]
    assert len(evidence_headers) >= 1, \
        "At least one standard-net header must have evidence_bundle_id for snapshot drilldown"
    # At least some standard-net alpha headers must have posting_log_id
    posting_log_headers = [
        h for h in headers
        if h["tenant_id"] == "tenant_alpha"
        and h["status"] in {"posted", "correction"}
        and h.get("posting_log_id")
    ]
    assert len(posting_log_headers) >= 10, \
        "Most standard-net headers must have posting_log_id for audit drilldown"
    # Sources table provides source_draft_id linkage
    sources = data["journal_entry_sources"]
    assert len(sources) >= 1, "Sources table must be non-empty for snapshot drilldown"
    alpha_net_ids = {
        h["id"] for h in headers
        if h["tenant_id"] == "tenant_alpha" and h["status"] in {"posted", "correction"}
    }
    linked_sources = [s for s in sources if s["journal_entry_id"] in alpha_net_ids]
    assert len(linked_sources) >= 1, "At least one source must link to a standard-net alpha header"


# ---------------------------------------------------------------------------
# Test 23: snapshot contract preserves correction/reversal policy
# ---------------------------------------------------------------------------


def test_snapshot_contract_preserves_correction_reversal_policy():
    data    = _load()
    headers = data["journal_entry_headers"]

    corrections = [h for h in headers if h["status"] == "correction" and h["tenant_id"] == "tenant_alpha"]
    assert len(corrections) >= 1, "At least one correction entry must be in fixture"
    for c in corrections:
        assert c["correction_of_entry_id"] is not None, \
            f"Correction {c['id']} missing correction_of_entry_id"

    reversals = [h for h in headers if h["status"] == "reversed" and h["tenant_id"] == "tenant_alpha"]
    assert len(reversals) >= 1, "At least one reversed entry must be in fixture"
    for r in reversals:
        # reversed entries carry correction_of_entry_id pointing to the original
        assert r.get("correction_of_entry_id") or r.get("reversed_by_entry_id") or \
            any(h.get("reversed_by_entry_id") == r["id"] for h in headers), \
            f"Reversed entry {r['id']} has no reversal chain link"

    # Reversed entries must NOT be in standard net
    net_ids = {
        h["id"] for h in headers
        if h["tenant_id"] == "tenant_alpha" and h["status"] in {"posted", "correction"}
    }
    for r in reversals:
        assert r["id"] not in net_ids, f"Reversed entry {r['id']} must not be in standard net"

    # Correction entries MUST be in standard net
    for c in corrections:
        assert c["id"] in net_ids, f"Correction entry {c['id']} must be in standard net"


# ---------------------------------------------------------------------------
# Test 24: snapshot contract preserves tenant isolation expectation
# ---------------------------------------------------------------------------


def test_snapshot_contract_preserves_tenant_isolation_expectation():
    data = _load()

    # tenant_beta isolation test documented in expected_reports
    assert "tenant_beta" in data["expected_reports"], \
        "expected_reports must have tenant_beta isolation section"
    beta_section = data["expected_reports"]["tenant_beta"]
    assert "isolation_test" in beta_section or "_note" in beta_section, \
        "tenant_beta section must document isolation test"

    # tenant_beta header has 9999 amount — must not appear in alpha totals
    alpha    = data["expected_reports"]["tenant_alpha"]
    tb_total = _d(alpha["trial_balance"]["total_dr"])
    assert tb_total != _d("9999") and tb_total != _d("9999") * 2, \
        "trial_balance total must not be 9999 — suggests tenant leakage"

    # tenant_beta lines must have tenant_id = tenant_beta
    beta_lines = [l for l in data["journal_entry_lines"] if l["tenant_id"] == "tenant_beta"]
    assert len(beta_lines) >= 1, "tenant_beta must have at least one line"
    for l in beta_lines:
        assert l["tenant_id"] == "tenant_beta", "tenant_beta line has wrong tenant_id"

    # must_not_appear_in_tenant_alpha_reports flag
    if "isolation_test" in beta_section:
        assert beta_section["isolation_test"].get("must_not_appear_in_tenant_alpha_reports") is True, \
            "must_not_appear_in_tenant_alpha_reports must be True"


# ---------------------------------------------------------------------------
# Test 25: no real PII or tax or bank patterns
# ---------------------------------------------------------------------------


def test_no_real_pii_or_tax_or_bank_patterns():
    text = _FIXTURE.read_text(encoding="utf-8")
    assert not re.search(r"\b\d{11}\b", text), "11-digit pattern — potential Georgian personal ID"
    assert not re.search(r"\b\d{9}\b", text),  "9-digit pattern — potential Georgian company ID"
    assert not re.search(r"\bGE\d{2}[A-Z0-9]{16,}\b", text), "GE IBAN pattern found"
    assert not re.search(r"\b[A-Za-z0-9._%+-]+@(gmail|yahoo|hotmail|outlook)\.(com|ge)\b", text), \
        "Real email address pattern found"
    for name in ["TBC Bank", "Bank of Georgia", "BOG", "სახალხო ბანკი"]:
        assert name not in text, f"Real bank name {name!r} found in fixture"
    assert not re.search(r"\b(LLC|Ltd\.|Inc\.|GmbH|შპს|სს)\b", text), "Real entity suffix found"


# ---------------------------------------------------------------------------
# Test 26: no DB or network imports in test file
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
# Test 27: no SQL or subprocess in test file
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
                parent      = getattr(node.func, "value", None)
                parent_name = getattr(parent, "id", "") if parent else ""
                if parent_name in ("subprocess", "os"):
                    raise AssertionError(f"Forbidden subprocess/os call: {fname!r}")
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
# Test 28: next task H28 documented
# ---------------------------------------------------------------------------


def test_next_task_h28_documented():
    text = _doc_text().lower()
    assert "h28" in text, "Next task H28 must be referenced in H27 doc"
    assert "next task" in text or "next safe task" in text, "Next task section must be present"
