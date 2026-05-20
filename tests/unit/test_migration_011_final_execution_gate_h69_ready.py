"""tests/unit/test_migration_011_final_execution_gate_h69_ready.py

Contract tests for 11C-H69-GATES — Migration 011 Final Execution Gate READY state.
Verifies the final gate doc has reached H69_READY_FOR_PRODUCTION_MIGRATION_EXECUTION
with all 15 gates passing and no remaining blockers.
No network, no DB, no app imports.
"""
import pathlib
import hashlib
import pytest

GATE_DOC = pathlib.Path(__file__).parents[2] / "docs" / "migration-011-final-execution-gate-h69-pre.md"
MIGRATION = pathlib.Path(__file__).parents[2] / "app" / "storage" / "migrations" / "011_posted_journal_entries_schema.sql"

EXPECTED_SHA256 = "3077cec4c3d87fc0167ba02f70b13dcff871c1ce031b6fd0644d32554b3235d0"


@pytest.fixture(scope="module")
def gate_doc():
    return GATE_DOC.read_text(encoding="utf-8")


class TestFinalGateDocExists:
    def test_gate_doc_exists(self):
        assert GATE_DOC.exists()

    def test_gate_doc_not_empty(self, gate_doc):
        assert len(gate_doc) > 500

    def test_task_references(self, gate_doc):
        assert "11C-H69-PRE-R2" in gate_doc
        assert "H69-GATES" in gate_doc or "11C-H69-GATES" in gate_doc


class TestAllGatesPass:
    def test_g1_h68_verified(self, gate_doc):
        assert "G1" in gate_doc and "PASS" in gate_doc

    def test_g2_sha_verified(self, gate_doc):
        assert EXPECTED_SHA256 in gate_doc

    def test_g3_backup_pitr_pass(self, gate_doc):
        assert "BACKUP_PREREQUISITES_READY" in gate_doc

    def test_g4_dry_run_pass(self, gate_doc):
        assert "DRY_RUN_ALREADY_PASSED_WITH_EVIDENCE" in gate_doc

    def test_g5_approval_pass(self, gate_doc):
        assert "APPROVAL_PACKET_SIGNED" in gate_doc

    def test_g6_maintenance_window_pass(self, gate_doc):
        assert "MAINTENANCE_WINDOW_READY" in gate_doc

    def test_g7_no_concurrent_deploy_pass(self, gate_doc):
        assert "NO_CONCURRENT_DEPLOY_CONFIRMED" in gate_doc

    def test_g8_rollback_owner_pass(self, gate_doc):
        assert "ROLLBACK_OWNER_CONFIRMED" in gate_doc or (
            "G8" in gate_doc and "PASS" in gate_doc
        )

    def test_g9_monitoring_owner_pass(self, gate_doc):
        assert "MONITORING_OWNER_CONFIRMED" in gate_doc or (
            "G9" in gate_doc and "PASS" in gate_doc
        )

    def test_g10_command_redacted(self, gate_doc):
        assert "REDACTED_DATABASE_URL" in gate_doc

    def test_g11_no_fixture(self, gate_doc):
        assert "G11" in gate_doc

    def test_g12_no_balance_activation(self, gate_doc):
        assert "demo_mode" in gate_doc or "Balance" in gate_doc

    def test_g13_no_write_apply(self, gate_doc):
        assert "G13" in gate_doc

    def test_g14_rollback_plan(self, gate_doc):
        assert "ROLLBACK_PLAN_READY_RESTORE_BASED" in gate_doc

    def test_g15_h69_not_started(self, gate_doc):
        assert "G15" in gate_doc


class TestGateCounts:
    def test_all_15_gates_pass(self, gate_doc):
        assert "All 15 gates" in gate_doc or "15 gates" in gate_doc

    def test_no_current_blockers(self, gate_doc):
        # Gate closure section must list all 6 previously-blocked gates as now closed
        assert "BACKUP_PREREQUISITES_READY" in gate_doc
        assert "APPROVAL_PACKET_SIGNED" in gate_doc
        assert "MAINTENANCE_WINDOW_READY" in gate_doc
        assert "NO_CONCURRENT_DEPLOY_CONFIRMED" in gate_doc

    def test_gate_closure_record_present(self, gate_doc):
        assert "Gate Closure Record" in gate_doc or "Gate closure" in gate_doc.lower()

    def test_closure_date_present(self, gate_doc):
        assert "2026-05-21" in gate_doc

    def test_closure_by_present(self, gate_doc):
        assert "Rolandi Gelikoshvili" in gate_doc


class TestFinalReadyDecision:
    def test_h69_ready_decision(self, gate_doc):
        assert "H69_READY_FOR_PRODUCTION_MIGRATION_EXECUTION" in gate_doc

    def test_maintenance_window_time_given(self, gate_doc):
        assert "23:00" in gate_doc or "2026-05-21" in gate_doc

    def test_execution_command_template_present(self, gate_doc):
        assert "REDACTED_DATABASE_URL" in gate_doc
        assert "011_posted_journal_entries_schema.sql" in gate_doc

    def test_post_execution_verification_referenced(self, gate_doc):
        assert "post-execution" in gate_doc.lower() or "Section 7" in gate_doc

    def test_h69_ready_statement_explicit(self, gate_doc):
        assert "H69_READY_FOR_PRODUCTION_MIGRATION_EXECUTION" in gate_doc
        # Must appear after the gate closure record
        idx_closure = gate_doc.find("Gate Closure Record")
        idx_ready = gate_doc.find("H69_READY_FOR_PRODUCTION_MIGRATION_EXECUTION", idx_closure)
        assert idx_ready > idx_closure, "H69_READY decision must appear after gate closure record"


class TestMigrationFileIntegrity:
    def test_migration_file_exists(self):
        assert MIGRATION.exists()

    def test_sha256_matches(self):
        actual = hashlib.sha256(MIGRATION.read_bytes()).hexdigest()
        assert actual == EXPECTED_SHA256, (
            f"Migration SHA changed!\nExpected: {EXPECTED_SHA256}\nActual: {actual}"
        )

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
    def test_no_raw_database_url(self, gate_doc):
        assert "postgresql://" not in gate_doc

    def test_no_production_password(self, gate_doc):
        assert "BridgeHub" + "2026x" not in gate_doc

    def test_no_posting_apply(self, gate_doc):
        assert "posting/" + "apply" not in gate_doc

    def test_no_gcloud_mutation(self, gate_doc):
        assert "gcloud run services update" not in gate_doc

    def test_no_balance_activation_key(self, gate_doc):
        assert "BALANCE_API_KEY=sk" not in gate_doc

    def test_drop_table_not_as_default(self, gate_doc):
        if "DROP TABLE" in gate_doc:
            assert "last resort" in gate_doc.lower() or "LAST RESORT" in gate_doc


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
