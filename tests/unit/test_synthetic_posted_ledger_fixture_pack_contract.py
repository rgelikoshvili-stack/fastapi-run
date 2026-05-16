"""
11C-H25 — Synthetic Posted-Ledger Fixture Pack Contract Tests

Verifies that:
- docs/synthetic-posted-ledger-test-data-pack.md exists with required sections
- tests/fixtures/posted_ledger/synthetic_posted_ledger_fixture_pack.json is valid
- All posted/correction entries are balanced (total_debit == total_credit)
- No line has both debit and credit positive
- Tenant isolation, status coverage, and evidence links are present
- No real PII, tax IDs, or bank account patterns

No DB, no network, no subprocess execution, no SQL, no migrations.
All assertions are read-only local file scans.
"""

import ast
import json
import pathlib
import re

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ROOT = pathlib.Path(__file__).parents[2]
_DOC = _ROOT / "docs" / "synthetic-posted-ledger-test-data-pack.md"
_FIXTURE = _ROOT / "tests" / "fixtures" / "posted_ledger" / "synthetic_posted_ledger_fixture_pack.json"
_THIS_FILE = pathlib.Path(__file__)

_REQUIRED_REPORTS = {
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
}


def _doc_text() -> str:
    assert _DOC.exists(), f"H25 doc missing: {_DOC}"
    return _DOC.read_text(encoding="utf-8")


def _fixture() -> dict:
    assert _FIXTURE.exists(), f"Fixture JSON missing: {_FIXTURE}"
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Test 1: H25 doc exists
# ---------------------------------------------------------------------------


def test_h25_doc_exists():
    assert _DOC.exists(), f"Missing: {_DOC}"
    assert _DOC.stat().st_size > 0, "H25 doc is empty"


# ---------------------------------------------------------------------------
# Test 2: fixture JSON exists and is valid
# ---------------------------------------------------------------------------


def test_fixture_json_exists_and_valid():
    assert _FIXTURE.exists(), f"Missing: {_FIXTURE}"
    assert _FIXTURE.stat().st_size > 0, "Fixture JSON is empty"
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "Fixture JSON root must be an object"


# ---------------------------------------------------------------------------
# Test 3: H25 non-action statement present
# ---------------------------------------------------------------------------


def test_h25_non_action_statement_present():
    raw = _doc_text()
    # Strip markdown bold markers before checking so "does **not** create" matches
    text = raw.lower().replace("**", "").replace("*", "")
    assert "h25 does not" in text or "non-action" in text, (
        "Non-action statement missing from H25 doc"
    )
    assert "does not create" in text or "does not connect" in text, (
        "Non-action statement must document no DB creation/connection"
    )
    assert "does not execute sql" in text or "does not run migrations" in text, (
        "Non-action statement must document no SQL/migrations"
    )
    assert "does not enable" in text or "posted_ledger_reports_enabled" in text, (
        "Non-action statement must document no feature flag enablement"
    )
    assert "does not activate" in text or "balance.ge" in text, (
        "Non-action statement must document no Balance.ge activation"
    )
    assert "h26" in text, "Next task H26 must be referenced"


# ---------------------------------------------------------------------------
# Test 4: fixture has required top-level sections
# ---------------------------------------------------------------------------


def test_fixture_has_required_top_level_sections():
    data = _fixture()
    required = {
        "metadata", "tenants", "accounts", "counterparties", "documents",
        "journal_entry_headers", "journal_entry_lines", "journal_entry_sources",
        "expected_reports", "invalid_rows",
    }
    for section in required:
        assert section in data, f"Fixture missing top-level section: {section!r}"


# ---------------------------------------------------------------------------
# Test 5: fixture has at least two synthetic tenants
# ---------------------------------------------------------------------------


def test_fixture_has_two_synthetic_tenants():
    data = _fixture()
    tenants = data.get("tenants", [])
    assert len(tenants) >= 2, f"Expected at least 2 tenants, found {len(tenants)}"
    tenant_ids = {t["id"] for t in tenants}
    assert "tenant_alpha" in tenant_ids, "tenant_alpha not found in tenants"
    assert "tenant_beta" in tenant_ids, "tenant_beta not found in tenants"


# ---------------------------------------------------------------------------
# Test 6: fixture contains required accounting categories
# ---------------------------------------------------------------------------


def test_fixture_contains_required_accounting_categories():
    data = _fixture()
    categories = set(data.get("metadata", {}).get("fixture_categories", []))
    required = {
        "income", "expense", "asset", "liability", "equity",
        "vat_tax", "payroll", "cash_bank", "counterparty_document",
        "evidence_audit", "corrections_reversals", "forbidden_states", "multi_tenant_negative",
    }
    missing = required - categories
    assert not missing, f"Missing fixture categories: {missing}"


