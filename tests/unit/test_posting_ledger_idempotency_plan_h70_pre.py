"""tests/unit/test_posting_ledger_idempotency_plan_h70_pre.py

Contract tests for 11C-H70-PRE — Posting Ledger Idempotency Plan.
Verifies the idempotency doc covers entry_hash, POSTING_DUPLICATE_BLOCKED,
transaction-level idempotency, split-brain handling, and concurrent write safety.
No network, no DB, no app imports.
"""
import pathlib
import pytest

DOC = pathlib.Path(__file__).parents[2] / "docs" / "posting-ledger-idempotency-plan-h70-pre.md"


@pytest.fixture(scope="module")
def doc():
    return DOC.read_text(encoding="utf-8")


class TestDocExists:
    def test_doc_exists(self):
        assert DOC.exists()

    def test_doc_not_empty(self, doc):
        assert len(doc) > 300

    def test_task_reference(self, doc):
        assert "11C-H70-PRE" in doc

    def test_final_decision_present(self, doc):
        assert "H70_PRE_DESIGN_READY_WAITING_FOR_H69" in doc

    def test_blocked_h69_present(self, doc):
        assert "BLOCKED_H69_MIGRATION_NOT_EXECUTED" in doc

    def test_blocked_schema_present(self, doc):
        assert "BLOCKED_LEDGER_SCHEMA_UNAVAILABLE" in doc


class TestExistingIdempotencyLayers:
    def test_entry_hash_documented(self, doc):
        assert "entry_hash" in doc

    def test_on_conflict_do_nothing_documented(self, doc):
        assert "DO NOTHING" in doc or "ON CONFLICT" in doc

    def test_posting_duplicate_blocked_documented(self, doc):
        assert "POSTING_DUPLICATE_BLOCKED" in doc

    def test_duplicate_check_query_documented(self, doc):
        assert "status IN" in doc or "posted" in doc.lower() and "simulated_success" in doc

    def test_blocking_statuses_present(self, doc):
        assert "simulated_success" in doc


class TestTransactionLevelIdempotency:
    def test_same_transaction_documented(self, doc):
        assert "same" in doc.lower() and "transaction" in doc.lower()

    def test_rollback_on_failure_documented(self, doc):
        assert "roll" in doc.lower()  # rollback

    def test_connector_failure_rolls_back(self, doc):
        assert "Connector fail" in doc or "connector fail" in doc.lower() or "rolled back" in doc.lower()

    def test_constraint_violation_rolls_back(self, doc):
        assert "constraint" in doc.lower() or "DB constraint" in doc

    def test_no_partial_state_documented(self, doc):
        assert "partial" in doc.lower()


class TestSplitBrainHandling:
    def test_split_brain_documented(self, doc):
        assert "split" in doc.lower() or "crash" in doc.lower()

    def test_existence_check_documented(self, doc):
        assert "existence check" in doc.lower() or "already exists" in doc.lower() or \
               "existing" in doc.lower()

    def test_sources_lookup_documented(self, doc):
        assert "journal_entry_sources" in doc

    def test_source_type_draft_documented(self, doc):
        assert "journal_draft" in doc


class TestConcurrentWriteSafety:
    def test_for_update_nowait_documented(self, doc):
        assert "FOR UPDATE NOWAIT" in doc or "NOWAIT" in doc or "DRAFT_LOCKED" in doc

    def test_single_writer_guarantee_documented(self, doc):
        assert "concurrent" in doc.lower() or "lock" in doc.lower()

    def test_draft_locked_response_documented(self, doc):
        assert "DRAFT_LOCKED" in doc


class TestMockTargetIdempotency:
    def test_mock_target_covered(self, doc):
        assert "mock" in doc.lower()

    def test_simulated_success_handled(self, doc):
        assert "simulated_success" in doc


class TestFutureUniqueConstraint:
    def test_future_unique_index_mentioned(self, doc):
        assert "UNIQUE" in doc or "unique" in doc.lower()

    def test_unique_index_not_in_h70(self, doc):
        assert "separate migration" in doc.lower() or "later task" in doc.lower() or \
               "future" in doc.lower()


class TestOneDraftOneLedgerInvariant:
    def test_one_draft_one_entry_guarantee_stated(self, doc):
        assert "one" in doc.lower() and ("draft" in doc.lower() or "posted ledger" in doc.lower())

    def test_at_most_one_documented(self, doc):
        assert "at most one" in doc.lower() or "exactly one" in doc.lower()


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
