"""
Tests for docs/local-report-snapshot-capture-h53.md (H53).

H53 captures local report snapshots from the approved synthetic fixture loaded
into a disposable local Docker PostgreSQL container (127.0.0.1:55433).
No production DB. No Cloud Run mutation. No feature flag.
"""

import os
import pytest

DOC_PATH = "docs/local-report-snapshot-capture-h53.md"

EXPECTED_FIXTURE_SHA256 = "1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299"
EXPECTED_MIGRATION_SHA256 = "F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA"


def _read_doc():
    with open(DOC_PATH, "r", encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_h53_capture_doc_exists(self):
        assert os.path.exists(DOC_PATH), f"Expected {DOC_PATH} to exist"

    def test_h53_capture_doc_not_empty(self):
        text = _read_doc()
        assert len(text) > 500


class TestApprovalReference:
    def test_h53_approval_reference_documented(self):
        text = _read_doc()
        assert "APPROVAL-2026-H50-001" in text

    def test_h53_approval_scope_documented(self):
        text = _read_doc()
        assert "local_docker_postgres_dry_run_only" in text

    def test_h53_approved_by_documented(self):
        text = _read_doc()
        assert "ROLANDI GELIKOSHVILI" in text

    def test_h53_expires_at_documented(self):
        text = _read_doc()
        assert "2026-05-25" in text

    def test_h53_approval_valid_documented(self):
        text = _read_doc()
        assert "valid" in text.lower() or "not expired" in text.lower() or "OWNER_APPROVAL_SIGNED" in text


class TestLocalDbTarget:
    def test_h53_local_db_target_documented(self):
        text = _read_doc()
        assert "127.0.0.1" in text
        assert "55433" in text

    def test_h53_container_name_documented(self):
        text = _read_doc()
        assert "bridge-hub-h53-postgres" in text

    def test_h53_volume_name_documented(self):
        text = _read_doc()
        assert "bridge-hub-h53-pgdata" in text

    def test_h53_no_production_db_connection(self):
        text = _read_doc()
        assert "NOT connected" in text or "no production" in text.lower()

    def test_h53_no_cloud_sql(self):
        text = _read_doc()
        assert "Cloud SQL" in text
        assert "NOT connected" in text or "not connected" in text.lower()


class TestMigrationAndFixtureHashes:
    def test_h53_migration_and_fixture_hashes_documented(self):
        text = _read_doc()
        assert EXPECTED_FIXTURE_SHA256 in text
        assert EXPECTED_MIGRATION_SHA256 in text

    def test_h53_fixture_path_documented(self):
        text = _read_doc()
        assert "synthetic_posted_ledger_fixture_pack.json" in text

    def test_h53_migration_path_documented(self):
        text = _read_doc()
        assert "011_posted_journal_entries_schema.sql" in text

    def test_h53_rows_loaded_documented(self):
        text = _read_doc()
        assert "52" in text
        assert "15" in text
        assert "33" in text
        assert "4" in text


class TestSnapshotCaptureMethod:
    def test_h53_snapshot_capture_method_documented(self):
        text = _read_doc()
        assert "capture_h53_local_report_snapshots" in text or "H53_LOCAL_DRY_RUN" in text

    def test_h53_guard_var_documented(self):
        text = _read_doc()
        assert "H53_LOCAL_DRY_RUN" in text

    def test_h53_localhost_guard_documented(self):
        text = _read_doc()
        assert "127.0.0.1:55433" in text

    def test_h53_sha256_verify_documented(self):
        text = _read_doc()
        assert "SHA-256" in text or "sha256" in text.lower()

    def test_h53_feature_flag_off_documented(self):
        text = _read_doc()
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text


class TestTrialBalanceSnapshot:
    def test_h53_trial_balance_snapshot_documented(self):
        text = _read_doc()
        assert "Trial Balance" in text or "trial_balance" in text

    def test_h53_trial_balance_accounts_documented(self):
        text = _read_doc()
        assert "1010" in text
        assert "3000" in text
        assert "4100" in text

    def test_h53_trial_balance_totals_documented(self):
        text = _read_doc()
        assert "14,480.00" in text

    def test_h53_total_volume_documented(self):
        text = _read_doc()
        assert "23,945.00" in text


class TestTenantSummary:
    def test_h53_tenant_summary_documented(self):
        text = _read_doc()
        assert "tenant_alpha" in text
        assert "tenant_beta" in text

    def test_h53_tenant_alpha_balance_documented(self):
        text = _read_doc()
        assert "24,470.00" in text

    def test_h53_tenant_beta_documented(self):
        text = _read_doc()
        assert "9,999.00" in text


class TestBalanceCheck:
    def test_h53_balance_check_documented(self):
        text = _read_doc()
        assert "34,469.00" in text
        assert "balanced" in text.lower() or "True" in text

    def test_h53_balance_difference_zero(self):
        text = _read_doc()
        assert "0.00" in text

    def test_h53_double_entry_invariant(self):
        text = _read_doc()
        assert "balanced" in text.lower()


class TestCaptureDecision:
    def test_h53_capture_decision_documented(self):
        text = _read_doc()
        assert "SNAPSHOT_CAPTURE_COMPLETE" in text or "Capture Decision" in text

    def test_h53_no_production_scope_in_capture(self):
        text = _read_doc()
        assert "NOT" in text or "not" in text.lower()
        assert "production" in text.lower()


class TestNoProductionOrCloudRunScope:
    def test_no_production_or_cloud_run_scope(self):
        text = _read_doc()
        assert "production DB" in text.lower() or "production db" in text.lower() or "NOT connected" in text
        assert "Cloud Run" in text or "cloud_run" in text.lower()

    def test_no_feature_flag_enabled(self):
        text = _read_doc()
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text
        assert "not set" in text.lower() or "OFF" in text or "not enabled" in text.lower()

    def test_no_balance_ge_activation(self):
        text = _read_doc()
        assert "Balance.ge" in text or "balance_ge" in text.lower() or "demo_mode" in text.lower()

    def test_safety_notes_documented(self):
        text = _read_doc()
        assert "Safety" in text or "safety" in text.lower()
        assert "synthetic" in text.lower()


class TestNoForbiddenImports:
    def test_no_db_docker_execution_imports(self):
        with open(__file__, "r", encoding="utf-8") as f:
            lines = f.readlines()
        _forbidden = [
            "import " + "psycopg",
            "import " + "sqlalchemy",
            "import " + "requests",
            "import " + "httpx",
            "import " + "socket",
            "import " + "subprocess",
            "from " + "app.",
            "from docker" + " import",
        ]
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for imp in _forbidden:
                assert imp not in stripped, f"Forbidden import: {stripped}"
