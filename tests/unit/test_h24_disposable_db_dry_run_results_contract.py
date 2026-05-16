"""
11C-H24 — Disposable DB Dry-Run Results Contract Tests

Verifies that docs/h24-disposable-db-dry-run-results.md exists and documents
all required sections, safety confirmations, and verdict.

No DB, no network, no subprocess execution, no SQL, no migrations.
All assertions are read-only document text scans.
"""

import ast
import pathlib
import re

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ROOT = pathlib.Path(__file__).parents[2]
_DOC = _ROOT / "docs" / "h24-disposable-db-dry-run-results.md"
_THIS_FILE = pathlib.Path(__file__)

# Forbidden credential fragments (split to avoid self-match)
_FORBIDDEN_PASSWORD = "BridgeHub" + "2026x"
_FORBIDDEN_HOST_IP = "35.192" + ".214.120"
_FORBIDDEN_SSH_HOST = "116.203" + ".134.24"
_FORBIDDEN_ADMIN_PW = "Admin" + "2026!"


def _doc_text() -> str:
    assert _DOC.exists(), f"H24 results document missing: {_DOC}"
    return _DOC.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 1: document exists
# ---------------------------------------------------------------------------


def test_h24_results_document_exists():
    assert _DOC.exists(), f"Missing: {_DOC}"
    assert _DOC.stat().st_size > 0, "H24 results document is empty"


# ---------------------------------------------------------------------------
# Test 2: mode documents disposable-only intent
# ---------------------------------------------------------------------------


def test_h24_mode_documents_disposable_only():
    text = _doc_text().lower()
    assert "disposable" in text, "Mode section must document disposable DB intent"
    assert "no production db" in text or "no production" in text, (
        "Mode must document no production DB"
    )
    assert "no cloud run" in text, "Mode must document no Cloud Run DB"
    assert "no balance" in text, "Mode must document no Balance.ge"
    assert "no feature flag" in text or "no runtime behavior" in text, (
        "Mode must document no feature flag or runtime behavior change"
    )


# ---------------------------------------------------------------------------
# Test 3: preflight guards documented
# ---------------------------------------------------------------------------


def test_preflight_guards_documented():
    text = _doc_text().lower()
    assert "preflight" in text or "guard" in text, "Preflight guards section missing"
    assert "operator approval" in text, "Operator approval not documented in guards"
    assert "localhost" in text, "DB host localhost must be documented"
    assert "bridgehub_disposable" in text or "bridgehub_test" in text, (
        "Disposable DB name must be documented"
    )
    assert "posted_ledger_reports_enabled" in text, (
        "POSTED_LEDGER_REPORTS_ENABLED guard must be documented"
    )
    assert "balance_api_key" in text, "BALANCE_API_KEY guard must be documented"
    assert "cleanup" in text, "Cleanup plan must be documented in preflight"


# ---------------------------------------------------------------------------
# Test 4: no production DB or Cloud Run DB documented
# ---------------------------------------------------------------------------


def test_no_production_db_or_cloud_run_db_documented():
    text = _doc_text().lower()
    assert "no production db" in text or "no production" in text, (
        "Must document no production DB used"
    )
    assert "no cloud run" in text, "Must document no Cloud Run DB used"
    # The document must not claim production was connected
    assert "connected to production" not in text, (
        "Document must not claim production DB was connected"
    )


# ---------------------------------------------------------------------------
# Test 5: no Balance.ge or feature flag documented
# ---------------------------------------------------------------------------


def test_no_balance_or_feature_flag_documented():
    text = _doc_text().lower()
    assert "no balance" in text, "Must document no Balance.ge"
    assert "demo_mode" in text or "not touched" in text or "no feature flag" in text, (
        "Must document Balance.ge / feature flag status"
    )
    assert "posted_ledger_reports_enabled" in text, (
        "POSTED_LEDGER_REPORTS_ENABLED must be documented as off/unset"
    )


# ---------------------------------------------------------------------------
# Test 6: disposable DB setup result documented
# ---------------------------------------------------------------------------


def test_disposable_db_setup_result_documented():
    text = _doc_text().lower()
    assert "disposable db setup" in text or "db setup" in text, (
        "Disposable DB setup section missing"
    )
    # Must document whether tools were available
    assert "psql" in text, "psql tool check must be documented"
    assert "pg_isready" in text, "pg_isready check must be documented"
    assert "createdb" in text, "createdb result must be documented"
    # Must document the outcome
    assert "blocked" in text or "not executed" in text or "not available" in text, (
        "DB setup outcome must be documented"
    )


# ---------------------------------------------------------------------------
# Test 7: migration execution result documented
# ---------------------------------------------------------------------------


def test_migration_execution_result_documented():
    text = _doc_text().lower()
    assert "migration execution" in text, "Migration execution section missing"
    assert "011_posted_journal_entries_schema.sql" in text.lower() or "011" in text, (
        "Migration file must be referenced"
    )
    assert "on_error_stop" in text or "not executed" in text, (
        "ON_ERROR_STOP flag or not-executed status must be documented"
    )
    assert "not executed" in text or "blocked" in text, (
        "Migration execution outcome must document not executed or blocked"
    )


