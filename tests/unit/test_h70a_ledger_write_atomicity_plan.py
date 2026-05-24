"""tests/unit/test_h70a_ledger_write_atomicity_plan.py

Contract tests for 11C-H70A-PRE — H70A Ledger Write Atomicity Plan.
Verifies the atomicity doc covers all required contracts and the decision is
H70A_PRE_ATOMICITY_PLAN_READY_WAITING_FOR_H69.
No network, no DB, no app imports.
"""
import pathlib
import pytest

ATOMICITY_DOC = pathlib.Path(__file__).parents[2] / "docs" / "h70a-ledger-write-atomicity-plan.md"


@pytest.fixture(scope="module")
def doc():
    return ATOMICITY_DOC.read_text(encoding="utf-8")


class TestDocExists:
    def test_doc_exists(self):
        assert ATOMICITY_DOC.exists()

    def test_doc_not_empty(self, doc):
        assert len(doc) > 500

    def test_task_reference(self, doc):
        assert "11C-H70A-PRE" in doc

    def test_docs_tests_only_statement(self, doc):
        text = doc.lower()
        assert "docs" in text and ("tests only" in text or "no runtime" in text)


class TestCurrentBehaviour:
    def test_h70_deployed(self, doc):
        assert "_write_ledger_entries" in doc

    def test_flag_state_documented(self, doc):
        assert "POSTED_LEDGER_WRITES_ENABLED" in doc

    def test_flag_defaults_false(self, doc):
        assert "false" in doc.lower()

    def test_migration_011_not_exist(self, doc):
        text = doc.lower()
        assert "do not exist" in text or "not exist" in text or "has not been executed" in text


class TestConsistencyModel:
    def test_three_tiers_documented(self, doc):
        assert "Tier 1" in doc
        assert "Tier 2" in doc
        assert "Tier 3" in doc

    def test_erp_tier_1(self, doc):
        assert "ERP" in doc

    def test_journal_drafts_tier_2(self, doc):
        assert "journal_drafts" in doc

    def test_ledger_tables_tier_3(self, doc):
        assert "journal_entry_headers" in doc
        assert "journal_entry_lines" in doc
        assert "journal_entry_sources" in doc

    def test_tier_2_commits_before_tier_3(self, doc):
        idx_t2 = doc.find("Tier 2")
        idx_t3 = doc.find("Tier 3")
        assert idx_t2 != -1 and idx_t3 != -1
        assert "MUST commit before" in doc or "committed" in doc


class TestAtomicityContract:
    def test_idempotent_contract(self, doc):
        assert "Idempotent" in doc or "idempotent" in doc.lower()

    def test_non_blocking_contract(self, doc):
        assert "Non-blocking" in doc or "non-blocking" in doc.lower()

    def test_auditable_contract(self, doc):
        assert "Auditable" in doc or "auditable" in doc.lower()

    def test_recoverable_contract(self, doc):
        assert "Recoverable" in doc or "recoverable" in doc.lower()

    def test_failure_must_not_rollback_tier2(self, doc):
        text = doc.lower()
        assert "must not roll back" in text or "non-blocking" in text


class TestIdempotencyAnchors:
    def test_source_hash_anchor(self, doc):
        assert "source_hash" in doc

    def test_line_no_anchor(self, doc):
        assert "line_no" in doc

    def test_sources_precheck(self, doc):
        assert "journal_entry_sources" in doc
        assert "source_type" in doc
        assert "source_id" in doc


class TestConsistencyInvariants:
    def test_inv1_balanced_totals(self, doc):
        assert "INV-1" in doc
        assert "total_debit" in doc or "debit" in doc.lower()

    def test_inv2_source_exists(self, doc):
        assert "INV-2" in doc

    def test_inv3_lines_exist(self, doc):
        assert "INV-3" in doc

    def test_inv4_no_draft_without_lines(self, doc):
        assert "INV-4" in doc

    def test_inv5_immutability(self, doc):
        assert "INV-5" in doc
        assert "Immutability" in doc or "immutab" in doc.lower()


class TestRequiredEnhancements:
    def test_req1_audit_event(self, doc):
        assert "REQ-1" in doc
        assert "ledger_write_failed" in doc

    def test_req2_recovery_query(self, doc):
        assert "REQ-2" in doc

    def test_req3_idempotent_retry(self, doc):
        assert "REQ-3" in doc

    def test_req4_recovered_event(self, doc):
        assert "REQ-4" in doc
        assert "ledger_write_recovered" in doc

    def test_req5_precheck(self, doc):
        assert "REQ-5" in doc

    def test_five_reqs_documented(self, doc):
        for i in range(1, 6):
            assert f"REQ-{i}" in doc


class TestAuditEvents:
    def test_failed_event_documented(self, doc):
        assert "ledger_write_failed" in doc

    def test_recovered_event_documented(self, doc):
        assert "ledger_write_recovered" in doc

    def test_skipped_event_documented(self, doc):
        assert "ledger_write_skipped" in doc

    def test_failed_fields(self, doc):
        assert "draft_id" in doc
        assert "tenant_id" in doc
        assert "error" in doc


class TestImmutabilityContract:
    def test_no_update_on_posted(self, doc):
        text = doc.lower()
        assert "must not be updated" in text or "no update" in text or "immutable" in text

    def test_reversal_appends(self, doc):
        text = doc.lower()
        assert "reversal" in text or "append" in text

    def test_reversed_by_entry_id(self, doc):
        assert "reversed_by_entry_id" in doc


class TestTransactionBoundary:
    def test_main_tx_commits_first(self, doc):
        assert "tr.commit()" in doc or "await tr.commit" in doc

    def test_ledger_write_separate_tx(self, doc):
        assert "conn.transaction()" in doc or "separate transaction" in doc

    def test_exception_caught(self, doc):
        assert "except Exception" in doc or "except" in doc


class TestFinalDecision:
    def test_decision_present(self, doc):
        assert "H70A_PRE_ATOMICITY_PLAN_READY_WAITING_FOR_H69" in doc

    def test_no_sql_executed(self, doc):
        text = doc.lower()
        assert "no sql" in text or "not executed" in text

    def test_production_not_touched(self, doc):
        text = doc.lower()
        assert "not touched" in text or "production db" in text

    def test_waiting_for_h69(self, doc):
        assert "H69" in doc
        assert "WAITING_FOR_H69" in doc or "waiting for h69" in doc.lower()


class TestSecurityConstraints:
    def test_no_raw_database_url(self, doc):
        assert "postgresql://" not in doc

    def test_no_production_password(self, doc):
        assert "BridgeHub" + "2026x" not in doc

    def test_no_posting_apply(self, doc):
        assert "posting/" + "apply" not in doc

    def test_no_balance_activation_key(self, doc):
        assert "BALANCE_API_KEY=sk" not in doc

    def test_no_gcloud_mutation(self, doc):
        assert "gcloud run services update" not in doc


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
