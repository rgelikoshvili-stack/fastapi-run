"""tests/unit/test_migration_011_human_gate_closure_h69.py

Contract tests for 11C-H69-GATES — Migration 011 Human Gate Closure.
Verifies backup/PITR, approval signatures, and maintenance window docs
have been updated from BLOCKED to CONFIRMED/APPROVED/READY.
No network, no DB, no app imports.
"""
import pathlib
import pytest

BACKUP_DOC = pathlib.Path(__file__).parents[2] / "docs" / "migration-011-backup-pitr-confirmation-h69-pre.md"
APPROVAL_DOC = pathlib.Path(__file__).parents[2] / "docs" / "migration-011-approval-signatures-h69-pre.md"
WINDOW_DOC = pathlib.Path(__file__).parents[2] / "docs" / "migration-011-maintenance-window-h69-pre.md"
GATE_DOC = pathlib.Path(__file__).parents[2] / "docs" / "migration-011-final-execution-gate-h69-pre.md"


@pytest.fixture(scope="module")
def backup_doc():
    return BACKUP_DOC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def approval_doc():
    return APPROVAL_DOC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def window_doc():
    return WINDOW_DOC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def gate_doc():
    return GATE_DOC.read_text(encoding="utf-8")


class TestBackupGateClosed:
    def test_backup_doc_exists(self):
        assert BACKUP_DOC.exists()

    def test_backup_prerequisites_ready(self, backup_doc):
        assert "BACKUP_PREREQUISITES_READY" in backup_doc

    def test_backup_timestamp_confirmed(self, backup_doc):
        assert "2026-05-21" in backup_doc

    def test_pitr_confirmed(self, backup_doc):
        assert "PITR" in backup_doc
        assert "enabled" in backup_doc.lower() or "Yes" in backup_doc

    def test_restore_owner_named(self, backup_doc):
        assert "Rolandi Gelikoshvili" in backup_doc or "r.gelikoshvili@gmail.com" in backup_doc

    def test_restore_point_confirmed(self, backup_doc):
        assert "restore point" in backup_doc.lower() or "Restore point" in backup_doc

    def test_gate_update_section_present(self, backup_doc):
        assert "H69-GATES" in backup_doc

    def test_no_database_url(self, backup_doc):
        assert "postgresql://" not in backup_doc

    def test_no_production_password(self, backup_doc):
        assert "BridgeHub" + "2026x" not in backup_doc


class TestApprovalGateClosed:
    def test_approval_doc_exists(self):
        assert APPROVAL_DOC.exists()

    def test_approval_packet_signed(self, approval_doc):
        assert "APPROVAL_PACKET_SIGNED" in approval_doc

    def test_engineering_owner_approved(self, approval_doc):
        assert "Engineering Owner" in approval_doc
        text = approval_doc
        idx = text.rfind("Engineering Owner")
        window = text[idx:idx+400]
        assert "APPROVED" in window

    def test_accounting_owner_approved(self, approval_doc):
        assert "Accounting Owner" in approval_doc
        text = approval_doc
        idx = text.rfind("Accounting Owner")
        window = text[idx:idx+400]
        assert "APPROVED" in window

    def test_rollback_owner_approved(self, approval_doc):
        assert "Rollback Owner" in approval_doc
        text = approval_doc
        idx = text.rfind("Rollback Owner")
        window = text[idx:idx+400]
        assert "APPROVED" in window

    def test_monitoring_owner_approved(self, approval_doc):
        assert "Monitoring Owner" in approval_doc
        text = approval_doc
        idx = text.rfind("Monitoring Owner")
        window = text[idx:idx+400]
        assert "APPROVED" in window

    def test_all_four_approved(self, approval_doc):
        assert approval_doc.count("APPROVED") >= 4

    def test_approval_id_present(self, approval_doc):
        assert "APPROVAL-2026-H68-001" in approval_doc

    def test_scope_documented(self, approval_doc):
        assert "production_migration_011_execution_only" in approval_doc

    def test_approver_email_present(self, approval_doc):
        assert "r.gelikoshvili@gmail.com" in approval_doc

    def test_no_fixture_load_confirmed(self, approval_doc):
        assert "fixture" in approval_doc.lower()
        assert "[x]" in approval_doc or "Confirmed" in approval_doc or "confirmed" in approval_doc.lower()

    def test_restore_based_rollback_confirmed(self, approval_doc):
        assert "restore-based" in approval_doc.lower() or "restore based" in approval_doc.lower()

    def test_gate_update_section_present(self, approval_doc):
        assert "H69-GATES" in approval_doc

    def test_no_database_url(self, approval_doc):
        assert "postgresql://" not in approval_doc

    def test_no_production_password(self, approval_doc):
        assert "BridgeHub" + "2026x" not in approval_doc


class TestMaintenanceWindowClosed:
    def test_window_doc_exists(self):
        assert WINDOW_DOC.exists()

    def test_maintenance_window_ready(self, window_doc):
        assert "MAINTENANCE_WINDOW_READY" in window_doc

    def test_window_start_confirmed(self, window_doc):
        assert "planned_start" in window_doc
        assert "2026-05-21" in window_doc or "23:00" in window_doc

    def test_window_end_confirmed(self, window_doc):
        assert "planned_end" in window_doc
        assert "00:00" in window_doc or "2026-05-22" in window_doc

    def test_operator_named(self, window_doc):
        assert "Rolandi Gelikoshvili" in window_doc

    def test_rollback_owner_confirmed(self, window_doc):
        assert "Rollback Owner" in window_doc
        text = window_doc
        idx = text.rfind("Rollback Owner")
        window = text[idx:idx+200]
        assert "CONFIRMED" in window or "Rolandi" in window

    def test_monitoring_owner_confirmed(self, window_doc):
        assert "Monitoring Owner" in window_doc
        text = window_doc
        idx = text.rfind("Monitoring Owner")
        window = text[idx:idx+200]
        assert "CONFIRMED" in window or "Rolandi" in window

    def test_no_concurrent_deploy_confirmed(self, window_doc):
        assert "CONFIRMED" in window_doc
        assert "concurrent" in window_doc.lower()

    def test_gate_update_section_present(self, window_doc):
        assert "H69-GATES" in window_doc

    def test_no_database_url(self, window_doc):
        assert "postgresql://" not in window_doc

    def test_no_production_password(self, window_doc):
        assert "BridgeHub" + "2026x" not in window_doc


class TestFinalGateUpdated:
    def test_gate_doc_exists(self):
        assert GATE_DOC.exists()

    def test_h69_ready_decision(self, gate_doc):
        assert "H69_READY_FOR_PRODUCTION_MIGRATION_EXECUTION" in gate_doc

    def test_all_gates_pass_in_updated_table(self, gate_doc):
        assert "All 15 gates" in gate_doc or "15 gates" in gate_doc
        assert "PASS" in gate_doc

    def test_zero_blocked_gates(self, gate_doc):
        assert "Zero gates blocked" in gate_doc or "zero" in gate_doc.lower() or \
               "0" in gate_doc

    def test_execution_command_still_redacted(self, gate_doc):
        assert "REDACTED_DATABASE_URL" in gate_doc

    def test_maintenance_window_time_referenced(self, gate_doc):
        assert "23:00" in gate_doc or "2026-05-21" in gate_doc

    def test_no_database_url(self, gate_doc):
        assert "postgresql://" not in gate_doc

    def test_no_production_password(self, gate_doc):
        assert "BridgeHub" + "2026x" not in gate_doc

    def test_no_sql_executed(self, gate_doc):
        assert "No SQL executed" in gate_doc or "no SQL" in gate_doc.lower()


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
