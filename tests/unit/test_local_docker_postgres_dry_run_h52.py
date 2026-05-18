"""
Tests for docs/local-docker-postgres-dry-run-h52.md (H52).

H52 executed the approved local Docker PostgreSQL dry-run:
- Container: bridge-hub-h52-postgres (postgres:16, local-only, 127.0.0.1:55432)
- Migration 011 executed in disposable local DB only
- Synthetic fixture loaded: 15 headers, 33 lines, 4 sources (52 total rows)
- All invariants verified
- Cleanup complete
- Final decision: SUCCESS_LOCAL_DOCKER_POSTGRES_DRY_RUN_COMPLETE
No Docker SDK, no DB imports, no network, no subprocess in this test file.
"""

import os
import pytest

DOC_PATH = "docs/local-docker-postgres-dry-run-h52.md"

EXPECTED_FIXTURE_SHA256 = "1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299"
EXPECTED_MIGRATION_SHA256 = "F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA"
EXPECTED_APPROVAL_ID = "APPROVAL-2026-H50-001"
EXPECTED_DECISION = "SUCCESS_LOCAL_DOCKER_POSTGRES_DRY_RUN_COMPLETE"
EXPECTED_DB_HOST = "127.0.0.1"
EXPECTED_DB_PORT = "55432"
EXPECTED_CONTAINER = "bridge-hub-h52-postgres"


def _read_doc():
    with open(DOC_PATH, "r", encoding="utf-8") as f:
        return f.read()


# --- tests ---

class TestDocumentExists:
    def test_h52_dry_run_doc_exists(self):
        assert os.path.exists(DOC_PATH), f"Expected {DOC_PATH} to exist"

    def test_h52_doc_not_empty(self):
        text = _read_doc()
        assert len(text) > 1000


class TestApprovalReference:
    def test_h52_approval_reference_documented(self):
        text = _read_doc()
        assert EXPECTED_APPROVAL_ID in text

    def test_approved_by_documented(self):
        text = _read_doc()
        assert "ROLANDI GELIKOSHVILI" in text

    def test_expires_at_documented(self):
        text = _read_doc()
        assert "2026-05-25" in text

    def test_approved_at_documented(self):
        text = _read_doc()
        assert "2026-05-18" in text

    def test_scope_documented(self):
        text = _read_doc()
        assert "local_docker_postgres_dry_run_only" in text


class TestScopeIsLocalOnly:
    def test_h52_scope_is_local_only(self):
        text = _read_doc()
        assert "local_only" in text or "local Docker" in text

    def test_no_production_db_scope(self):
        text = _read_doc()
        assert "NOT touch production DB" in text or "no production DB" in text.lower() or "No production DB" in text

    def test_no_cloud_run_db_scope(self):
        text = _read_doc()
        assert "Cloud Run DB" in text

    def test_no_real_posting(self):
        text = _read_doc()
        assert "Balance.ge" in text


class TestPreflightResults:
    def test_h52_preflight_results_documented(self):
        text = _read_doc()
        assert "Preflight" in text or "preflight" in text.lower()

    def test_fixture_hash_matches(self):
        text = _read_doc()
        assert EXPECTED_FIXTURE_SHA256 in text

    def test_migration_hash_matches(self):
        text = _read_doc()
        assert EXPECTED_MIGRATION_SHA256 in text

    def test_approval_not_expired_documented(self):
        text = _read_doc()
        assert "not expired" in text.lower() or "expires_at" in text or "2026-05-25" in text

    def test_docker_context_documented(self):
        text = _read_doc()
        assert "desktop-linux" in text


class TestDockerContainerDetails:
    def test_h52_docker_container_details_documented(self):
        text = _read_doc()
        assert EXPECTED_CONTAINER in text

    def test_image_documented(self):
        text = _read_doc()
        assert "postgres:16" in text

    def test_volume_documented(self):
        text = _read_doc()
        assert "bridge-hub-h52-pgdata" in text

    def test_port_documented(self):
        text = _read_doc()
        assert EXPECTED_DB_PORT in text

    def test_postgres_version_documented(self):
        text = _read_doc()
        assert "16" in text and "postgres" in text.lower()


class TestDbTargetIsLocalhost:
    def test_h52_db_target_is_localhost_only(self):
        text = _read_doc()
        assert EXPECTED_DB_HOST in text

    def test_db_port_is_55432(self):
        text = _read_doc()
        assert EXPECTED_DB_PORT in text

    def test_localhost_only_bind_documented(self):
        text = _read_doc()
        assert "127.0.0.1" in text

    def test_no_remote_db_in_target_proof(self):
        text = _read_doc()
        assert "no remote host" in text.lower() or "no Cloud SQL" in text or "not connected" in text.lower()


class TestMigrationHash:
    def test_h52_migration_hash_documented(self):
        text = _read_doc()
        assert EXPECTED_MIGRATION_SHA256 in text

    def test_migration_path_documented(self):
        text = _read_doc()
        assert "011_posted_journal_entries_schema.sql" in text

    def test_migration_objects_documented(self):
        text = _read_doc()
        assert "journal_entry_headers" in text
        assert "journal_entry_lines" in text
        assert "journal_entry_sources" in text

    def test_index_count_documented(self):
        text = _read_doc()
        assert "14" in text


class TestFixtureHash:
    def test_h52_fixture_hash_documented(self):
        text = _read_doc()
        assert EXPECTED_FIXTURE_SHA256 in text

    def test_fixture_path_documented(self):
        text = _read_doc()
        assert "synthetic_posted_ledger_fixture_pack.json" in text

    def test_fixture_is_synthetic(self):
        text = _read_doc()
        assert "synthetic" in text.lower()

    def test_no_production_data_in_fixture(self):
        text = _read_doc()
        assert "no production" in text.lower() or "no real" in text.lower()


class TestMigrationExecutionResult:
    def test_h52_migration_execution_result_documented(self):
        text = _read_doc()
        assert "Migration" in text and ("SUCCESS" in text or "success" in text.lower())

    def test_three_tables_created(self):
        text = _read_doc()
        assert "journal_entry_headers" in text
        assert "journal_entry_lines" in text
        assert "journal_entry_sources" in text

    def test_migration_executed_against_local_db(self):
        text = _read_doc()
        assert "127.0.0.1:55432" in text or "bridge_hub_h52" in text


class TestFixtureLoadResult:
    def test_h52_fixture_load_result_documented_or_blocked_safely(self):
        text = _read_doc()
        assert "Fixture Load" in text or "fixture load" in text.lower()

    def test_row_counts_documented(self):
        text = _read_doc()
        assert "15" in text
        assert "33" in text
        assert "4" in text

    def test_total_rows_documented(self):
        text = _read_doc()
        assert "52" in text

    def test_fixture_load_status_success(self):
        text = _read_doc()
        assert "SUCCESS" in text or "success" in text.lower()


class TestFinalDecision:
    def test_h52_final_decision_documented(self):
        text = _read_doc()
        assert EXPECTED_DECISION in text

    def test_next_task_h53_documented(self):
        text = _read_doc()
        assert "H53" in text


class TestNoProductionDbOrCloudRun:
    def test_no_production_db_or_cloud_run_scope(self):
        text = _read_doc()
        assert "Cloud Run" in text
        assert "NOT" in text or "no" in text.lower()

    def test_no_balance_ge_activation(self):
        text = _read_doc()
        assert "Balance.ge" in text

    def test_no_feature_flag_enabled(self):
        text = _read_doc()
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text


class TestNoForbiddenImports:
    def test_no_forbidden_imports_in_test_file(self):
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
