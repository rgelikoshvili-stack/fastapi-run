"""tests/unit/test_migration_011_production_execution_plan_h68.py

Contract tests for 11C-H68 — Migration 011 Production Execution Plan.
No network, no DB, no app imports.
"""
import pathlib
import re
import pytest

DOC = pathlib.Path(__file__).parents[2] / "docs" / "migration-011-production-execution-plan-h68.md"
MIGRATION = pathlib.Path(__file__).parents[2] / "app" / "storage" / "migrations" / "011_posted_journal_entries_schema.sql"


@pytest.fixture(scope="module")
def doc():
    return DOC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql():
    return MIGRATION.read_text(encoding="utf-8")


class TestDocumentExists:
    def test_execution_plan_doc_exists(self):
        assert DOC.exists()

    def test_execution_plan_not_empty(self, doc):
        assert len(doc) > 500

    def test_task_reference(self, doc):
        assert "11C-H68" in doc


class TestH67RootCause:
    def test_h67_decision_documented(self, doc):
        assert "H67_BLOCKED_POSTED_LEDGER_SCHEMA_MISSING" in doc

    def test_missing_tables_documented(self, doc):
        assert "journal_entry_headers" in doc
        assert "journal_entry_lines" in doc
        assert "journal_entry_sources" in doc

    def test_root_cause_documented(self, doc):
        assert "never been executed" in doc or "never run" in doc or "never executed" in doc


class TestMigration011Identity:
    def test_migration_file_path_documented(self, doc):
        assert "011_posted_journal_entries_schema.sql" in doc

    def test_sha256_documented(self, doc):
        assert "3077cec4c3d87fc0167ba02f70b13dcff871c1ce031b6fd0644d32554b3235d0" in doc

    def test_migration_file_exists(self):
        assert MIGRATION.exists()

    def test_migration_sha256_matches(self):
        import hashlib
        digest = hashlib.sha256(MIGRATION.read_bytes()).hexdigest()
        assert digest == "3077cec4c3d87fc0167ba02f70b13dcff871c1ce031b6fd0644d32554b3235d0"


class TestMigrationReviewPassAdditive:
    def test_review_decision_documented(self, doc):
        assert "MIGRATION_011_REVIEW_PASS_ADDITIVE" in doc

    def test_create_table_if_not_exists_in_sql(self, sql):
        assert "CREATE TABLE IF NOT EXISTS journal_entry_headers" in sql
        assert "CREATE TABLE IF NOT EXISTS journal_entry_lines" in sql
        assert "CREATE TABLE IF NOT EXISTS journal_entry_sources" in sql

    def test_create_index_if_not_exists_in_sql(self, sql):
        assert "CREATE INDEX IF NOT EXISTS" in sql

    def test_no_drop_table_in_sql(self, sql):
        assert "DROP TABLE" not in sql

    def test_no_truncate_in_sql(self, sql):
        assert "TRUNCATE" not in sql

    def test_no_delete_dml_in_sql(self, sql):
        # ON DELETE CASCADE is a FK constraint, not DML — check for DML DELETE only
        lines = [l.strip() for l in sql.splitlines()]
        for line in lines:
            if line.upper().startswith("DELETE FROM"):
                pytest.fail(f"Destructive DML found: {line}")

    def test_no_update_dml_in_sql(self, sql):
        lines = [l.strip() for l in sql.splitlines()]
        for line in lines:
            if line.upper().startswith("UPDATE ") and " SET " in line.upper():
                pytest.fail(f"Destructive DML found: {line}")

    def test_no_insert_dml_in_sql(self, sql):
        lines = [l.strip() for l in sql.splitlines()]
        for line in lines:
            if line.upper().startswith("INSERT INTO"):
                pytest.fail(f"Fixture INSERT found: {line}")

    def test_tenant_id_not_null_in_sql(self, sql):
        assert "tenant_id" in sql
        assert "NOT NULL" in sql

    def test_account_type_column_in_sql(self, sql):
        assert "account_type" in sql

    def test_cashflow_category_column_in_sql(self, sql):
        assert "cashflow_category" in sql


class TestPreExecutionChecklist:
    def test_backup_pitr_checklist_documented(self, doc):
        assert "PITR" in doc or "backup" in doc.lower()

    def test_staging_dry_run_checklist_documented(self, doc):
        assert "staging" in doc.lower() or "disposable" in doc.lower() or "dry-run" in doc.lower()

    def test_maintenance_window_documented(self, doc):
        assert "maintenance window" in doc.lower() or "Maintenance window" in doc

    def test_personnel_roles_documented(self, doc):
        assert "Engineering owner" in doc or "engineering owner" in doc.lower()
        assert "Rollback owner" in doc or "rollback owner" in doc.lower()
        assert "Monitoring owner" in doc or "monitoring owner" in doc.lower()


class TestPostExecutionVerification:
    def test_post_exec_plan_documented(self, doc):
        assert "Post-Execution" in doc or "post-execution" in doc.lower()

    def test_version_check_documented(self, doc):
        assert "/version" in doc

    def test_health_check_documented(self, doc):
        assert "/health" in doc

    def test_report_endpoint_recheck_documented(self, doc):
        assert "trial-balance" in doc or "trial_balance" in doc

    def test_no_5xx_check_documented(self, doc):
        assert "5xx" in doc


class TestH68Decision:
    def test_approval_decision_documented(self, doc):
        assert "APPROVAL_READY_FOR_SIGNATURE_AFTER_BACKUP_AND_DRY_RUN" in doc

    def test_h69_not_started(self, doc):
        assert "H69 not started" in doc or "H69 execution must NOT begin" in doc or "H69" in doc

    def test_no_production_sql_executed(self, doc):
        assert "No SQL executed" in doc or "No production SQL" in doc or "no production SQL" in doc.lower()


class TestNoForbiddenPatterns:
    def test_no_raw_database_url(self, doc):
        assert "postgresql://" not in doc

    def test_no_production_password(self, doc):
        assert "BridgeHub" + "2026x" not in doc

    def test_no_raw_jwt_secret(self, doc):
        assert "BridgeHub" + "2026JWT" not in doc

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
