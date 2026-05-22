"""tests/unit/test_migration_011_maintenance_window_renewal_h69.py

Contract tests for 11C-H69-WINDOW-REAPPROVAL — Migration 011 Maintenance Window Renewal.
Verifies the renewal doc records the expired window, H70-PRE dependency, new window,
personnel, backup/PITR reconfirmation, and approval packet reference.
No network, no DB, no app imports.
"""
import pathlib
import pytest

RENEWAL_DOC = pathlib.Path(__file__).parents[2] / "docs" / "migration-011-maintenance-window-renewal-h69.md"


@pytest.fixture(scope="module")
def renewal_doc():
    return RENEWAL_DOC.read_text(encoding="utf-8")


class TestDocExists:
    def test_renewal_doc_exists(self):
        assert RENEWAL_DOC.exists()

    def test_renewal_doc_not_empty(self, renewal_doc):
        assert len(renewal_doc) > 500

    def test_task_reference(self, renewal_doc):
        assert "11C-H69-WINDOW-REAPPROVAL" in renewal_doc


class TestPreviousWindowExpired:
    def test_previous_window_documented(self, renewal_doc):
        assert "2026-05-21" in renewal_doc
        assert "previous_window" in renewal_doc

    def test_expired_not_executed(self, renewal_doc):
        assert "EXPIRED_NOT_EXECUTED" in renewal_doc

    def test_no_execution_occurred(self, renewal_doc):
        text = renewal_doc.lower()
        assert "not touched" in text or "not executed" in text or "no sql" in text

    def test_previous_window_time_documented(self, renewal_doc):
        assert "23:00" in renewal_doc

    def test_production_db_not_touched(self, renewal_doc):
        text = renewal_doc.lower()
        assert "production db not touched" in text or "not touched" in text or "no sql" in text


class TestH70PreDependency:
    def test_h70_pre_decision_recorded(self, renewal_doc):
        assert "H70_PRE_LIVE_VERIFICATION_PASS_WAITING_FOR_H69" in renewal_doc

    def test_h70_pre_sha_recorded(self, renewal_doc):
        assert "91f1df6a2d6067a144c149772d04a986cc75dd65" in renewal_doc

    def test_h70_implementation_not_started(self, renewal_doc):
        text = renewal_doc.lower()
        assert "h70 implementation" in text or "posted_ledger_writes_enabled" in renewal_doc


class TestNewWindow:
    def test_new_window_start_documented(self, renewal_doc):
        assert "new_window_start_utc" in renewal_doc

    def test_new_window_end_documented(self, renewal_doc):
        assert "new_window_end_utc" in renewal_doc

    def test_new_window_is_future_of_expired(self, renewal_doc):
        assert "2026-05-23" in renewal_doc or "2026-05-24" in renewal_doc or "2026-05-25" in renewal_doc

    def test_new_window_approved_decision(self, renewal_doc):
        assert "H69_NEW_MAINTENANCE_WINDOW_APPROVED" in renewal_doc


class TestPersonnel:
    def test_operator_confirmed(self, renewal_doc):
        assert "Operator" in renewal_doc
        idx = renewal_doc.rfind("Operator")
        window = renewal_doc[idx:idx+200]
        assert "CONFIRMED" in window or "Rolandi" in window

    def test_rollback_owner_confirmed(self, renewal_doc):
        assert "Rollback Owner" in renewal_doc
        idx = renewal_doc.rfind("Rollback Owner")
        window = renewal_doc[idx:idx+200]
        assert "CONFIRMED" in window or "Rolandi" in window

    def test_monitoring_owner_confirmed(self, renewal_doc):
        assert "Monitoring Owner" in renewal_doc
        idx = renewal_doc.rfind("Monitoring Owner")
        window = renewal_doc[idx:idx+200]
        assert "CONFIRMED" in window or "Rolandi" in window

    def test_operator_named(self, renewal_doc):
        assert "Rolandi Gelikoshvili" in renewal_doc

    def test_email_present(self, renewal_doc):
        assert "r.gelikoshvili@gmail.com" in renewal_doc


class TestBackupPitrReconfirmed:
    def test_backup_reconfirmation_present(self, renewal_doc):
        assert "BACKUP_PREREQUISITES_READY" in renewal_doc

    def test_reconfirmed_marker(self, renewal_doc):
        assert "RECONFIRMED" in renewal_doc

    def test_pitr_mentioned(self, renewal_doc):
        assert "PITR" in renewal_doc

    def test_restore_point_available(self, renewal_doc):
        text = renewal_doc.lower()
        assert "restore point" in text or "restore_point" in renewal_doc


class TestNoConcurrentDeploy:
    def test_no_concurrent_deploy_confirmed(self, renewal_doc):
        assert "NO_CONCURRENT_DEPLOY_CONFIRMED" in renewal_doc
        assert "concurrent" in renewal_doc.lower()


class TestApprovalReference:
    def test_approval_id_referenced(self, renewal_doc):
        assert "APPROVAL-2026-H68-001" in renewal_doc

    def test_scope_documented(self, renewal_doc):
        assert "production_migration_011_execution_only" in renewal_doc

    def test_renewal_approval_timestamp(self, renewal_doc):
        assert "renewal_approval_timestamp" in renewal_doc or "2026-05-23" in renewal_doc


class TestSecurityConstraints:
    def test_no_database_url(self, renewal_doc):
        assert "postgresql://" not in renewal_doc

    def test_no_production_password(self, renewal_doc):
        assert "BridgeHub" + "2026x" not in renewal_doc

    def test_no_sql_executed(self, renewal_doc):
        text = renewal_doc.lower()
        assert "no sql" in text or "not executed" in text or "no production" in text

    def test_no_balance_activation_key(self, renewal_doc):
        assert "BALANCE_API_KEY=sk" not in renewal_doc

    def test_no_posting_apply(self, renewal_doc):
        assert "posting/" + "apply" not in renewal_doc

    def test_redacted_command_if_psql_present(self, renewal_doc):
        if "psql" in renewal_doc:
            assert "REDACTED_DATABASE_URL" in renewal_doc

    def test_no_gcloud_mutation(self, renewal_doc):
        assert "gcloud run services update" not in renewal_doc


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
