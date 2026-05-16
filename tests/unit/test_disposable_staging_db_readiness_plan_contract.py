"""
11C-H22 — Disposable/Staging DB Readiness Plan Contract Tests

Verifies documentation completeness and readiness contract for the
disposable/staging database readiness plan.

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

_PLAN_DOC = (
    pathlib.Path(__file__).parents[2]
    / "docs"
    / "disposable-staging-db-readiness-plan.md"
)
_MIGRATION_FILE = (
    pathlib.Path(__file__).parents[2]
    / "app"
    / "storage"
    / "migrations"
    / "011_posted_journal_entries_schema.sql"
)
_THIS_FILE = pathlib.Path(__file__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_H_CHAIN_TASKS = [f"H{i}" for i in range(1, 22)]  # H1 through H21

_REQUIRED_SCHEMA_HEADERS_COLUMNS = [
    "tenant_id",
    "status",
    "posting_log_id",
    "source_draft_id",
    "evidence_bundle_id",
]

_REQUIRED_SCHEMA_LINES_COLUMNS = [
    "journal_entry_id",
    "tenant_id",
    "account_code",
    "ledger_line_id",
]

_REQUIRED_TEST_DATA_KEYWORDS = [
    "correction",
    "reversal",
    "evidence_bundle_id",
    "posting_log_id",
    "source_draft_id",
]

_ALL_OFFICIAL_REPORTS = [
    "Trial Balance",
    "P&L Summary",
    "P&L Detail",
    "Balance Sheet Summary",
    "Balance Sheet Detail",
    "VAT Register",
    "Account Ledger",
    "Counterparty Ledger",
    "Payroll Ledger",
    "Journal Entries List",
    "Cashflow",
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
# Tests 1–5: document existence, non-action, chain, known state
# ---------------------------------------------------------------------------


def test_contract_document_exists():
    assert _PLAN_DOC.exists(), f"Missing: {_PLAN_DOC}"


def test_h22_is_docs_and_contract_tests_only():
    text = _doc_text().lower()
    assert "docs and contract tests only" in text


def test_non_action_statement_present():
    text = _doc_text()
    assert "Non-Action Statement" in text


def test_h1_to_h21_chain_documented():
    text = _doc_text()
    for task in _H_CHAIN_TASKS:
        assert task in text, f"Missing task {task} in H1–H21 chain"


def test_disposable_postgres_decision_documented():
    section = _find_section(_doc_text(), "Decision")
    assert "disposable" in section
    assert "available" in section or "unavailable" in section


# ---------------------------------------------------------------------------
# Tests 6–7: Case A and Case B paths
# ---------------------------------------------------------------------------


def test_case_a_available_path_documented():
    section = _find_section(_doc_text(), "Case A")
    assert "disposable" in section or "available" in section
    assert "migration" in section or "schema" in section


def test_case_b_unavailable_path_documented():
    section = _find_section(_doc_text(), "Case B")
    assert "unavailable" in section or "not available" in section
    assert "infrastructure" in section or "provision" in section


# ---------------------------------------------------------------------------
# Tests 8–13: migration file contract, schema validation, columns
# ---------------------------------------------------------------------------


def test_migration_file_contract_section_present():
    section = _find_section(_doc_text(), "Migration File Contract")
    assert "011_posted_journal_entries_schema.sql" in section
    assert "idempotent" in section or "if not exists" in section


def test_schema_validation_checklist_present():
    section = _find_section(_doc_text(), "Schema Validation")
    assert "journal_entry_headers" in section
    assert "journal_entry_lines" in section


def test_journal_entry_headers_columns_listed():
    section = _find_section(_doc_text(), "Schema Validation")
    for col in _REQUIRED_SCHEMA_HEADERS_COLUMNS:
        assert col in section, f"Missing column in headers checklist: {col!r}"


def test_journal_entry_lines_columns_listed():
    section = _find_section(_doc_text(), "Schema Validation")
    for col in _REQUIRED_SCHEMA_LINES_COLUMNS:
        assert col in section, f"Missing column in lines checklist: {col!r}"


def test_journal_entry_sources_listed():
    section = _find_section(_doc_text(), "Schema Validation")
    assert "journal_entry_sources" in section


def test_synthetic_test_data_requirements_present():
    section = _find_section(_doc_text(), "Synthetic Test Data")
    for kw in _REQUIRED_TEST_DATA_KEYWORDS:
        assert kw in section, f"Missing test data keyword: {kw!r}"


# ---------------------------------------------------------------------------
# Tests 14–17: reports, feature flag, security, go/no-go
# ---------------------------------------------------------------------------


def test_report_verification_checklist_present():
    text = _doc_text()
    for report in _ALL_OFFICIAL_REPORTS:
        assert report in text, f"Missing report type: {report!r}"


def test_feature_flag_decision_rules_present():
    section = _find_section(_doc_text(), "Feature Flag Decision")
    assert "posted_ledger_reports_enabled" in section
    assert "remains off" in section or "remain off" in section
    assert "fail-closed" in section or "fail closed" in section


def test_security_privacy_requirements_present():
    section = _find_section(_doc_text(), "Security")
    assert "tenant_id" in section or "tenant isolation" in section
    assert "secret" in section
    assert "production" in section


def test_go_no_go_criteria_present():
    section = _find_section(_doc_text(), "Go / No-Go")
    assert "go" in section
    assert "no-go" in section
    assert "disposable" in section or "staging" in section


# ---------------------------------------------------------------------------
# Tests 18–20: migration file inspection (read-only text checks)
# ---------------------------------------------------------------------------


def test_migration_file_exists_and_not_executed_in_h22():
    assert _MIGRATION_FILE.exists(), f"Migration file missing: {_MIGRATION_FILE}"
    doc = _doc_text().lower()
    assert "h22 does not execute it" in doc or "does not execute" in doc


def test_migration_file_contains_required_tables():
    sql = _MIGRATION_FILE.read_text(encoding="utf-8")
    assert "journal_entry_headers" in sql
    assert "journal_entry_lines" in sql
    assert "journal_entry_sources" in sql


def test_migration_file_has_no_destructive_sql():
    sql = _MIGRATION_FILE.read_text(encoding="utf-8").upper()
    assert "DROP TABLE" not in sql, "Migration file contains DROP TABLE"
    assert "DELETE FROM" not in sql, "Migration file contains DELETE FROM"
    assert "TRUNCATE" not in sql, "Migration file contains TRUNCATE"


# ---------------------------------------------------------------------------
# Tests 21–23: AST-based self-referential safety checks
# ---------------------------------------------------------------------------


def test_no_db_or_network_imports_in_test_file():
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_top = {
        "asyncpg", "psycopg2", "sqlalchemy", "httpx", "requests",
        "aiohttp", "urllib", "socket",
    }
    forbidden_prefix = {"startup.migrations", "app.startup"}
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


def test_h22_does_not_start_h23_contract():
    text = _doc_text()
    assert "H23" in text
    assert "H22 does not start H23" in text
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "h23" not in node.module.lower(), (
                f"H23 import found in H22 test file: {node.module!r}"
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "h23" not in alias.name.lower(), (
                    f"H23 import found in H22 test file: {alias.name!r}"
                )
