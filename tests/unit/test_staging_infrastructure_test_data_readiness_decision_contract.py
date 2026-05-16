"""
11C-H21 — Staging Infrastructure / Test Data Readiness Decision Contract Tests

Verifies documentation completeness and decision contract for the staging
infrastructure and test data readiness decision.

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
    / "staging-infrastructure-test-data-readiness-decision.md"
)
_THIS_FILE = pathlib.Path(__file__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_H_CHAIN_TASKS = [f"H{i}" for i in range(1, 21)]  # H1 through H20

_DECISION_CASES = ["Case A", "Case B", "Case C", "Case D", "Case E", "Case F"]

_REQUIRED_EVIDENCE_KEYWORDS = [
    "staging service",
    "staging db",
    "test data",
    "not production",
]

_TEST_DATA_KEYWORDS = [
    "posted income",
    "correction",
    "reversal",
    "evidence_bundle_id",
    "posting_log_id",
    "source_draft_id",
]

_STAGING_DB_KEYWORDS = [
    "journal_entry_headers",
    "journal_entry_lines",
    "tenant_id",
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


def test_h21_is_docs_and_contract_tests_only():
    text = _doc_text().lower()
    assert "docs and contract tests only" in text


def test_non_action_statement_present():
    text = _doc_text()
    assert "Non-Action Statement" in text


def test_h1_to_h20_chain_documented():
    text = _doc_text()
    for task in _H_CHAIN_TASKS:
        assert task in text, f"Missing task {task} in H1–H20 chain"


def test_current_known_state_documented():
    section = _find_section(_doc_text(), "Current Known State")
    assert "not confirmed" in section or "unavailable" in section
    assert "staging" in section


# ---------------------------------------------------------------------------
# Tests 6–11: decision matrix, evidence, test data, DB, feature flag, security
# ---------------------------------------------------------------------------


def test_decision_matrix_lists_all_required_cases():
    section = _find_section(_doc_text(), "Decision Matrix")
    for case in _DECISION_CASES:
        assert case.lower() in section, f"Missing decision case: {case!r}"


def test_required_evidence_before_staging_switch():
    section = _find_section(_doc_text(), "Required Evidence")
    for kw in _REQUIRED_EVIDENCE_KEYWORDS:
        assert kw in section, f"Missing evidence keyword: {kw!r}"


def test_test_data_readiness_requirements_present():
    section = _find_section(_doc_text(), "Test Data Readiness")
    for kw in _TEST_DATA_KEYWORDS:
        assert kw in section, f"Missing test data keyword: {kw!r}"


def test_staging_db_readiness_requirements_present():
    section = _find_section(_doc_text(), "Staging DB Readiness")
    for kw in _STAGING_DB_KEYWORDS:
        assert kw in section, f"Missing staging DB keyword: {kw!r}"


def test_feature_flag_decision_rules_present():
    section = _find_section(_doc_text(), "Feature Flag Decision")
    assert "posted_ledger_reports_enabled" in section
    assert "remains off" in section or "remain off" in section
    assert "fail-closed" in section or "fail closed" in section


def test_security_privacy_decision_present():
    section = _find_section(_doc_text(), "Security")
    assert "rbac" in section or "permission" in section
    assert "tenant_id" in section or "tenant isolation" in section
    assert "secret" in section


# ---------------------------------------------------------------------------
# Tests 12–15: recommended path, go/no-go, non-goals, next task
# ---------------------------------------------------------------------------


def test_recommended_next_path_documented():
    section = _find_section(_doc_text(), "Recommended Next Path")
    assert "h22" in section
    assert "disposable" in section or "db readiness" in section


def test_go_no_go_criteria_present():
    section = _find_section(_doc_text(), "Go / No-Go")
    assert "go" in section
    assert "no-go" in section


def test_non_goals_forbid_infra_db_runtime_ui_changes():
    section = _find_section(_doc_text(), "Non-Goals")
    assert "infrastructure" in section or "infra" in section
    assert "database" in section or " db" in section
    assert "runtime" in section
    assert "ui" in section or "static" in section


def test_next_task_h22_documented():
    text = _doc_text()
    assert "H22" in text


# ---------------------------------------------------------------------------
# Tests 16–18: AST-based self-referential safety checks
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


def test_h21_does_not_start_h22_contract():
    text = _doc_text()
    # H22 must be documented as the next task
    assert "H22" in text
    # Doc must explicitly state H21 does not start H22
    assert "H21 does not start H22" in text
    # Test file must not import any H22 contract module
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "h22" not in node.module.lower(), (
                f"H22 import found in H21 test file: {node.module!r}"
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "h22" not in alias.name.lower(), (
                    f"H22 import found in H21 test file: {alias.name!r}"
                )