# ---------------------------------------------------------------------------
# Test 8: schema inspection result documented
# ---------------------------------------------------------------------------


def test_schema_inspection_result_documented():
    text = _doc_text()
    lower = text.lower()
    assert "schema inspection" in lower or "schema" in lower, (
        "Schema inspection section missing"
    )
    assert "journal_entry_headers" in text, (
        "journal_entry_headers must be referenced in schema section"
    )
    assert "journal_entry_lines" in text, (
        "journal_entry_lines must be referenced in schema section"
    )
    assert "journal_entry_sources" in text, (
        "journal_entry_sources must be referenced in schema section"
    )
    assert "tenant_id" in text, "tenant_id column must be documented"
    assert "total_debit" in text and "total_credit" in text, (
        "Balanced header constraint columns must be documented"
    )
    assert "additive" in lower, "Additive-only behavior must be documented"
    assert "evidence_bundle_id" in text, "evidence_bundle_id must be documented"
    assert "posting_log_id" in text, "posting_log_id must be documented"
    assert "source_draft_id" in text, "source_draft_id must be documented"


# ---------------------------------------------------------------------------
# Test 9: idempotency check documented
# ---------------------------------------------------------------------------


def test_idempotency_check_documented():
    text = _doc_text().lower()
    assert "idempotency" in text, "Idempotency check section missing"
    # Must document either execution result or reason it was not run
    assert "if not exists" in text or "not executed" in text or "idempotent" in text, (
        "Idempotency check must document IF NOT EXISTS guards or execution result"
    )


# ---------------------------------------------------------------------------
# Test 10: cleanup / teardown documented
# ---------------------------------------------------------------------------


def test_cleanup_teardown_documented():
    text = _doc_text().lower()
    assert "cleanup" in text or "teardown" in text, (
        "Cleanup / teardown section missing"
    )
    assert "dropdb" in text, "dropdb command must be documented in cleanup"
    assert "database_url" in text, "DATABASE_URL unset must be documented in cleanup"


# ---------------------------------------------------------------------------
# Test 11: safety confirmation documented
# ---------------------------------------------------------------------------


def test_safety_confirmation_documented():
    text = _doc_text().lower()
    assert "safety confirmation" in text, "Safety confirmation section missing"
    assert "no production db" in text or "no production" in text, (
        "No production DB confirmation missing"
    )
    assert "no cloud run" in text, "No Cloud Run DB confirmation missing"
    assert "no balance" in text, "No Balance.ge confirmation missing"
    assert "no feature flag" in text or "no runtime code" in text, (
        "No feature flag or no runtime code change confirmation missing"
    )
    assert "no infrastructure" in text, "No infrastructure change confirmation missing"


# ---------------------------------------------------------------------------
# Test 12: verdict documented
# ---------------------------------------------------------------------------


def test_verdict_documented():
    text = _doc_text().lower()
    assert "verdict" in text, "Verdict section missing"
    # Must be one of: blocked, passed, failed
    assert "blocked" in text or "passed" in text or "failed" in text, (
        "Verdict must state blocked, passed, or failed"
    )
    # Must reference next task
    assert "h25" in text, "Next task H25 must be referenced in verdict"
    assert "safe to proceed" in text, "'Safe to proceed' statement missing from verdict"


# ---------------------------------------------------------------------------
# Test 13: no real credentials in results document
# ---------------------------------------------------------------------------


def test_no_real_credentials_in_results_doc():
    text = _doc_text()
    assert _FORBIDDEN_PASSWORD not in text, (
        "Forbidden hardcoded password found in H24 results doc"
    )
    assert _FORBIDDEN_HOST_IP not in text, (
        "Forbidden production host IP found in H24 results doc"
    )
    assert _FORBIDDEN_SSH_HOST not in text, (
        "Forbidden production SSH host found in H24 results doc"
    )
    assert _FORBIDDEN_ADMIN_PW not in text, (
        "Forbidden admin password found in H24 results doc"
    )
    # No private key material (stored as fragments to avoid self-match in repo scan)
    for marker in [
        "BEGIN " + "RSA",
        "BEGIN " + "OPENSSH",
        "BEGIN " + "PRIVATE",
        "PRIVATE " + "KEY",
    ]:
        assert marker not in text, (
            f"Private key material marker {marker!r} found in H24 results doc"
        )


# ---------------------------------------------------------------------------
# Test 14: no DB or network imports in this test file
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
# Test 15: no subprocess execution in this test file
# ---------------------------------------------------------------------------


def test_no_subprocess_execution_in_test_file():
    source = _THIS_FILE.read_text(encoding="utf-8")
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
                    raise AssertionError(
                        f"Forbidden subprocess/os call in test file: {fname!r}"
                    )
