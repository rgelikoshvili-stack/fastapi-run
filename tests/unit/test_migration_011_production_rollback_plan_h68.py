"""tests/unit/test_migration_011_production_rollback_plan_h68.py

Contract tests for 11C-H68 — Migration 011 Production Rollback Plan.
No network, no DB, no app imports.
"""
import pathlib
import re
import pytest

DOC = pathlib.Path(__file__).parents[2] / "docs" / "migration-011-production-rollback-plan-h68.md"


@pytest.fixture(scope="module")
def doc():
    return DOC.read_text(encoding="utf-8")


class TestDocumentExists:
    def test_rollback_plan_doc_exists(self):
        assert DOC.exists()

    def test_rollback_plan_not_empty(self, doc):
        assert len(doc) > 400

    def test_task_reference(self, doc):
        assert "11C-H68" in doc


class TestRollbackPrinciple:
    def test_restore_based_not_drop_based(self, doc):
        assert "restore" in doc.lower() or "PITR" in doc

    def test_default_not_drop_table(self, doc):
        # Default rollback must not be DROP TABLE
        assert "Default rollback does NOT include" in doc or \
               "not DROP" in doc or \
               "restore-based" in doc.lower() or \
               "ROLLBACK_PLAN_READY_RESTORE_BASED" in doc

    def test_pitr_strategy_documented(self, doc):
        assert "PITR" in doc

    def test_feature_flag_strategy_documented(self, doc):
        assert "POSTED_LEDGER_REPORTS_ENABLED" in doc


class TestRollbackLevels:
    def test_level_0_rerun_documented(self, doc):
        assert "Re-run" in doc or "re-run" in doc.lower() or "idempotent" in doc.lower()

    def test_level_1_pitr_restore_documented(self, doc):
        assert "PITR" in doc
        assert "restore" in doc.lower()

    def test_level_2_flag_disable_documented(self, doc):
        assert "POSTED_LEDGER_REPORTS_ENABLED" in doc

    def test_level_3_drop_is_last_resort(self, doc):
        # If DROP TABLE appears anywhere, "last resort" must also appear in the document
        if "DROP TABLE" in doc:
            assert "last resort" in doc.lower() or "LAST RESORT" in doc, \
                "DROP TABLE found in doc but no 'last resort' qualifier present"


class TestRollbackTriggers:
    def test_5xx_trigger_documented(self, doc):
        assert "5xx" in doc

    def test_auth_bypass_trigger_documented(self, doc):
        assert "auth bypass" in doc.lower() or "Auth bypass" in doc

    def test_app_startup_failure_trigger(self, doc):
        assert "fails to start" in doc.lower() or "startup" in doc.lower()

    def test_psql_exit_nonzero_trigger(self, doc):
        assert "non-zero" in doc.lower() or "exit" in doc.lower() or "fails" in doc.lower()


class TestPostRollbackVerification:
    def test_post_rollback_health_check(self, doc):
        assert "/health" in doc

    def test_post_rollback_report_check(self, doc):
        assert "trial-balance" in doc or "POSTED_LEDGER_UNAVAILABLE" in doc

    def test_post_rollback_no_5xx(self, doc):
        assert "5xx" in doc

    def test_cashflow_data_integrity_check(self, doc):
        assert "bank_transactions" in doc or "cashflow" in doc.lower()


class TestRollbackDecision:
    def test_rollback_decision_documented(self, doc):
        assert "ROLLBACK_PLAN_READY_RESTORE_BASED" in doc

    def test_no_rollback_sql_executed_in_h68(self, doc):
        assert "No SQL executed" in doc or "no SQL executed" in doc.lower() or \
               "not executed" in doc.lower() or "No production SQL" in doc


class TestNoForbiddenPatterns:
    def test_no_raw_database_url(self, doc):
        assert "postgresql://" not in doc

    def test_no_production_password(self, doc):
        assert "BridgeHub2026x" not in doc

    def test_no_posting_apply(self, doc):
        assert "posting/" + "apply" not in doc

    def test_no_gcloud_mutation(self, doc):
        assert "gcloud run services update" not in doc

    def test_no_balance_activation(self, doc):
        assert "BALANCE_API_KEY=sk" not in doc

    def test_drop_table_not_default(self, doc):
        # If DROP TABLE appears, "last resort" qualifier must be in the document
        if "DROP TABLE" in doc:
            assert "last resort" in doc.lower() or "LAST RESORT" in doc


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
                assert pat not in stripped, f"Forbidden: {pat!r} in {stripped!r}"
