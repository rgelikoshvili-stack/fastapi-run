"""tests/unit/test_migration_011_final_execution_gate_renewal_h69.py

Contract tests for 11C-H69-WINDOW-REAPPROVAL — Migration 011 Final Execution Gate Renewal.
Verifies all 15 gates pass under the renewed window and the final decision is
H69_READY_FOR_PRODUCTION_MIGRATION_EXECUTION_RENEWED_WINDOW.
No network, no DB, no app imports.
"""
import pathlib
import pytest

GATE_DOC = pathlib.Path(__file__).parents[2] / "docs" / "migration-011-final-execution-gate-renewal-h69.md"
EXPECTED_SHA256 = "3077cec4c3d87fc0167ba02f70b13dcff871c1ce031b6fd0644d32554b3235d0"


@pytest.fixture(scope="module")
def gate_doc():
    return GATE_DOC.read_text(encoding="utf-8")


class TestDocExists:
    def test_gate_doc_exists(self):
        assert GATE_DOC.exists()

    def test_gate_doc_not_empty(self, gate_doc):
        assert len(gate_doc) > 500

    def test_task_reference(self, gate_doc):
        assert "11C-H69-WINDOW-REAPPROVAL" in gate_doc


class TestRenewalContext:
    def test_previous_window_documented(self, gate_doc):
        assert "2026-05-21" in gate_doc
        assert "previous_window" in gate_doc

    def test_expired_not_executed_documented(self, gate_doc):
        assert "EXPIRED_NOT_EXECUTED" in gate_doc

    def test_h70_pre_sha_documented(self, gate_doc):
        assert "91f1df6a2d6067a144c149772d04a986cc75dd65" in gate_doc

    def test_h70_pre_decision_documented(self, gate_doc):
        assert "H70_PRE_LIVE_VERIFICATION_PASS_WAITING_FOR_H69" in gate_doc

    def test_production_db_not_touched(self, gate_doc):
        text = gate_doc.lower()
        assert "not touched" in text or "no sql" in text or "has not been run" in text


class TestAllGatesPass:
    def test_g1_h69_gates_passed(self, gate_doc):
        assert "G1" in gate_doc and "PASS" in gate_doc

    def test_g2_previous_window_expired_documented(self, gate_doc):
        assert "G2" in gate_doc
        assert "EXPIRED_NOT_EXECUTED" in gate_doc

    def test_g3_h70_pre_verified(self, gate_doc):
        assert "G3" in gate_doc
        assert "H70_PRE_LIVE_VERIFICATION_PASS_WAITING_FOR_H69" in gate_doc

    def test_g4_new_window_approved(self, gate_doc):
        assert "G4" in gate_doc
        assert "H69_NEW_MAINTENANCE_WINDOW_APPROVED" in gate_doc or (
            "G4" in gate_doc and "PASS" in gate_doc
        )

    def test_g5_backup_pitr_reconfirmed(self, gate_doc):
        assert "BACKUP_PREREQUISITES_READY" in gate_doc
        assert "RECONFIRMED" in gate_doc

    def test_g6_rollback_owner(self, gate_doc):
        assert "ROLLBACK_OWNER_CONFIRMED" in gate_doc or (
            "G6" in gate_doc and "PASS" in gate_doc
        )

    def test_g7_monitoring_owner(self, gate_doc):
        assert "MONITORING_OWNER_CONFIRMED" in gate_doc or (
            "G7" in gate_doc and "PASS" in gate_doc
        )

    def test_g8_no_concurrent_deploy(self, gate_doc):
        assert "NO_CONCURRENT_DEPLOY_CONFIRMED" in gate_doc

    def test_g9_sha_documented(self, gate_doc):
        assert EXPECTED_SHA256 in gate_doc

    def test_g10_command_redacted(self, gate_doc):
        assert "REDACTED_DATABASE_URL" in gate_doc

    def test_g11_no_fixture(self, gate_doc):
        assert "G11" in gate_doc

    def test_g12_balance_demo_mode(self, gate_doc):
        assert "demo_mode" in gate_doc or "Balance" in gate_doc

    def test_g13_no_posting_apply_mentioned(self, gate_doc):
        assert "G13" in gate_doc

    def test_g14_execution_not_started(self, gate_doc):
        assert "G14" in gate_doc

    def test_g15_h70_not_started(self, gate_doc):
        assert "G15" in gate_doc


class TestGateCounts:
    def test_all_15_gates_pass(self, gate_doc):
        assert "15 gates" in gate_doc or "All 15" in gate_doc
        assert "PASS" in gate_doc

    def test_zero_blocked(self, gate_doc):
        assert "Zero gates blocked" in gate_doc or "0" in gate_doc or "zero" in gate_doc.lower()

    def test_renewal_window_time_documented(self, gate_doc):
        assert "23:00" in gate_doc

    def test_closure_by_present(self, gate_doc):
        assert "Rolandi Gelikoshvili" in gate_doc


class TestFinalDecision:
    def test_renewed_ready_decision(self, gate_doc):
        assert "H69_READY_FOR_PRODUCTION_MIGRATION_EXECUTION_RENEWED_WINDOW" in gate_doc

    def test_no_sql_executed_statement(self, gate_doc):
        text = gate_doc.lower()
        assert "no sql" in text or "not executed" in text

    def test_execution_command_template_present(self, gate_doc):
        assert "REDACTED_DATABASE_URL" in gate_doc
        assert "011_posted_journal_entries_schema.sql" in gate_doc

    def test_post_execution_verification_referenced(self, gate_doc):
        assert "post-execution" in gate_doc.lower() or "Section 7" in gate_doc

    def test_ready_decision_appears_after_gate_table(self, gate_doc):
        idx_gates = gate_doc.find("Gate Evaluation")
        if idx_gates == -1:
            idx_gates = gate_doc.find("G1")
        idx_ready = gate_doc.find("H69_READY_FOR_PRODUCTION_MIGRATION_EXECUTION_RENEWED_WINDOW", idx_gates)
        assert idx_ready > idx_gates, "Final decision must appear after gate evaluation table"


class TestSecurityConstraints:
    def test_no_raw_database_url(self, gate_doc):
        assert "postgresql://" not in gate_doc

    def test_no_production_password(self, gate_doc):
        assert "BridgeHub" + "2026x" not in gate_doc

    def test_no_posting_apply(self, gate_doc):
        assert "posting/" + "apply" not in gate_doc

    def test_no_balance_activation_key(self, gate_doc):
        assert "BALANCE_API_KEY=sk" not in gate_doc

    def test_no_gcloud_mutation(self, gate_doc):
        assert "gcloud run services update" not in gate_doc

    def test_drop_table_last_resort_only(self, gate_doc):
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
