"""tests/unit/test_report_mismatch_recheck_after_schema_fix_h67.py

Contract tests for 11C-H67 — Report Mismatch Recheck After H66 Schema Fix.
Verifies the docs/report-mismatch-recheck-after-schema-fix-h67.md exists and
contains all required decisions and findings. No network, no DB, no app imports.
"""
import pathlib
import re
import pytest

DOC_PATH = pathlib.Path(__file__).parents[2] / "docs" / "report-mismatch-recheck-after-schema-fix-h67.md"
SAFETY_DOC = pathlib.Path(__file__).parents[2] / "docs" / "h67-authenticated-report-safety-summary.md"
RUNTIME_DOC = pathlib.Path(__file__).parents[2] / "docs" / "post-h66-report-endpoint-runtime-check-h67.md"


@pytest.fixture(scope="module")
def doc_text():
    return DOC_PATH.read_text(encoding="utf-8")


class TestDocumentExists:
    def test_h67_mismatch_doc_exists(self):
        assert DOC_PATH.exists(), "H67 mismatch recheck doc must exist"

    def test_h67_mismatch_doc_not_empty(self, doc_text):
        assert len(doc_text) > 500

    def test_task_reference(self, doc_text):
        assert "11C-H67" in doc_text

    def test_follows_h66(self, doc_text):
        assert "H66" in doc_text or "h66" in doc_text


class TestH65BPriorFinding:
    def test_prior_blocker_documented(self, doc_text):
        assert "REPORT_MISMATCH_DEEP_CHECK_BLOCKED_NO_REPORT_DATA" in doc_text

    def test_h65b_referenced(self, doc_text):
        assert "H65B" in doc_text

    def test_root_cause_documented(self, doc_text):
        assert "journal_entry_lines" in doc_text

    def test_migration_011_context(self, doc_text):
        assert "011" in doc_text


class TestH66SchemaFixContext:
    def test_bank_transactions_fix_documented(self, doc_text):
        assert "bank_transactions" in doc_text

    def test_pipeline_runs_fix_documented(self, doc_text):
        assert "pipeline_runs" in doc_text

    def test_account_type_fix_documented(self, doc_text):
        assert "account_type" in doc_text

    def test_cashflow_category_fix_documented(self, doc_text):
        assert "cashflow_category" in doc_text

    def test_alter_table_context_documented(self, doc_text):
        assert "ALTER TABLE" in doc_text


class TestAuthTokenAvailability:
    def test_token_availability_documented(self, doc_text):
        assert "Token" in doc_text or "token" in doc_text

    def test_token_not_raw_in_doc(self, doc_text):
        # Must not contain a raw JWT (three dot-separated base64 segments)
        assert not re.search(r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}', doc_text)

    def test_no_authorization_bearer_literal(self, doc_text):
        # Must not contain a literal populated Bearer token
        assert not re.search(r'Authorization:\s*Bearer\s+eyJ', doc_text)


class TestEndpointMatrix:
    def test_trial_balance_classified(self, doc_text):
        assert "trial-balance" in doc_text or "trial_balance" in doc_text

    def test_balance_sheet_classified(self, doc_text):
        assert "balance-sheet" in doc_text or "balance_sheet" in doc_text

    def test_cashflow_pass_documented(self, doc_text):
        assert "PASS_WITH_DATA" in doc_text

    def test_blocked_schema_missing_documented(self, doc_text):
        assert "BLOCKED_SCHEMA_MISSING" in doc_text

    def test_blocked_not_implemented_documented(self, doc_text):
        assert "BLOCKED_NOT_IMPLEMENTED" in doc_text


class TestH53BaselineReference:
    def test_h53_referenced(self, doc_text):
        assert "H53" in doc_text

    def test_synthetic_fixture_noted(self, doc_text):
        assert "synthetic" in doc_text.lower() or "fixture" in doc_text.lower()


class TestInvariantChecks:
    def test_no_5xx_confirmed(self, doc_text):
        assert "5xx" in doc_text

    def test_no_secrets_confirmed(self, doc_text):
        assert "secret" in doc_text.lower() or "Secret" in doc_text

    def test_no_cross_tenant_confirmed(self, doc_text):
        assert "cross-tenant" in doc_text or "tenant" in doc_text.lower()


class TestMismatchDecision:
    def test_final_decision_present(self, doc_text):
        assert "REPORT_MISMATCH_DEEP_CHECK_BLOCKED_SCHEMA_MISSING" in doc_text

    def test_not_rollback_decision(self, doc_text):
        assert "ROLLBACK_REQUIRED" not in doc_text

    def test_cashflow_confirmed_live(self, doc_text):
        # Cashflow data values should be documented
        assert "91581" in doc_text or "91,581" in doc_text

    def test_bank_transactions_confirmed_live(self, doc_text):
        assert "CONFIRMED" in doc_text or "confirmed" in doc_text.lower()

    def test_migration_011_root_cause(self, doc_text):
        assert "migration 011" in doc_text.lower() or "Migration 011" in doc_text


class TestNoForbiddenPatterns:
    def test_no_database_url(self, doc_text):
        assert "postgresql://" not in doc_text

    def test_no_production_password(self, doc_text):
        assert "BridgeHub2026x" not in doc_text

    def test_no_posting_apply(self, doc_text):
        assert "posting/" + "apply" not in doc_text

    def test_no_gcloud_mutation(self, doc_text):
        assert "gcloud run services update" not in doc_text

    def test_no_balance_activation(self, doc_text):
        assert "BALANCE_API_KEY=" not in doc_text or "missing" in doc_text


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
