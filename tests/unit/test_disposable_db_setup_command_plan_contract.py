"""
11C-H23 — Disposable DB Setup Contract / Command Plan Tests

Verifies documentation completeness and safety contract for the
disposable DB setup command plan.

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
    / "disposable-db-setup-command-plan.md"
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

_H_CHAIN_TASKS = [f"H{i}" for i in range(1, 23)]  # H1 through H22

_REQUIRED_SAFETY_PRINCIPLES = [
    "disposable only",
    "non-production",
    "no production host",
    "no production credentials",
    "synthetic",
]

_REQUIRED_PREFLIGHT_KEYWORDS = [
    "human approval",
    "localhost",
    "createdb",
    "pg_isready",
    "disposable",
]

_REQUIRED_FIXTURE_CATEGORIES = [
    "correction",
    "reversal",
    "source_draft_id",
    "posting_log_id",
    "evidence_bundle_id",
]

_REQUIRED_EVIDENCE_ITEMS = [
    "operator",
    "transcript",
    "migration",
    "cleanup",
    "go",
]

_REQUIRED_TEARDOWN_KEYWORDS = [
    "dropdb",
    "unset",
    "cleanup",
    "production",
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
# Tests 1–4: document existence, non-action, chain
# ---------------------------------------------------------------------------


def test_contract_document_exists():
    assert _PLAN_DOC.exists(), f"Missing: {_PLAN_DOC}"


def test_h23_is_docs_and_contract_tests_only():
    text = _doc_text().lower()
    assert "docs and contract tests only" in text


def test_non_action_statement_present():
    text = _doc_text()
    assert "Non-Action Statement" in text


def test_h1_to_h22_chain_documented():
    text = _doc_text()
    for task in _H_CHAIN_TASKS:
        assert task in text, f"Missing task {task} in H1–H22 chain"


# ---------------------------------------------------------------------------
# Tests 5–7: safety principles, preflight, environment template
# ---------------------------------------------------------------------------


def test_disposable_db_safety_principles_present():
    section = _find_section(_doc_text(), "Safety Principles")
    for kw in _REQUIRED_SAFETY_PRINCIPLES:
        assert kw in section, f"Missing safety principle: {kw!r}"


def test_preflight_requirements_present():
    section = _find_section(_doc_text(), "Preflight")
    for kw in _REQUIRED_PREFLIGHT_KEYWORDS:
        assert kw in section, f"Missing preflight keyword: {kw!r}"


def test_environment_template_uses_placeholders_only():
    section = _find_section(_doc_text(), "Environment Template")
    assert "placeholder" in section
    assert "<non_prod_user>" in section or "<non_prod_password>" in section or "non_prod_" in section
    assert "placeholders only" in section or "placeholder" in section
    assert "never commit" in section or "do not commit" in section or "never set" in section


# ---------------------------------------------------------------------------
# Tests 8–10: command plan, production guards, migration plan
# ---------------------------------------------------------------------------


def test_future_command_plan_marked_not_executed():
    section = _find_section(_doc_text(), "Future Command Plan")
    assert "not executed" in section
    assert "future" in section
    assert "createdb" in section or "pg_isready" in section


def test_production_guard_commands_present():
    section = _find_section(_doc_text(), "Production Guard")
    assert "production host" in section or "production" in section
    assert "aborting" in section or "abort" in section
    assert "guard" in section


def test_011_migration_execution_plan_marked_future_only():
    section = _find_section(_doc_text(), "011 Migration Execution Plan")
    assert "future only" in section or "not executed" in section
    assert "011_posted_journal_entries_schema.sql" in section
    assert "not executed in h23" in section or "future" in section


# ---------------------------------------------------------------------------
# Tests 11–13: schema inspection, fixture load, verification commands
# ---------------------------------------------------------------------------


def test_schema_inspection_commands_present():
    section = _find_section(_doc_text(), "Schema Inspection")
    assert "journal_entry_headers" in section
    assert "journal_entry_lines" in section
    assert "journal_entry_sources" in section
    assert "tenant_id" in section
    assert "future only" in section or "not executed" in section


def test_synthetic_fixture_load_plan_present():
    section = _find_section(_doc_text(), "Synthetic Fixture")
    for kw in _REQUIRED_FIXTURE_CATEGORIES:
        assert kw in section, f"Missing fixture category: {kw!r}"
    assert "no production data" in section or "no real" in section


def test_future_verification_commands_present():
    section = _find_section(_doc_text(), "Future Verification")
    assert "pytest" in section or "python -m pytest" in section
    assert "not executed in h23" in section or "future" in section
    assert "database_url" in section or "test_mode" in section


# ---------------------------------------------------------------------------
# Tests 14–16: evidence, cleanup, go/no-go
# ---------------------------------------------------------------------------


def test_evidence_collection_template_present():
    section = _find_section(_doc_text(), "Evidence Collection")
    for kw in _REQUIRED_EVIDENCE_ITEMS:
        assert kw in section, f"Missing evidence item: {kw!r}"


def test_cleanup_teardown_plan_present():
    section = _find_section(_doc_text(), "Cleanup")
    for kw in _REQUIRED_TEARDOWN_KEYWORDS:
        assert kw in section, f"Missing teardown keyword: {kw!r}"


def test_go_no_go_criteria_present():
    section = _find_section(_doc_text(), "Go / No-Go")
    assert "go" in section
    assert "no-go" in section
    assert "human approval" in section or "approved" in section


# ---------------------------------------------------------------------------
# Tests 17–18: non-goals, next task
# ---------------------------------------------------------------------------


def test_non_goals_forbid_db_sql_migration_runtime_ui_changes():
    section = _find_section(_doc_text(), "Non-Goals")
    assert "database" in section or " db" in section
    assert "sql" in section
    assert "migration" in section
    assert "runtime" in section or "runtime code" in section
    assert "ui" in section or "static" in section


def test_next_task_h24_or_sec1_documented():
    text = _doc_text()
    assert "H24" in text
    assert "SEC-1" in text


# ---------------------------------------------------------------------------
# Tests 19–20: migration file checks, no real credentials
# ---------------------------------------------------------------------------


def test_sql_migration_file_exists_but_is_not_executed():
    assert _MIGRATION_FILE.exists(), f"Migration file missing: {_MIGRATION_FILE}"
    doc = _doc_text().lower()
    assert "not executed in h23" in doc or "not executed" in doc


def test_no_real_credentials_or_production_hosts_in_doc():
    text = _doc_text()
    # No real password patterns (must be placeholders only)
    import re as _re
    real_pw = _re.findall(r'password\s*[=:]\s*["\']?(?!<)[A-Za-z0-9!@#$%^&*]{8,}', text, _re.IGNORECASE)
    assert not real_pw, f"Possible real password found in doc: {real_pw}"
    # No known production host patterns (Cloud SQL socket or IP-like production strings)
    assert "cloudsql" not in text.lower() or "cloud sql" in text.lower()
    # Doc must contain placeholder markers
    assert "<non_prod_user>" in text.lower() or "<non_prod_password>" in text.lower() or "placeholder" in text.lower()


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


def test_no_subprocess_or_infra_mutation_commands_in_test_file():
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


def test_h23_does_not_start_h24_contract():
    text = _doc_text()
    assert "H24" in text
    assert "H23 does not start H24" in text
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "h24" not in node.module.lower(), (
                f"H24 import found in H23 test file: {node.module!r}"
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "h24" not in alias.name.lower(), (
                    f"H24 import found in H23 test file: {alias.name!r}"
                )