# ---------------------------------------------------------------------------
# Test 7: all posted and correction entries balance
# ---------------------------------------------------------------------------


def test_all_posted_and_correction_entries_balance():
    data = _fixture()
    headers = {h["id"]: h for h in data["journal_entry_headers"]}
    lines = data["journal_entry_lines"]

    # Group lines by journal_entry_id
    from collections import defaultdict
    entry_lines: dict = defaultdict(list)
    for line in lines:
        entry_lines[line["journal_entry_id"]].append(line)

    for hdr_id, hdr in headers.items():
        if hdr["status"] not in ("posted", "correction"):
            continue
        total_dr = round(sum(float(l["debit"]) for l in entry_lines[hdr_id]), 2)
        total_cr = round(sum(float(l["credit"]) for l in entry_lines[hdr_id]), 2)
        hdr_dr = round(float(hdr["total_debit"]), 2)
        hdr_cr = round(float(hdr["total_credit"]), 2)
        assert total_dr == total_cr, (
            f"Entry {hdr_id} ({hdr.get('_comment', '')}) lines dr={total_dr} != cr={total_cr}"
        )
        assert total_dr == hdr_dr, (
            f"Entry {hdr_id} line sum dr={total_dr} != header total_debit={hdr_dr}"
        )
        assert total_cr == hdr_cr, (
            f"Entry {hdr_id} line sum cr={total_cr} != header total_credit={hdr_cr}"
        )


# ---------------------------------------------------------------------------
# Test 8: no line has both debit and credit positive
# ---------------------------------------------------------------------------


def test_no_line_has_both_debit_and_credit():
    data = _fixture()
    for line in data["journal_entry_lines"]:
        dr = float(line["debit"])
        cr = float(line["credit"])
        assert not (dr > 0 and cr > 0), (
            f"Line {line['id']} has both debit={dr} and credit={cr} positive — violates ck_jel_not_both_positive"
        )


# ---------------------------------------------------------------------------
# Test 9: tenant_id present on all headers and lines
# ---------------------------------------------------------------------------


def test_tenant_id_present_on_headers_and_lines():
    data = _fixture()
    for hdr in data["journal_entry_headers"]:
        assert hdr.get("tenant_id"), f"Header {hdr.get('id')} missing tenant_id"
    for line in data["journal_entry_lines"]:
        assert line.get("tenant_id"), f"Line {line.get('id')} missing tenant_id"


# ---------------------------------------------------------------------------
# Test 10: status coverage includes posted, correction, reversed, and forbidden
# ---------------------------------------------------------------------------


def test_status_coverage_includes_posted_correction_reversed_forbidden():
    data = _fixture()
    header_statuses = {h["status"] for h in data["journal_entry_headers"]}
    invalid_statuses = {r["status"] for r in data.get("invalid_rows", [])}
    all_statuses = header_statuses | invalid_statuses

    assert "posted" in header_statuses, "No 'posted' entries found"
    assert "correction" in header_statuses, "No 'correction' entries found"
    assert "reversed" in header_statuses, "No 'reversed' entries found"

    # voided or a forbidden status must be present
    has_voided = "voided" in header_statuses
    has_forbidden = bool({"draft", "approved", "auto_approved", "simulated_success"} & invalid_statuses)
    assert has_voided or has_forbidden, (
        "Fixture must have either voided status in headers or forbidden status in invalid_rows"
    )
    # Check forbidden explicitly in invalid_rows
    assert has_forbidden, (
        f"invalid_rows must contain at least one forbidden status (draft/approved/etc); found: {invalid_statuses}"
    )


# ---------------------------------------------------------------------------
# Test 11: standard net status expectation documented in fixture metadata
# ---------------------------------------------------------------------------


def test_standard_net_status_expectation_documented():
    data = _fixture()
    meta = data.get("metadata", {})
    rule = meta.get("standard_net_filter_rule", "")
    assert rule, "metadata.standard_net_filter_rule must be present"
    assert "posted" in rule, "standard_net_filter_rule must mention 'posted'"
    assert "correction" in rule, "standard_net_filter_rule must mention 'correction'"

    # Also check expected_reports has standard_net_filter
    er = data.get("expected_reports", {}).get("tenant_alpha", {})
    assert er.get("standard_net_filter"), "expected_reports.tenant_alpha.standard_net_filter must be present"
    assert er.get("standard_net_excludes"), "expected_reports.tenant_alpha.standard_net_excludes must be present"
    excludes = er["standard_net_excludes"]
    assert "reversed" in excludes, "standard_net_excludes must list 'reversed'"
    assert "voided" in excludes, "standard_net_excludes must list 'voided'"


