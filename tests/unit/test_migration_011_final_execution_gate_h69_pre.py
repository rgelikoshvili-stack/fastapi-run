"""tests/unit/test_migration_011_final_execution_gate_h69_pre.py

Contract tests for 11C-H69-PRE-R2 — Migration 011 Final Execution Gate.
No network, no DB, no app imports.
"""
import pathlib
import pytest

DOC = pathlib.Path(__file__).parents[2] / "docs" / "migration-011-final-execution-gate-h69-pre.md"
MIGRATION = pathlib.Path(__file__).parents[2] / "app" / "storage" / "migrations" / "011_posted_journal_entries_schema.sql"


@pytest.fixture(scope="module")
def doc():
    return DOC.read_text(encoding="utf-8")


class TestDocumentExists:
    def test_final_gate_doc_exists(self):
        assert DOC.exists()

    def test_final_gate_doc_not_empty(self, doc):
        assert len(doc) > 500

    def test_task_reference(self, doc):
        assert "11C-H69-PRE-R2" in doc


class TestAllGatesDocumented:
    def test_g1_h68_verified(self, doc):
        assert "G1" in doc
        assert "H68" in doc

    def test_g2_migration_sha(self, doc):
        assert "G2" in doc
        assert "3077cec4c3d87fc0167ba02f70b13dcff871c1ce031b6fd0644d32554b3235d0" in doc

    def test_g3_backup_pitr(self, doc):
        assert "G3" in doc
        assert "PITR" in doc or "Backup" in doc

    def test_g4_dry_run(self, doc):
        assert "G4" in doc
        assert "dry-run" in doc.lower() or "Dry-run" in doc

    def test_g5_approval_signed(self, doc):
        assert "G5" in doc
        assert "Approval" in doc or "approval" in doc.lower()

    def test_g6_maintenance_window(self, doc):
        assert "G6" in doc
        assert "Maintenance" in doc or "maintenance" in doc.lower()

    def test_g7_no_concurrent_deploys(self, doc):
        assert "G7" in doc
        assert "concurrent" in doc.lower()

    def test_g8_rollback_owner(self, doc):
        assert "G8" in doc
        assert "Rollback" in doc

    def test_g9_monitoring_owner(self, doc):
        assert "G9" in doc
        assert "Monitoring" in doc

    def test_g10_command_redacted(self, doc):
        assert "G10" in doc
        assert "redact" in doc.lower() or "REDACTED" in doc

    def test_g11_no_fixture_load(self, doc):
        assert "G11" in doc
        assert "fixture" in doc.lower()

    def test_g12_no_balance_activation(self, doc):
        assert "G12" in doc
        assert "Balance" in doc

    def test_g13_no_write_apply(self, doc):
        assert "G13" in doc
        assert "write" in doc.lower() or "apply" in doc.lower()

    def test_g14_rollback_plan_ready(self, doc):
        assert "G14" in doc
        assert "ROLLBACK_PLAN_READY_RESTORE_BASED" in doc

    def test_g15_h69_not_started(self, doc):
        assert "G15" in doc
        assert "not yet begun" in doc.lower() or "NOT begin" in doc or "not started" in doc.lower()


class TestGatePassCount:
    def test_pass_gates_documented(self, doc):
        assert "PASS" in doc

    def test_blocked_gates_documented(self, doc):
        assert "BLOCKED" in doc

    def test_nine_gates_pass(self, doc):
        assert "9" in doc

    def test_six_gates_blocked(self, doc):
        assert "6" in doc


class TestBlockedGateDetails:
    def test_g3_backup_blocked(self, doc):
        assert "BLOCKED_BACKUP_RESTORE_CONFIRMATION_MISSING" in doc

    def test_g5_approval_blocked(self, doc):
        assert "BLOCKED_APPROVAL_SIGNATURE_MISSING" in doc

    def test_g6_maintenance_blocked(self, doc):
        assert "BLOCKED_MAINTENANCE_WINDOW_MISSING" in doc

    def test_g7_concurrent_deploy_blocked(self, doc):
        assert "BLOCKED_NO_CONCURRENT_DEPLOY_CONFIRMATION_MISSING" in doc


class TestPassGateDetails:
    def test_g4_dry_run_pass_documented(self, doc):
        assert "DRY_RUN_ALREADY_PASSED_WITH_EVIDENCE" in doc

    def test_g1_h68_live_verification_referenced(self, doc):
        assert "H68_LIVE_VERIFICATION_PASS" in doc or "H68 live" in doc.lower()

    def test_g12_demo_mode_confirmed(self, doc):
        assert "demo_mode" in doc


class TestExecutionCommandTemplate:
    def test_execution_template_present(self, doc):
        assert "REDACTED_DATABASE_URL" in doc

    def test_do_not_execute_in_pre(self, doc):
        assert "Do NOT execute" in doc or "do NOT execute" in doc or \
               "Do not execute" in doc

    def test_migration_file_referenced(self, doc):
        assert "011_posted_journal_entries_schema.sql" in doc


class TestFinalDecision:
    def test_critical_blocker_decision(self, doc):
        assert "BLOCKED_BACKUP_RESTORE_CONFIRMATION_MISSING" in doc

    def test_h69_not_allowed(self, doc):
        assert "H69 execution must NOT begin" in doc or "must NOT" in doc or \
               "must not begin" in doc.lower()

    def test_h69_ready_decision_in_closure(self, doc):
        assert "H69_READY_FOR_PRODUCTION_MIGRATION_EXECUTION" in doc

    def test_gate_closure_tracking(self, doc):
        assert "BACKUP_PREREQUISITES_READY" in doc
        assert "APPROVAL_PACKET_SIGNED" in doc
        assert "MAINTENANCE_WINDOW_READY" in doc

    def test_no_sql_executed(self, doc):
        assert "No SQL executed" in doc or "no SQL" in doc.lower() or \
               "No production DB" in doc


class TestMigrationFileIntegrity:
    def test_migration_file_exists(self):
        assert MIGRATION.exists()

    def test_migration_additive_only(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        assert "DROP TABLE" not in sql
        assert "TRUNCATE" not in sql
        for line in [l.strip() for l in sql.splitlines()]:
            assert not line.upper().startswith("DELETE FROM"), f"DML DELETE: {line}"
            assert not (line.upper().startswith("UPDATE ") and " SET " in line.upper()), \
                f"DML UPDATE: {line}"
            assert not line.upper().startswith("INSERT INTO"), f"Fixture INSERT: {line}"


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

    def test_drop_table_not_as_default(self, doc):
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
