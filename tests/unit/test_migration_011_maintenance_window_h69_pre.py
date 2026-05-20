"""tests/unit/test_migration_011_maintenance_window_h69_pre.py

Contract tests for 11C-H69-PRE-R2 — Migration 011 Maintenance Window.
No network, no DB, no app imports.
"""
import pathlib
import pytest

DOC = pathlib.Path(__file__).parents[2] / "docs" / "migration-011-maintenance-window-h69-pre.md"


@pytest.fixture(scope="module")
def doc():
    return DOC.read_text(encoding="utf-8")


class TestDocumentExists:
    def test_maintenance_window_doc_exists(self):
        assert DOC.exists()

    def test_maintenance_window_doc_not_empty(self, doc):
        assert len(doc) > 400

    def test_task_reference(self, doc):
        assert "11C-H69-PRE-R2" in doc


class TestWindowFields:
    def test_planned_start_field(self, doc):
        assert "planned_start" in doc

    def test_planned_end_field(self, doc):
        assert "planned_end" in doc

    def test_window_pending(self, doc):
        assert "PENDING" in doc

    def test_timezone_specified(self, doc):
        assert "UTC" in doc or "timezone" in doc.lower() or "time_zone" in doc


class TestPersonnel:
    def test_operator_field(self, doc):
        assert "Operator" in doc or "operator" in doc.lower()

    def test_rollback_owner_field(self, doc):
        assert "Rollback Owner" in doc or "Rollback owner" in doc or "rollback_owner" in doc

    def test_monitoring_owner_field(self, doc):
        assert "Monitoring Owner" in doc or "Monitoring owner" in doc or "monitoring_owner" in doc

    def test_engineering_owner_field(self, doc):
        assert "Engineering Owner" in doc or "engineering owner" in doc.lower()


class TestNoConcurrentDeploy:
    def test_no_concurrent_deploy_documented(self, doc):
        assert "concurrent" in doc.lower() or "No concurrent" in doc

    def test_no_balance_activation_in_window(self, doc):
        assert "Balance.ge" in doc

    def test_no_write_apply_in_window(self, doc):
        assert "write" in doc.lower() or "apply" in doc.lower()


class TestPreExecChecks:
    def test_version_check_listed(self, doc):
        assert "/version" in doc

    def test_health_check_listed(self, doc):
        assert "/health" in doc

    def test_5xx_check_listed(self, doc):
        assert "5xx" in doc

    def test_balance_demo_mode_check(self, doc):
        assert "demo_mode" in doc


class TestRollbackTriggers:
    def test_rollback_triggers_documented(self, doc):
        assert "Rollback" in doc or "rollback" in doc.lower()

    def test_restore_based_rollback(self, doc):
        assert "PITR" in doc or "restore" in doc.lower()

    def test_drop_table_not_default(self, doc):
        if "DROP TABLE" in doc:
            assert "last resort" in doc.lower() or "LAST RESORT" in doc

    def test_5xx_trigger_documented(self, doc):
        assert "5xx" in doc


class TestPostExecMonitoring:
    def test_post_execution_monitoring_documented(self, doc):
        assert "post-execution" in doc.lower() or "Post-Execution" in doc or \
               "after execution" in doc.lower() or "30 minutes" in doc

    def test_monitoring_window_duration(self, doc):
        assert "30" in doc or "minutes" in doc.lower()

    def test_report_endpoint_check_in_monitoring(self, doc):
        assert "trial-balance" in doc or "balance-sheet" in doc or "cashflow" in doc


class TestGateDecision:
    def test_blocked_decision_present(self, doc):
        assert "BLOCKED_MAINTENANCE_WINDOW_MISSING" in doc

    def test_maintenance_window_ready_in_closure(self, doc):
        assert "MAINTENANCE_WINDOW_READY" in doc

    def test_h69_blocked_stated(self, doc):
        assert "H69" in doc
        assert "BLOCKED" in doc or "must NOT begin" in doc

    def test_no_production_sql(self, doc):
        assert "No SQL executed" in doc or "no production SQL" in doc.lower() or \
               "No production DB" in doc


class TestNoForbiddenPatterns:
    def test_no_raw_database_url(self, doc):
        assert "postgresql://" not in doc

    def test_no_production_password(self, doc):
        assert "BridgeHub" + "2026x" not in doc

    def test_no_posting_apply(self, doc):
        assert "posting/" + "apply" not in doc

    def test_no_gcloud_mutation(self, doc):
        assert "gcloud run services update" not in doc

    def test_no_balance_activation(self, doc):
        assert "BALANCE_API_KEY=sk" not in doc


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
