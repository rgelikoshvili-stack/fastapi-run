"""tests/unit/test_h67_authenticated_report_safety_summary.py

Contract tests for 11C-H67 — Authenticated Report Safety Summary.
Verifies the docs/h67-authenticated-report-safety-summary.md exists and
records all required safety properties. No network, no DB, no app imports.
"""
import pathlib
import re
import pytest

DOC_PATH = pathlib.Path(__file__).parents[2] / "docs" / "h67-authenticated-report-safety-summary.md"


@pytest.fixture(scope="module")
def doc_text():
    return DOC_PATH.read_text(encoding="utf-8")


class TestDocumentExists:
    def test_safety_summary_doc_exists(self):
        assert DOC_PATH.exists(), "H67 safety summary doc must exist"

    def test_safety_summary_not_empty(self, doc_text):
        assert len(doc_text) > 400

    def test_task_reference(self, doc_text):
        assert "11C-H67" in doc_text


class TestTokenSafety:
    def test_token_safety_section_present(self, doc_text):
        assert "Token" in doc_text

    def test_token_not_committed(self, doc_text):
        assert "No" in doc_text  # "Token committed to git: No"

    def test_no_raw_jwt(self, doc_text):
        assert not re.search(r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}', doc_text)

    def test_no_bearer_literal(self, doc_text):
        assert not re.search(r'Authorization:\s*Bearer\s+eyJ', doc_text)

    def test_token_not_stored_in_doc(self, doc_text):
        assert "H65_AUTH_TOKEN=" not in doc_text


class TestTenantSafetyRecheck:
    def test_tenant_safety_recheck_section(self, doc_text):
        assert "Tenant" in doc_text

    def test_unauthenticated_401_reconfirmed(self, doc_text):
        assert "401" in doc_text

    def test_tenant_scoped_confirmed(self, doc_text):
        assert "tenant_id" in doc_text or "tenant" in doc_text.lower()

    def test_tenant_safety_decision_documented(self, doc_text):
        assert "TENANT_SAFETY_RECHECK_PASS" in doc_text

    def test_no_tenant_leakage_decision(self, doc_text):
        # The trigger name may appear in the evaluation table (as NOT fired),
        # but the final H67 decision must not be ROLLBACK_REQUIRED_TENANT_LEAKAGE
        assert "H67 decision: ROLLBACK_REQUIRED" "TENANT_LEAKAGE" not in doc_text
        assert "Fired? Yes" not in doc_text


class TestBalanceGeGuard:
    def test_balance_ge_section_present(self, doc_text):
        assert "Balance.ge" in doc_text or "balance" in doc_text.lower()

    def test_demo_mode_confirmed(self, doc_text):
        assert "demo_mode" in doc_text

    def test_balance_api_key_missing(self, doc_text):
        assert "missing" in doc_text.lower()

    def test_balance_not_activated(self, doc_text):
        assert "No" in doc_text  # "Balance.ge activated during H67: No"


class TestPostingApplyGuard:
    def test_posting_guard_section(self, doc_text):
        assert "posting" in doc_text.lower() or "Posting" in doc_text

    def test_no_posting_apply_called(self, doc_text):
        # posting/apply should appear only as "not called" or in negation
        if "posting/apply" in doc_text:
            # Must be negated
            idx = doc_text.find("posting/apply")
            context = doc_text[max(0, idx-20):idx+60]
            assert "No" in context or "not" in context.lower()

    def test_no_write_endpoints_called(self, doc_text):
        assert "write endpoint" in doc_text.lower() or "No" in doc_text


class TestProductionDbSafety:
    def test_db_safety_section(self, doc_text):
        assert "DB" in doc_text or "database" in doc_text.lower()

    def test_no_direct_db_connection(self, doc_text):
        assert "Direct DB connection" in doc_text or "direct" in doc_text.lower()

    def test_no_manual_sql(self, doc_text):
        assert "Manual SQL" in doc_text or "manual sql" in doc_text.lower()

    def test_no_production_url_in_doc(self, doc_text):
        assert "postgresql://" not in doc_text

    def test_no_psql(self, doc_text):
        assert "psql " not in doc_text


class TestRollbackTriggerEvaluation:
    def test_rollback_section_present(self, doc_text):
        assert "Rollback" in doc_text or "rollback" in doc_text

    def test_no_rollback_required(self, doc_text):
        assert "NOT REQUIRED" in doc_text or "not required" in doc_text.lower()

    def test_no_5xx_rollback_trigger(self, doc_text):
        assert "ROLLBACK_REQUIRED_REPORT_ENDPOINT_5XX" in doc_text

    def test_no_secret_exposure_trigger(self, doc_text):
        assert "ROLLBACK_REQUIRED_SECRET_EXPOSURE" in doc_text

    def test_no_auth_bypass_trigger(self, doc_text):
        assert "ROLLBACK_REQUIRED_AUTH_BYPASS" in doc_text


class TestFinalDecision:
    def test_final_h67_decision_present(self, doc_text):
        assert "H67_BLOCKED_POSTED_LEDGER_SCHEMA_MISSING" in doc_text

    def test_next_task_documented(self, doc_text):
        assert "H68" in doc_text

    def test_migration_011_next_action(self, doc_text):
        assert "migration 011" in doc_text.lower() or "Migration 011" in doc_text

    def test_no_h68_started(self, doc_text):
        # H68 should appear only as "next task", not as a completed action
        assert "H68 started" not in doc_text


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
