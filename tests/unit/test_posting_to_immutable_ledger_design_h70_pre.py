"""tests/unit/test_posting_to_immutable_ledger_design_h70_pre.py

Contract tests for 11C-H70-PRE — Posting to Immutable Ledger Design.
Verifies the design doc covers current behavior, target behavior, all preserved
invariants, balanced entry rule, and H70_PRE_DESIGN_READY_WAITING_FOR_H69 decision.
No network, no DB, no app imports.
"""
import pathlib
import pytest

DOC = pathlib.Path(__file__).parents[2] / "docs" / "posting-to-immutable-ledger-design-h70-pre.md"


@pytest.fixture(scope="module")
def doc():
    return DOC.read_text(encoding="utf-8")


class TestDocExists:
    def test_doc_exists(self):
        assert DOC.exists()

    def test_doc_not_empty(self, doc):
        assert len(doc) > 500

    def test_task_reference(self, doc):
        assert "11C-H70-PRE" in doc

    def test_final_decision_present(self, doc):
        assert "H70_PRE_DESIGN_READY_WAITING_FOR_H69" in doc

    def test_blocked_h69_decision_present(self, doc):
        assert "BLOCKED_H69_MIGRATION_NOT_EXECUTED" in doc

    def test_blocked_schema_decision_present(self, doc):
        assert "BLOCKED_LEDGER_SCHEMA_UNAVAILABLE" in doc


class TestCurrentBehaviorDocumented:
    def test_posting_logs_documented(self, doc):
        assert "posting_logs" in doc

    def test_journal_drafts_documented(self, doc):
        assert "journal_drafts" in doc

    def test_status_posted_documented(self, doc):
        assert "status" in doc and "posted" in doc

    def test_entry_hash_documented(self, doc):
        assert "entry_hash" in doc

    def test_for_update_documented(self, doc):
        assert "FOR UPDATE" in doc or "NOWAIT" in doc

    def test_approved_only_rule_documented(self, doc):
        assert "approved" in doc.lower()
        assert "DRAFT_NOT_APPROVED" in doc or "approved-only" in doc.lower() or "approved_draft" in doc.lower()

    def test_period_lock_documented(self, doc):
        assert "period" in doc.lower() and ("lock" in doc.lower() or "PERIOD_LOCKED" in doc)

    def test_duplicate_block_documented(self, doc):
        assert "POSTING_DUPLICATE_BLOCKED" in doc

    def test_tenant_isolation_documented(self, doc):
        assert "tenant_id" in doc


class TestTargetBehaviorDocumented:
    def test_journal_entry_headers_documented(self, doc):
        assert "journal_entry_headers" in doc

    def test_journal_entry_lines_documented(self, doc):
        assert "journal_entry_lines" in doc

    def test_journal_entry_sources_documented(self, doc):
        assert "journal_entry_sources" in doc

    def test_atomic_transaction_documented(self, doc):
        assert "transaction" in doc.lower() or "atomic" in doc.lower() or "COMMIT" in doc

    def test_same_transaction_documented(self, doc):
        assert "same transaction" in doc.lower() or "same DB transaction" in doc.lower()

    def test_balanced_entry_validated(self, doc):
        assert "ck_jeh_balanced" in doc or "balanced" in doc.lower()

    def test_total_debit_credit_documented(self, doc):
        assert "total_debit" in doc and "total_credit" in doc

    def test_line_hash_documented(self, doc):
        assert "line_hash" in doc

    def test_period_column_documented(self, doc):
        assert "period" in doc and "YYYY-MM" in doc or "entry_date" in doc

    def test_source_type_documented(self, doc):
        assert "source_type" in doc

    def test_account_type_column_documented(self, doc):
        assert "account_type" in doc

    def test_cashflow_category_column_documented(self, doc):
        assert "cashflow_category" in doc


class TestPreservedInvariants:
    def test_approved_only_preserved(self, doc):
        assert "approved" in doc.lower()

    def test_period_lock_preserved(self, doc):
        assert "period" in doc.lower() and "lock" in doc.lower()

    def test_duplicate_block_preserved(self, doc):
        assert "POSTING_DUPLICATE_BLOCKED" in doc

    def test_tenant_isolation_preserved(self, doc):
        assert "tenant_id" in doc

    def test_immutability_documented(self, doc):
        assert "immutable" in doc.lower() or "immutability" in doc.lower()

    def test_rollback_correction_pattern_documented(self, doc):
        assert "correction" in doc.lower() or "reversal" in doc.lower() or "reversed" in doc.lower()

    def test_no_delete_on_posted_rows(self, doc):
        assert "no DELETE" in doc or "never DELETE" in doc or "never delete" in doc.lower() or \
               "no destructive" in doc.lower()

    def test_posting_logs_preserved(self, doc):
        assert "posting_logs" in doc
        assert "preserved" in doc.lower() or "unchanged" in doc.lower() or "additive" in doc.lower()


class TestH69Dependency:
    def test_h69_dependency_documented(self, doc):
        assert "H69" in doc

    def test_tables_must_exist_documented(self, doc):
        assert "must exist" in doc.lower() or "tables" in doc.lower()

    def test_blocked_until_h69_documented(self, doc):
        idx_blocked = doc.find("BLOCKED")
        idx_h69 = doc.find("H69")
        assert idx_blocked > 0 and idx_h69 > 0


class TestUUIDIntMismatch:
    def test_integer_uuid_mismatch_addressed(self, doc):
        assert "UUID" in doc or "INTEGER" in doc or "int" in doc.lower()

    def test_source_draft_id_documented(self, doc):
        assert "source_draft_id" in doc


class TestNoForbiddenPatterns:
    def test_no_raw_database_url(self, doc):
        assert "postgresql://" not in doc

    def test_no_production_password(self, doc):
        assert "BridgeHub" + "2026x" not in doc

    def test_no_posting_apply_path(self, doc):
        assert "posting/" + "apply" not in doc

    def test_no_gcloud_mutation(self, doc):
        assert "gcloud run services update" not in doc

    def test_no_balance_activation_key(self, doc):
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
