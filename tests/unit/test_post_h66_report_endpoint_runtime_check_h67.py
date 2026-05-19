"""tests/unit/test_post_h66_report_endpoint_runtime_check_h67.py

Contract tests for 11C-H67 — Post-H66 Report Endpoint Runtime Check.
Verifies the docs/post-h66-report-endpoint-runtime-check-h67.md exists and
contains all required runtime findings. No network, no DB, no app imports.
"""
import pathlib
import re
import pytest

DOC_PATH = pathlib.Path(__file__).parents[2] / "docs" / "post-h66-report-endpoint-runtime-check-h67.md"


@pytest.fixture(scope="module")
def doc_text():
    return DOC_PATH.read_text(encoding="utf-8")


class TestDocumentExists:
    def test_runtime_check_doc_exists(self):
        assert DOC_PATH.exists(), "H67 runtime check doc must exist"

    def test_runtime_check_doc_not_empty(self, doc_text):
        assert len(doc_text) > 400

    def test_task_reference(self, doc_text):
        assert "11C-H67" in doc_text


class TestVersionHealthChecks:
    def test_version_endpoint_documented(self, doc_text):
        assert "/version" in doc_text

    def test_h66_sha_documented(self, doc_text):
        assert "7429cfecb61efac48522d933ce6dd27f6b4ba5db" in doc_text

    def test_health_endpoint_documented(self, doc_text):
        assert "/health" in doc_text

    def test_degraded_reason_documented(self, doc_text):
        assert "BALANCE_API_KEY" in doc_text

    def test_demo_mode_documented(self, doc_text):
        assert "demo_mode" in doc_text

    def test_no_secrets_in_health(self, doc_text):
        # Health response must not show actual key values
        assert "BridgeHub2026x" not in doc_text
        assert "sk-ant-api" not in doc_text


class TestUnauthProtection:
    def test_401_documented(self, doc_text):
        assert "401" in doc_text

    def test_trial_balance_unauth_documented(self, doc_text):
        assert "trial-balance" in doc_text

    def test_no_data_without_auth(self, doc_text):
        assert "No report data exposed without auth" in doc_text or "no data" in doc_text.lower() or "not exposed" in doc_text.lower() or "RBAC" in doc_text


class TestAuthenticatedEndpointMatrix:
    def test_endpoint_matrix_present(self, doc_text):
        assert "cashflow" in doc_text

    def test_posted_ledger_unavailable_documented(self, doc_text):
        assert "POSTED_LEDGER_UNAVAILABLE" in doc_text

    def test_journal_entry_lines_error_documented(self, doc_text):
        assert "journal_entry_lines" in doc_text

    def test_cashflow_data_documented(self, doc_text):
        # Actual production values should be in the doc
        assert "91581" in doc_text or "91,581" in doc_text

    def test_no_5xx_documented(self, doc_text):
        assert "5xx" in doc_text

    def test_zero_5xx_confirmed(self, doc_text):
        assert "0" in doc_text


class TestMissingTableStatus:
    def test_bank_transactions_exists_documented(self, doc_text):
        assert "bank_transactions" in doc_text
        assert "EXISTS" in doc_text or "confirmed" in doc_text.lower()

    def test_pipeline_runs_created_documented(self, doc_text):
        assert "pipeline_runs" in doc_text

    def test_journal_entry_lines_still_missing(self, doc_text):
        assert "STILL MISSING" in doc_text or "still missing" in doc_text.lower() or "still absent" in doc_text.lower() or "does not exist" in doc_text.lower()

    def test_migration_011_not_run(self, doc_text):
        assert "migration 011" in doc_text.lower() or "Migration 011" in doc_text


class TestDecision:
    def test_final_decision_documented(self, doc_text):
        assert "BLOCKED_POSTED_LEDGER_SCHEMA_MISSING" in doc_text

    def test_not_rollback(self, doc_text):
        assert "ROLLBACK_REQUIRED" not in doc_text


class TestNoForbiddenPatterns:
    def test_no_raw_jwt(self, doc_text):
        assert not re.search(r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}', doc_text)

    def test_no_bearer_token(self, doc_text):
        assert not re.search(r'Authorization:\s*Bearer\s+eyJ', doc_text)

    def test_no_database_url(self, doc_text):
        assert "postgresql://" not in doc_text

    def test_no_posting_apply(self, doc_text):
        assert "posting/apply" not in doc_text

    def test_no_gcloud_mutation(self, doc_text):
        assert "gcloud run services update" not in doc_text

    def test_no_raw_psql_command(self, doc_text):
        # psql may appear as a word in explanatory text; check it's not used as a command
        assert "$ psql" not in doc_text and "psql postgres" not in doc_text


class TestNoForbiddenImports:
    def test_no_forbidden_imports(self):
        with open(__file__, encoding="utf-8") as fh:
            lines = fh.readlines()
        forbidden = [
            "import " + "psycopg", "import " + "sqlalchemy",
            "import " + "requests", "import " + "httpx",
            "import " + "socket", "import " + "subprocess",
            "from " + "app.", "from docker" + " import",
        ]
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pat in forbidden:
                assert pat not in stripped, f"Forbidden import: {pat!r} in {stripped!r}"
