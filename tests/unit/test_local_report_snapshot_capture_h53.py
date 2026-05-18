"""
Tests for docs/local-report-snapshot-capture-h53.md (H53).
No Docker, no DB, no network — pure doc content verification.
"""
import os
import pytest

DOC_PATH = "docs/local-report-snapshot-capture-h53.md"
FIXTURE_SHA = "1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299"
MIGRATION_SHA = "F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA"


def _read():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_h53_capture_doc_exists(self):
        assert os.path.exists(DOC_PATH)

    def test_h53_capture_doc_not_empty(self):
        assert len(_read()) > 500


class TestApprovalReference:
    def test_approval_id_documented(self):
        assert "APPROVAL-2026-H50-001" in _read()

    def test_approved_by_documented(self):
        assert "ROLANDI GELIKOSHVILI" in _read()

    def test_expires_at_documented(self):
        assert "2026-05-25" in _read()

    def test_scope_documented(self):
        assert "local_docker_postgres_dry_run_only" in _read()


class TestLocalDbTarget:
    def test_h53_local_db_target_documented(self):
        text = _read()
        assert "127.0.0.1" in text
        assert "55433" in text

    def test_container_name_documented(self):
        assert "bridge-hub-h53-postgres" in _read()

    def test_volume_name_documented(self):
        assert "bridge-hub-h53-pgdata" in _read()

    def test_no_production_db_connection(self):
        assert "NOT connected" in _read()

    def test_no_cloud_sql(self):
        text = _read()
        assert "Cloud SQL" in text
        assert "NOT connected" in text


class TestMigrationAndFixtureHashes:
    def test_fixture_sha_documented(self):
        assert FIXTURE_SHA in _read()

    def test_migration_sha_documented(self):
        assert MIGRATION_SHA in _read()

    def test_fixture_path_documented(self):
        assert "synthetic_posted_ledger_fixture_pack.json" in _read()

    def test_migration_path_documented(self):
        assert "011_posted_journal_entries_schema.sql" in _read()

    def test_rows_documented(self):
        text = _read()
        assert "52" in text
        assert "15" in text
        assert "33" in text


class TestSnapshotCaptureMethod:
    def test_guard_var_documented(self):
        assert "H53_LOCAL_DRY_RUN" in _read()

    def test_localhost_guard_documented(self):
        assert "127.0.0.1:55433" in _read()

    def test_sha256_verify_documented(self):
        assert "SHA-256" in _read()

    def test_feature_flag_off_documented(self):
        assert "POSTED_LEDGER_REPORTS_ENABLED" in _read()


class TestTrialBalanceSnapshot:
    def test_trial_balance_documented(self):
        assert "Trial Balance" in _read()

    def test_trial_balance_accounts(self):
        text = _read()
        assert "1010" in text
        assert "3000" in text
        assert "4100" in text

    def test_trial_balance_column_total(self):
        assert "14,480.00" in _read()

    def test_standard_net_volume(self):
        assert "23,945.00" in _read()

    def test_full_db_balance(self):
        assert "34,469.00" in _read()


class TestTenantSummary:
    def test_tenant_alpha_documented(self):
        assert "tenant_alpha" in _read()

    def test_tenant_beta_documented(self):
        assert "tenant_beta" in _read()

    def test_tenant_isolation_note(self):
        text = _read()
        assert "9,999.00" in text


class TestCaptureDecision:
    def test_capture_decision_documented(self):
        assert "SNAPSHOT_CAPTURE_COMPLETE" in _read()

    def test_pl_documented(self):
        text = _read()
        assert "2,300.00" in text
        assert "3,525.00" in text
        assert "-1,225.00" in text

    def test_balance_sheet_documented(self):
        text = _read()
        assert "10,955.00" in text
        assert "2,180.00" in text


class TestSafetyConfirmation:
    def test_no_production_scope(self):
        text = _read()
        assert "production" in text.lower()
        assert "NOT" in text

    def test_no_feature_flag_enabled(self):
        text = _read()
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text
        assert "not set" in text.lower() or "OFF" in text


class TestNoForbiddenImports:
    def test_no_forbidden_imports(self):
        with open(__file__, encoding="utf-8") as f:
            lines = f.readlines()
        forbidden = [
            "import " + "psycopg", "import " + "sqlalchemy",
            "import " + "requests", "import " + "httpx",
            "import " + "socket", "import " + "subprocess",
            "from " + "app.", "from docker" + " import",
        ]
        for line in lines:
            s = line.strip()
            if s.startswith("#"): continue
            for imp in forbidden:
                assert imp not in s, f"Forbidden import: {s}"