# ---------------------------------------------------------------------------
# Test 12: correction and reversal links present in headers
# ---------------------------------------------------------------------------


def test_correction_and_reversal_links_present():
    data = _fixture()
    headers = data["journal_entry_headers"]

    correction_ids = [h["correction_of_entry_id"] for h in headers if h.get("correction_of_entry_id")]
    reversal_ids = [h["reversed_by_entry_id"] for h in headers if h.get("reversed_by_entry_id")]

    assert correction_ids, "No correction_of_entry_id links found in any header"
    assert reversal_ids, "No reversed_by_entry_id links found in any header"

    # The linked IDs must reference existing headers
    header_ids = {h["id"] for h in headers}
    for cid in correction_ids:
        assert cid in header_ids, f"correction_of_entry_id={cid!r} does not reference a known header"
    for rid in reversal_ids:
        assert rid in header_ids, f"reversed_by_entry_id={rid!r} does not reference a known header"


# ---------------------------------------------------------------------------
# Test 13: evidence, posting log, and source draft links present in headers
# ---------------------------------------------------------------------------


def test_evidence_posting_source_links_present():
    data = _fixture()
    headers = data["journal_entry_headers"]

    evidence_ids = [h["evidence_bundle_id"] for h in headers if h.get("evidence_bundle_id")]
    posting_log_ids = [h["posting_log_id"] for h in headers if h.get("posting_log_id")]
    source_draft_ids = [h["source_draft_id"] for h in headers if h.get("source_draft_id")]

    assert evidence_ids, "No evidence_bundle_id found on any header"
    assert posting_log_ids, "No posting_log_id found on any header"
    assert source_draft_ids, "No source_draft_id found on any header"


# ---------------------------------------------------------------------------
# Test 14: multi-tenant negative rows present (tenant_beta)
# ---------------------------------------------------------------------------


def test_multi_tenant_negative_rows_present():
    data = _fixture()
    beta_headers = [h for h in data["journal_entry_headers"] if h.get("tenant_id") == "tenant_beta"]
    beta_lines = [l for l in data["journal_entry_lines"] if l.get("tenant_id") == "tenant_beta"]
    assert beta_headers, "No tenant_beta headers found — multi-tenant negative test rows missing"
    assert beta_lines, "No tenant_beta lines found — multi-tenant negative test rows missing"


# ---------------------------------------------------------------------------
# Test 15: expected_reports includes all 11 required reports
# ---------------------------------------------------------------------------


def test_expected_reports_include_all_11_reports():
    data = _fixture()
    er_alpha = data.get("expected_reports", {}).get("tenant_alpha", {})
    present = set(er_alpha.keys())
    missing = _REQUIRED_REPORTS - present
    assert not missing, f"expected_reports.tenant_alpha missing: {missing}"


# ---------------------------------------------------------------------------
# Test 16: expected report totals are deterministic numbers
# ---------------------------------------------------------------------------


def test_expected_report_totals_are_deterministic_numbers():
    data = _fixture()
    er = data["expected_reports"]["tenant_alpha"]

    tb = er["trial_balance"]
    assert isinstance(tb["total_dr"], (int, float)), "trial_balance.total_dr must be numeric"
    assert isinstance(tb["total_cr"], (int, float)), "trial_balance.total_cr must be numeric"
    assert abs(tb["total_dr"] - tb["total_cr"]) < 0.01, (
        f"Trial balance out of balance: total_dr={tb['total_dr']} total_cr={tb['total_cr']}"
    )
    assert tb["total_dr"] > 0, "trial_balance.total_dr must be > 0"

    pl = er["pl_summary"]
    assert isinstance(pl["total_income"], (int, float)), "pl_summary.total_income must be numeric"
    assert isinstance(pl["total_expense"], (int, float)), "pl_summary.total_expense must be numeric"
    assert isinstance(pl["net_profit_loss"], (int, float)), "pl_summary.net_profit_loss must be numeric"
    assert abs(pl["net_profit_loss"] - (pl["total_income"] - pl["total_expense"])) < 0.01, (
        "net_profit_loss must equal total_income - total_expense"
    )

    bs = er["balance_sheet_summary"]
    assert isinstance(bs["total_assets"], (int, float)), "balance_sheet total_assets must be numeric"
    assert isinstance(bs["total_liabilities"], (int, float)), "balance_sheet total_liabilities must be numeric"
    assert isinstance(bs["total_equity"], (int, float)), "balance_sheet total_equity must be numeric"
    assert abs(bs["total_assets"] - (bs["total_liabilities"] + bs["total_equity"])) < 0.01, (
        f"Balance sheet does not balance: assets={bs['total_assets']} liab+eq={bs['total_liabilities']+bs['total_equity']}"
    )

    vat = er["vat_register"]
    assert isinstance(vat["vat_input_reclaimable"], (int, float))
    assert isinstance(vat["vat_output_payable"], (int, float))
    assert isinstance(vat["net_vat_position"], (int, float))


