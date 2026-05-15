"""
11C-H19 — Production Report Migration Approval Plan Contract Tests

Verifies documentation completeness and planning contract for the production
migration from journal_drafts to posted-ledger reports.

No DB, no network, no Cloud Run mutation, no SQL, no migrations.
All assertions are documentation and in-memory contract checks only.
"""

import ast
import pathlib
import re

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PLAN_DOC = pathlib.Path(__file__).parents[2] / "docs" / "production-report-migration-approval-plan.md"
_THIS_FILE = pathlib.Path(__file__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_H_CHAIN_TASKS = [f"H{i}" for i in range(1, 19)]

_ALL_OFFICIAL_REPORTS = [
    "Trial Balance",
    "Profit & Loss Summary",
    "Profit & Loss Detail",
    "Balance Sheet Summary",
    "Balance Sheet Detail",
    "VAT Register",
    "Account Ledger",
    "Counterparty Ledger",
    "Payroll Ledger",
    "Journal Entries List",
    "Cashflow",
]

_APPROVAL_GATE_KEYWORDS = [
    "technical readiness",
    "schema readiness",
    "report comparison readiness",
    "business sign-off",
    "privacy review",
    "rollback readiness",
    "production change approval",
    "post-switch monitoring approval",
]

_LEDGER_LINK_FIELDS = [
    "journal_entry_headers",
    "journal_entry_lines",
    "tenant_id",
    "evidence_bundle_id",
    "posting_log_id",
    "source_draft_id",
]

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _doc_text() -> str:
    assert _PLAN_DOC.exists(), f"Plan doc missing: {_PLAN_DOC}"
    return _PLAN_DOC.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests 1–8: document existence and non-action statement
# ---------------------------------------------------------------------------


def test_contract_document_exists():
    assert _PLAN_DOC.exists(), f"Missing: {_PLAN_DOC}"


def test_h19_is_docs_and_contract_tests_only():
    text = _doc_text().lower()
    assert "docs and contract tests only" in text


def test_production_non_action_statement_present():
    text = _doc_text()
    assert "Production Non-Action Statement" in text


def test_h1_to_h18_chain_documented():
    text = _doc_text()
    for task in _H_CHAIN_TASKS:
        assert task in text, f"Missing task {task} in H1–H18 chain"


def test_feature_flag_must_remain_off_in_h19():
    text = _doc_text()
    assert "POSTED_LEDGER_REPORTS_ENABLED" in text
    assert "remains OFF" in text


def test_no_cloud_run_env_change_in_h19():
    text = _doc_text().lower()
    assert "no cloud run env" in text


def test_no_sql_or_migration_execution_in_h19():
    text = _doc_text().lower()
    assert "no sql" in text
    assert "no migration" in text


def test_no_production_db_or_cloud_run_db_touch():
    text = _doc_text().lower()
    assert "no production db" in text
    assert "no cloud run db" in text


# ---------------------------------------------------------------------------
# Tests 9–15: preconditions section
# ---------------------------------------------------------------------------


def _preconditions_section(text: str) -> str:
    start = text.lower().find("preconditions")
    assert start != -1, "Preconditions section not found in plan doc"
    return text[start : start + 3500]


def test_preconditions_require_local_test_db_verification():
    section = _preconditions_section(_doc_text()).lower()
    assert "local" in section
    assert "db" in section or "database" in section


def test_preconditions_require_staging_or_nonprod_verification():
    section = _preconditions_section(_doc_text()).lower()
    assert "staging" in section or "nonprod" in section or "non-production" in section


def test_preconditions_require_posted_ledger_tables():
    section = _preconditions_section(_doc_text()).lower()
    assert "posted ledger" in section or "journal_entry_headers" in section


def test_preconditions_require_old_vs_new_report_comparison():
    section = _preconditions_section(_doc_text()).lower()
    assert "old" in section
    assert "new" in section
    assert "comparison" in section


def test_preconditions_require_accountant_signoff():
    section = _preconditions_section(_doc_text()).lower()
    assert "accountant" in section
    assert "sign-off" in section


def test_preconditions_require_rollback_plan():
    section = _preconditions_section(_doc_text()).lower()
    assert "rollback plan" in section


def test_preconditions_require_monitoring_plan():
    section = _preconditions_section(_doc_text()).lower()
    assert "monitoring plan" in section


# ---------------------------------------------------------------------------
# Tests 16–22: data/ledger preconditions, reports, gates, checklist
# ---------------------------------------------------------------------------


def test_data_ledger_preconditions_include_required_tables_and_links():
    text = _doc_text()
    for field in _LEDGER_LINK_FIELDS:
        assert field in text, f"Missing required field: {field!r}"


def test_old_vs_new_comparison_lists_all_official_reports():
    text = _doc_text()
    for report in _ALL_OFFICIAL_REPORTS:
        assert report in text, f"Missing report type: {report!r}"


def test_approval_gates_include_all_required_gates():
    text = _doc_text()
    gates_start = text.lower().find("approval gates")
    assert gates_start != -1, "Approval Gates section not found"
    gates_section = text[gates_start : gates_start + 3000].lower()
    for kw in _APPROVAL_GATE_KEYWORDS:
        assert kw in gates_section, f"Missing approval gate keyword: {kw!r}"


def test_rollback_plan_is_feature_flag_off_and_non_destructive():
    text = _doc_text()
    m = re.search(r"^##[^\n]*rollback plan", text, re.MULTILINE | re.IGNORECASE)
    assert m is not None, "Rollback Plan section heading not found"
    section = text[m.start() : m.start() + 3000].lower()
    assert "feature flag" in section or "posted_ledger_reports_enabled" in section
    assert "non-destructive" in section or "do not drop" in section


def test_monitoring_plan_includes_version_health_flag_error_latency():
    text = _doc_text()
    m = re.search(r"^##[^\n]*monitoring plan", text, re.MULTILINE | re.IGNORECASE)
    assert m is not None, "Monitoring Plan section heading not found"
    section = text[m.start() : m.start() + 3000].lower()
    assert "/version" in section
    assert "/health" in section
    assert "error rate" in section or "error_rate" in section
    assert "latency" in section


def test_security_privacy_gates_include_tenant_rbac_no_secrets():
    text = _doc_text()
    security_start = text.lower().find("security")
    assert security_start != -1, "Security section not found"
    section = text[security_start : security_start + 3000].lower()
    assert "tenant_id" in section or "tenant isolation" in section
    assert "rbac" in section or "permission" in section
    assert "secret" in section


def test_go_no_go_checklist_present():
    text = _doc_text().lower()
    assert "go / no-go" in text or "go/no-go" in text or "go no go" in text


# ---------------------------------------------------------------------------
# Tests 23–26: future-only sections and next task
# ---------------------------------------------------------------------------


def test_future_production_switch_marked_not_executed_in_h19():
    text = _doc_text()
    assert "Production Switch Procedure" in text
    assert "Future Only" in text
    assert "Not Executed in H19" in text


def test_post_switch_verification_future_only():
    text = _doc_text()
    assert "Post-Switch Verification" in text
    assert "Future Only" in text


def test_non_goals_forbid_runtime_code_and_ui_changes():
    text = _doc_text().lower()
    nongoals_start = text.find("non-goals")
    assert nongoals_start != -1, "Non-goals section not found"
    section = text[nongoals_start : nongoals_start + 2000]
    assert "runtime" in section or "runtime code" in section
    assert "ui" in section or "static" in section


def test_next_task_h20_documented():
    text = _doc_text()
    assert "H20" in text


# ---------------------------------------------------------------------------
# Tests 27–29: AST-based self-referential safety checks
# ---------------------------------------------------------------------------


def test_no_db_or_network_imports_in_test_file():
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_top = {
        "asyncpg", "psycopg2", "sqlalchemy", "httpx", "requests",
        "aiohttp", "urllib", "socket",
    }
    forbidden_prefix = {
        "startup.migrations", "app.startup",
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
            for prefix in forbidden_prefix:
                assert not node.module.startswith(prefix), (
                    f"Forbidden import prefix in test file: {node.module!r}"
                )


def test_no_gcloud_or_infra_mutation_commands_in_test_file():
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_calls = {"system", "popen", "Popen", "check_call", "check_output"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                fname = node.func.attr
            elif isinstance(node.func, ast.Name):
                fname = node.func.id
            else:
                fname = ""
            assert fname not in forbidden_calls, (
                f"Forbidden subprocess/os call in test file: {fname!r}"
            )
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for tool in ("gcloud", "kubectl", "terraform", "helm"):
                if node.value.startswith(tool + " ") and "deploy" in node.value:
                    raise AssertionError(
                        f"Forbidden infra deploy command in test file: {node.value!r}"
                    )


def test_h19_does_not_start_h20_contract():
    text = _doc_text()
    # H20 must be documented as the next task
    assert "H20" in text
    # Doc must explicitly state H19 does not start H20
    assert "H19 does not start H20" in text
    # Test file must not import any H20 contract module
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "h20" not in node.module.lower(), (
                f"H20 import found in H19 test file: {node.module!r}"
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "h20" not in alias.name.lower(), (
                    f"H20 import found in H19 test file: {alias.name!r}"
                )
