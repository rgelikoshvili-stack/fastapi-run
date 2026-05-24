"""tests/unit/test_h70a_split_brain_recovery_plan.py

Contract tests for 11C-H70A-PRE — H70A Split-Brain Recovery Plan.
Verifies the split-brain doc covers all 5 cases and the decision is
H70A_PRE_SPLIT_BRAIN_PLAN_READY_WAITING_FOR_H69.
No network, no DB, no app imports.
"""
import pathlib
import pytest

RECOVERY_DOC = pathlib.Path(__file__).parents[2] / "docs" / "h70a-split-brain-recovery-plan.md"


@pytest.fixture(scope="module")
def doc():
    return RECOVERY_DOC.read_text(encoding="utf-8")


class TestDocExists:
    def test_doc_exists(self):
        assert RECOVERY_DOC.exists()

    def test_doc_not_empty(self, doc):
        assert len(doc) > 500

    def test_task_reference(self, doc):
        assert "11C-H70A-PRE" in doc

    def test_docs_tests_only_statement(self, doc):
        text = doc.lower()
        assert "docs" in text and ("tests only" in text or "no runtime" in text)


class TestSplitBrainTaxonomy:
    def test_sb1_case_documented(self, doc):
        assert "SB-1" in doc

    def test_sb2_case_documented(self, doc):
        assert "SB-2" in doc

    def test_sb3_case_documented(self, doc):
        assert "SB-3" in doc

    def test_sb4_case_documented(self, doc):
        assert "SB-4" in doc

    def test_sb5_case_documented(self, doc):
        assert "SB-5" in doc

    def test_five_cases_present(self, doc):
        for i in range(1, 6):
            assert f"SB-{i}" in doc

    def test_tier_states_documented(self, doc):
        assert "MISSING" in doc
        assert "PARTIAL" in doc

    def test_severity_documented(self, doc):
        assert "HIGH" in doc
        assert "MEDIUM" in doc or "LOW" in doc


class TestDetectionQuery:
    def test_detection_query_documented(self, doc):
        assert "journal_entry_sources" in doc
        assert "source_type" in doc
        assert "source_id" in doc

    def test_no_execute_statement(self, doc):
        text = doc.lower()
        assert "never executed in this task" in text or "template only" in text

    def test_journal_drafts_referenced(self, doc):
        assert "journal_drafts" in doc

    def test_posting_logs_referenced(self, doc):
        assert "posting_logs" in doc


class TestRecoveryRules:
    def test_idempotency_precheck(self, doc):
        assert "idempotency pre-check" in doc.lower() or "pre-check" in doc.lower()

    def test_precheck_code_template(self, doc):
        assert "journal_entry_sources" in doc
        assert "source_type" in doc
        assert "str(draft_id)" in doc

    def test_ledger_write_skipped_emitted(self, doc):
        assert "ledger_write_skipped" in doc

    def test_sb1_recovery_documented(self, doc):
        assert "SB-1" in doc
        text = doc.lower()
        assert "_write_ledger_entries" in doc or "re-run" in text or "re-running" in text

    def test_sb2_recovery_delete_then_rerun(self, doc):
        assert "SB-2" in doc
        text = doc.lower()
        assert "delete" in text

    def test_sb3_recovery_partial_insert(self, doc):
        assert "SB-3" in doc
        text = doc.lower()
        assert "insert" in text

    def test_sb4_process_restart(self, doc):
        assert "SB-4" in doc
        text = doc.lower()
        assert "process restart" in text or "restart" in text

    def test_sb5_false_split_brain(self, doc):
        assert "SB-5" in doc
        text = doc.lower()
        assert "no action" in text or "skip" in text or "false split-brain" in text


class TestRecoveryAuditEvents:
    def test_failed_event(self, doc):
        assert "ledger_write_failed" in doc

    def test_recovered_event(self, doc):
        assert "ledger_write_recovered" in doc

    def test_skipped_event(self, doc):
        assert "ledger_write_skipped" in doc

    def test_partial_delete_event(self, doc):
        assert "ledger_recovery_partial_delete" in doc

    def test_all_required_fields(self, doc):
        assert "draft_id" in doc
        assert "tenant_id" in doc
        assert "header_id" in doc


class TestRecoveryInvariants:
    def test_rinv1_one_source_per_draft(self, doc):
        assert "RINV-1" in doc

    def test_rinv2_one_event_per_draft(self, doc):
        assert "RINV-2" in doc

    def test_rinv3_no_duplicate_headers(self, doc):
        assert "RINV-3" in doc
        assert "source_hash" in doc

    def test_rinv4_tier2_immutable(self, doc):
        assert "RINV-4" in doc
        assert "journal_drafts" in doc or "posting_logs" in doc

    def test_rinv5_recovery_idempotent(self, doc):
        assert "RINV-5" in doc
        assert "idempotent" in doc.lower()

    def test_five_invariants_present(self, doc):
        for i in range(1, 6):
            assert f"RINV-{i}" in doc


class TestNonRecoveryCases:
    def test_erp_failure_out_of_scope(self, doc):
        text = doc.lower()
        assert "erp connector" in text or "tier 1" in text

    def test_not_posted_out_of_scope(self, doc):
        text = doc.lower()
        assert "never reached" in text or "not a split-brain" in text


class TestActivationSequence:
    def test_migration_011_gate(self, doc):
        assert "Migration 011" in doc or "migration 011" in doc.lower()

    def test_h69_window_referenced(self, doc):
        assert "H69" in doc
        assert "23:00" in doc

    def test_req1_to_req5_referenced(self, doc):
        assert "REQ-1" in doc or "REQ-5" in doc or "atomicity-plan" in doc

    def test_four_conditions_documented(self, doc):
        assert "POSTED_LEDGER_WRITES_ENABLED=true" in doc or "POSTED_LEDGER_WRITES_ENABLED" in doc


class TestFinalDecision:
    def test_split_brain_decision_present(self, doc):
        assert "H70A_PRE_SPLIT_BRAIN_PLAN_READY_WAITING_FOR_H69" in doc

    def test_no_sql_executed(self, doc):
        text = doc.lower()
        assert "no sql" in text or "not executed" in text

    def test_production_not_touched(self, doc):
        text = doc.lower()
        assert "not touched" in text or "production db" in text


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