# ---------------------------------------------------------------------------
# Test 17: no real PII, tax IDs, or bank account numbers
# ---------------------------------------------------------------------------


def test_no_real_pii_or_tax_ids_or_bank_accounts():
    fixture_text = _FIXTURE.read_text(encoding="utf-8")

    # No Georgian personal ID pattern (11 consecutive digits, not UUIDs)
    personal_id_match = re.search(r'(?<![0-9a-fA-F-])\d{11}(?![0-9a-fA-F-])', fixture_text)
    assert not personal_id_match, (
        f"Possible Georgian personal ID (11-digit) found in fixture: {personal_id_match.group()!r}"
    )

    # No real Georgian company tax ID (9-digit numeric)
    company_id_match = re.search(r'(?<![0-9a-fA-F-])\d{9}(?![0-9a-fA-F-])', fixture_text)
    assert not company_id_match, (
        f"Possible company tax ID (9-digit) found in fixture: {company_id_match.group()!r}"
    )

    # No real IBAN pattern (GE + 2 digits + 16 digits)
    iban_match = re.search(r'\bGE\d{2}[A-Z0-9]{16,}\b', fixture_text)
    assert not iban_match, (
        f"Possible real IBAN found in fixture: {iban_match.group()!r}"
    )

    # No real email addresses
    email_match = re.search(r'\b[A-Za-z0-9._%+\-]+@(?!example\.com)[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b', fixture_text)
    assert not email_match, (
        f"Possible real email address found in fixture: {email_match.group()!r}"
    )

    # Marker: all tenant IDs should start with tenant_
    fixture_text_lower = fixture_text.lower()
    assert "tenant_alpha" in fixture_text_lower, "tenant_alpha not found in fixture"
    assert "synthetic" in fixture_text_lower, "Synthetic marker missing from fixture"


# ---------------------------------------------------------------------------
# Test 18: no DB or network imports in this test file
# ---------------------------------------------------------------------------


def test_no_db_or_network_imports_in_test_file():
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_top = {
        "asyncpg", "psycopg2", "sqlalchemy", "httpx", "requests",
        "aiohttp", "socket",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden_top, (
                    f"Forbidden import in test file: {alias.name!r}"
                )
        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            assert root not in forbidden_top, (
                f"Forbidden import-from in test file: {node.module!r}"
            )


# ---------------------------------------------------------------------------
# Test 19: no SQL or subprocess execution in this test file
# ---------------------------------------------------------------------------


def test_no_sql_or_subprocess_in_test_file():
    source = _THIS_FILE.read_text(encoding="utf-8")
    # Check no subprocess calls
    tree = ast.parse(source)
    forbidden_calls = {"system", "popen", "Popen", "check_call", "check_output", "run"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                fname = node.func.attr
            elif isinstance(node.func, ast.Name):
                fname = node.func.id
            else:
                fname = ""
            if fname in forbidden_calls:
                parent = getattr(node.func, "value", None)
                parent_name = getattr(parent, "id", "") if parent else ""
                if parent_name in ("subprocess", "os"):
                    raise AssertionError(f"Forbidden subprocess/os call in test file: {fname!r}")
    # No raw SQL strings (stored as fragments to avoid self-match)
    sql_keywords = [
        "INSERT" + " INTO",
        "UPDATE" + " ",
        "DELETE" + " FROM",
        "CREATE" + " TABLE",
        "ALTER" + " TABLE",
        "DROP" + " TABLE",
    ]
    for kw in sql_keywords:
        assert kw not in source, f"Forbidden SQL keyword {kw!r} found in test file"


# ---------------------------------------------------------------------------
# Test 20: next task H26 documented in H25 doc
# ---------------------------------------------------------------------------


def test_next_task_h26_documented():
    text = _doc_text()
    assert "H26" in text, "Next task H26 must be referenced in H25 doc"
    assert "next task" in text.lower() or "next safe task" in text.lower(), (
        "Next task section missing from H25 doc"
    )
