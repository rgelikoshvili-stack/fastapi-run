"""
11C-H20 — Staging Environment Readiness Plan Contract Tests

Verifies documentation completeness and planning contract for the staging
environment readiness plan required before any non-production feature flag
switch or future production report migration.

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

_PLAN_DOC = pathlib.Path(__file__).parents[2] / "docs" / "staging-environment-readiness-plan.md"
_THIS_FILE = pathlib.Path(__file__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_H_CHAIN_TASKS = [f"H{i}" for i in range(1, 20)]  # H1 through H19

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

_REQUIRED_STAGING_COMPONENT_KEYWORDS = [
    "staging cloud run",
    "staging database",
    "test data",
    "secrets",
]

_REQUIRED_ISOLATION_KEYWORDS = [
    "production db",
    "credentials",
    "tenant",
]

_REQUIRED_TEST_DATA_KEYWORDS = [
    "correction",
    "reversal",
    "vat",
    "payroll",
    "evidence_bundle_id",
    "posting_log_id",
    "source_draft_id",
]

_REQUIRED_MONITORING_KEYWORDS = [
    "/version",
    "/health",
    "error rate",
    "latency",
]

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _doc_text() -> str:
    assert _PLAN_DOC.exists(), f"Plan doc missing: {_PLAN_DOC}"
    return _PLAN_DOC.read_text(encoding="utf-8")


def _find_section(text: str, keyword: str, window: int = 3000) -> str:
    m = re.search(rf"^##[^\n]*{re.escape(keyword)}", text, re.MULTILINE | re.IGNORECASE)
    assert m is not None, f"Section not found: {keyword!r}"
    return text[m.start() : m.start() + window].lower()


# ---------------------------------------------------------------------------
# Tests 1–9: document existence and non-action statement
# ---------------------------------------------------------------------------


def test_contract_document_exists():
    assert _PLAN_DOC.exists(), f"Missing: {_PLAN_DOC}"


def test_h20_is_docs_and_contract_tests_only():
    text = _doc_text().lower()
    assert "docs and contract tests only" in text


def test_staging_non_action_statement_present():
    text = _doc_text()
    assert "Staging Non-Action Statement" in text


def test_h1_to_h19_chain_documented():
    text = _doc_text()
    for task in _H_CHAIN_TASKS:
        assert task in text, f"Missing task {task} in H1–H19 chain"


def test_no_staging_infrastructure_created_in_h20():
    text = _doc_text().lower()
    assert "does not create staging" in text or "no staging cloud run service is created" in text


def test_no_feature_flag_enablement_in_h20():
    text = _doc_text().lower()
    assert "does not enable any feature flag" in text or "no feature flag is enabled" in text
    assert "posted_ledger_reports_enabled" in text


def test_no_cloud_run_env_change_in_h20():
    text = _doc_text().lower()
    assert "no cloud run env" in text


def test_no_sql_or_migration_execution_in_h20():
    text = _doc_text().lower()
    assert "no sql" in text
    assert "no migration" in text


def test_no_production_db_or_cloud_run_db_touch():
    text = _doc_text().lower()
    assert "no production db" in text
    assert "no cloud run db" in text


# ---------------------------------------------------------------------------
# Tests 10–14: components, isolation, feature flag, staging DB, test data
# ---------------------------------------------------------------------------


def test_required_staging_components_listed():
    section = _find_section(_doc_text(), "Required Staging Environment Components")
    for kw in _REQUIRED_STAGING_COMPONENT_KEYWORDS:
        assert kw in section, f"Missing staging component keyword: {kw!r}"


def test_environment_isolation_requirements_present():
    section = _find_section(_doc_text(), "Environment Isolation Requirements")
    for kw in _REQUIRED_ISOLATION_KEYWORDS:
        assert kw in section, f"Missing isolation keyword: {kw!r}"


def test_feature_flag_readiness_rules_present():
    section = _find_section(_doc_text(), "Feature Flag Readiness")
    assert "posted_ledger_reports_enabled" in section
    assert "default off" in section or "default: off" in section or "default\n" in section or "default" in section
    assert "fail-closed" in section or "fail closed" in section


def test_staging_database_readiness_requirements_present():
    section = _find_section(_doc_text(), "Staging Database Readiness")
    assert "journal_entry_headers" in section
    assert "journal_entry_lines" in section


def test_test_data_readiness_requirements_present():
    section = _find_section(_doc_text(), "Test Data Readiness")
    for kw in _REQUIRED_TEST_DATA_KEYWORDS:
        assert kw in section, f"Missing test data keyword: {kw!r}"


# ---------------------------------------------------------------------------
# Tests 15–19: reports, security, monitoring, rollback, go/no-go
# ---------------------------------------------------------------------------


def test_all_official_reports_in_verification_checklist():
    text = _doc_text()
    for report in _ALL_OFFICIAL_REPORTS:
        assert report in text, f"Missing report type: {report!r}"


def test_security_access_readiness_present():
    section = _find_section(_doc_text(), "Security")
    assert "rbac" in section or "permission" in section
    assert "tenant_id" in section or "tenant isolation" in section
    assert "401" in section or "403" in section


def test_monitoring_observability_readiness_present():
    section = _find_section(_doc_text(), "Monitoring")
    for kw in _REQUIRED_MONITORING_KEYWORDS:
        assert kw in section, f"Missing monitoring keyword: {kw!r}"


def test_rollback_readiness_present():
    section = _find_section(_doc_text(), "Rollback Readiness")
    assert "non-destructive" in section or "do not drop" in section
    assert "feature flag" in section or "posted_ledger_reports_enabled" in section


def test_go_no_go_checklist_present():
    text = _doc_text().lower()
    assert "go / no-go" in text or "go/no-go" in text or "go no go" in text


# ---------------------------------------------------------------------------
# Tests 20–22: gaps, non-goals, next task
# ---------------------------------------------------------------------------


def test_staging_readiness_gaps_documented():
    section = _find_section(_doc_text(), "Staging Readiness Gaps")
    assert "does not exist" in section or "future" in section


def test_non_goals_forbid_runtime_code_and_ui_changes():
    section = _find_section(_doc_text(), "Non-Goals")
    assert "runtime" in section or "runtime code" in section
    assert "ui" in section or "static" in section


def test_next_task_h21_documented():
    text = _doc_text()
    assert "H21" in text


# ---------------------------------------------------------------------------
# Tests 23–25: AST-based self-referential safety checks
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


def test_h20_does_not_start_h21_contract():
    text = _doc_text()
    # H21 must be documented as the next task
    assert "H21" in text
    # Doc must explicitly state H20 does not start H21
    assert "H20 does not start H21" in text
    # Test file must not import any H21 contract module
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "h21" not in node.module.lower(), (
                f"H21 import found in H20 test file: {node.module!r}"
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "h21" not in alias.name.lower(), (
                    f"H21 import found in H20 test file: {alias.name!r}"
                )
