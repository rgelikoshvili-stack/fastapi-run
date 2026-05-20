"""tests/unit/test_migration_011_disposable_dry_run_evidence_h69_pre.py

Contract tests for 11C-H69-PRE-R2 — Migration 011 Disposable Dry-Run Evidence.
No network, no DB, no app imports.
"""
import pathlib
import hashlib
import pytest

DOC = pathlib.Path(__file__).parents[2] / "docs" / "migration-011-disposable-dry-run-evidence-h69-pre.md"
MIGRATION = pathlib.Path(__file__).parents[2] / "app" / "storage" / "migrations" / "011_posted_journal_entries_schema.sql"

EXPECTED_SHA256 = "3077cec4c3d87fc0167ba02f70b13dcff871c1ce031b6fd0644d32554b3235d0"


@pytest.fixture(scope="module")
def doc():
    return DOC.read_text(encoding="utf-8")


class TestDocumentExists:
    def test_dry_run_evidence_doc_exists(self):
        assert DOC.exists()

    def test_dry_run_evidence_doc_not_empty(self, doc):
        assert len(doc) > 400

    def test_task_reference(self, doc):
        assert "11C-H69-PRE-R2" in doc


class TestDryRunTarget:
    def test_production_not_used(self, doc):
        assert "NOT production" in doc or "not production" in doc.lower() or \
               "NOT used" in doc or "FORBIDDEN" in doc

    def test_disposable_target_documented(self, doc):
        assert "Disposable" in doc or "disposable" in doc.lower() or "Docker" in doc

    def test_docker_container_referenced(self, doc):
        assert "Docker" in doc or "docker" in doc.lower()

    def test_container_cleaned_up(self, doc):
        assert "stopped" in doc.lower() or "cleanup" in doc.lower() or "removed" in doc.lower()


class TestSHAVerification:
    def test_sha256_documented(self, doc):
        assert EXPECTED_SHA256 in doc

    def test_sha_match_confirmed(self, doc):
        assert "SHA VERIFIED" in doc or "SHA match" in doc or "Match: YES" in doc or \
               "match" in doc.lower()

    def test_migration_file_exists(self):
        assert MIGRATION.exists()

    def test_migration_sha256_current(self):
        actual = hashlib.sha256(MIGRATION.read_bytes()).hexdigest()
        assert actual == EXPECTED_SHA256, (
            f"Migration 011 SHA-256 changed!\n"
            f"Expected: {EXPECTED_SHA256}\n"
            f"Actual:   {actual}"
        )


class TestDryRunSteps:
    def test_first_run_exit_zero(self, doc):
        assert "exit 0" in doc.lower() or "Exit code: **0**" in doc or \
               "exit code 0" in doc.lower()

    def test_idempotency_second_run(self, doc):
        assert "idempotency" in doc.lower() or "second run" in doc.lower() or \
               "Second Run" in doc

    def test_all_three_tables_verified(self, doc):
        assert "journal_entry_headers" in doc
        assert "journal_entry_lines" in doc
        assert "journal_entry_sources" in doc

    def test_account_type_verified(self, doc):
        assert "account_type" in doc

    def test_cashflow_category_verified(self, doc):
        assert "cashflow_category" in doc

    def test_index_count_documented(self, doc):
        assert "pg_indexes" in doc or "index" in doc.lower()

    def test_constraint_verified(self, doc):
        assert "ck_jeh_balanced" in doc or "balanced" in doc.lower()

    def test_unbalanced_rejected(self, doc):
        assert "violates check constraint" in doc or "CONSTRAINT ENFORCED" in doc or \
               "must fail" in doc.lower()


class TestEvidenceDecision:
    def test_pass_decision_present(self, doc):
        assert "DRY_RUN_ALREADY_PASSED_WITH_EVIDENCE" in doc

    def test_no_destructive_side_effects(self, doc):
        assert "No destructive" in doc or "no destructive" in doc.lower()

    def test_cleanup_confirmed(self, doc):
        assert "Cleanup" in doc or "cleanup" in doc.lower()

    def test_no_production_db_touched(self, doc):
        assert "No production DB" in doc or "not production" in doc.lower() or \
               "production DB was not used" in doc.lower()


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
