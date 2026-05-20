"""tests/unit/test_migration_011_dry_run_prerequisites_h68.py

Contract tests for 11C-H68 — Migration 011 Dry-Run Prerequisites.
No network, no DB, no app imports.
"""
import pathlib
import hashlib
import pytest

DOC = pathlib.Path(__file__).parents[2] / "docs" / "migration-011-dry-run-prerequisites-h68.md"
MIGRATION = pathlib.Path(__file__).parents[2] / "app" / "storage" / "migrations" / "011_posted_journal_entries_schema.sql"

EXPECTED_SHA256 = "3077cec4c3d87fc0167ba02f70b13dcff871c1ce031b6fd0644d32554b3235d0"


@pytest.fixture(scope="module")
def doc():
    return DOC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql():
    return MIGRATION.read_text(encoding="utf-8")


class TestDocumentExists:
    def test_dry_run_doc_exists(self):
        assert DOC.exists()

    def test_dry_run_doc_not_empty(self, doc):
        assert len(doc) > 400

    def test_task_reference(self, doc):
        assert "11C-H68" in doc


class TestDryRunRequired:
    def test_dry_run_required_decision(self, doc):
        assert "DRY_RUN_REQUIRED_BEFORE_PRODUCTION" in doc

    def test_production_forbidden_as_dry_run(self, doc):
        assert "FORBIDDEN" in doc or "never use production" in doc.lower() or \
               "never" in doc.lower()

    def test_disposable_db_documented(self, doc):
        assert "disposable" in doc.lower() or "Disposable" in doc

    def test_separate_instance_required(self, doc):
        assert "separate" in doc.lower() or "disposable" in doc.lower()


class TestDryRunEnvironmentOptions:
    def test_disposable_local_postgres_option(self, doc):
        assert "local PostgreSQL" in doc or "local postgres" in doc.lower() or \
               "createdb" in doc

    def test_staging_clone_option(self, doc):
        assert "staging" in doc.lower() or "clone" in doc.lower()

    def test_production_forbidden(self, doc):
        assert "FORBIDDEN" in doc


class TestDryRunSteps:
    def test_sha256_verification_step(self, doc):
        assert EXPECTED_SHA256 in doc

    def test_first_run_step(self, doc):
        assert "First" in doc or "first run" in doc.lower() or "run 1" in doc.lower()

    def test_idempotency_run_step(self, doc):
        assert "idempotency" in doc.lower() or "second run" in doc.lower() or "run 2" in doc.lower()

    def test_table_verification_step(self, doc):
        assert "information_schema" in doc or "table" in doc.lower()

    def test_column_verification_step(self, doc):
        assert "account_type" in doc
        assert "cashflow_category" in doc

    def test_index_verification_step(self, doc):
        assert "pg_indexes" in doc or "index" in doc.lower()

    def test_accounting_constraint_verification_step(self, doc):
        assert "ck_jeh_balanced" in doc or "balanced" in doc.lower()

    def test_cleanup_step(self, doc):
        assert "dropdb" in doc or "cleanup" in doc.lower() or "Cleanup" in doc


class TestDryRunPassCriteria:
    def test_pass_criteria_section(self, doc):
        assert "Pass Criteria" in doc or "pass criteria" in doc.lower() or "Criteria" in doc

    def test_exit_code_criterion(self, doc):
        assert "exit code" in doc.lower() or "exit_code" in doc.lower()

    def test_idempotency_criterion(self, doc):
        assert "idempotency" in doc.lower() or "idempotent" in doc.lower()

    def test_three_tables_criterion(self, doc):
        assert "journal_entry_headers" in doc
        assert "journal_entry_lines" in doc
        assert "journal_entry_sources" in doc


class TestDryRunEvidenceTemplate:
    def test_evidence_template_present(self, doc):
        assert "Evidence" in doc or "evidence" in doc.lower()

    def test_dry_run_completed_field(self, doc):
        assert "DRY_RUN_ALREADY_PASSED_WITH_EVIDENCE" in doc

    def test_approver_field(self, doc):
        assert "Executed by" in doc or "executed by" in doc.lower()


class TestH12Context:
    def test_h12_reference(self, doc):
        assert "H12" in doc

    def test_h12_blocked_context(self, doc):
        assert "BLOCKED" in doc or "blocked" in doc.lower()


class TestMigrationFileIntegrity:
    def test_migration_exists(self):
        assert MIGRATION.exists()

    def test_migration_sha256_current(self):
        actual = hashlib.sha256(MIGRATION.read_bytes()).hexdigest()
        assert actual == EXPECTED_SHA256, (
            f"Migration 011 SHA-256 changed!\n"
            f"Expected: {EXPECTED_SHA256}\n"
            f"Actual:   {actual}\n"
            f"If the migration was intentionally modified, update the expected hash "
            f"and all related docs."
        )

    def test_migration_is_additive_only(self, sql):
        assert "DROP TABLE" not in sql
        assert "TRUNCATE" not in sql
        lines = [l.strip() for l in sql.splitlines()]
        for line in lines:
            assert not line.upper().startswith("DELETE FROM"), f"DML DELETE found: {line}"
            assert not (line.upper().startswith("UPDATE ") and " SET " in line.upper()), \
                f"DML UPDATE found: {line}"
            assert not line.upper().startswith("INSERT INTO"), f"Fixture INSERT found: {line}"


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
