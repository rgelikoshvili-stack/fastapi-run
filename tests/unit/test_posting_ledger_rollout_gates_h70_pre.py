"""tests/unit/test_posting_ledger_rollout_gates_h70_pre.py

Contract tests for 11C-H70-PRE — Posting Ledger Rollout Gates.
Verifies the rollout gates doc covers H69 dependency, POSTED_LEDGER_WRITES_ENABLED
feature flag, staging verification, production enable process, post-enable monitoring,
rollback strategy, and report layer independence.
No network, no DB, no app imports.
"""
import pathlib
import pytest

DOC = pathlib.Path(__file__).parents[2] / "docs" / "posting-ledger-rollout-gates-h70-pre.md"


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


class TestH69Gate:
    def test_h69_gate_documented(self, doc):
        assert "H69" in doc

    def test_tables_must_exist_check(self, doc):
        assert "journal_entry_headers" in doc
        assert "journal_entry_lines" in doc
        assert "journal_entry_sources" in doc

    def test_h69_schema_confirmation_required(self, doc):
        assert "H69_PRODUCTION_MIGRATION_SUCCESS_CONFIRMED" in doc or \
               "migration success" in doc.lower() or "tables confirmed" in doc.lower()

    def test_blocked_if_table_missing(self, doc):
        assert "BLOCKED_LEDGER_SCHEMA_UNAVAILABLE" in doc


class TestFeatureFlag:
    def test_posted_ledger_writes_enabled_present(self, doc):
        assert "POSTED_LEDGER_WRITES_ENABLED" in doc

    def test_default_false_documented(self, doc):
        assert "false" in doc.lower() and "default" in doc.lower()

    def test_no_write_when_disabled(self, doc):
        text = doc.lower()
        assert "dormant" in text or "no ledger" in text or "revert" in text

    def test_enable_without_code_deploy_documented(self, doc):
        assert "without" in doc.lower() and ("code" in doc.lower() or "deploy" in doc.lower())

    def test_immediate_rollback_via_flag_documented(self, doc):
        assert "immediately" in doc.lower() or "immediate" in doc.lower()


class TestStagingGate:
    def test_staging_verification_documented(self, doc):
        assert "staging" in doc.lower()

    def test_mock_posting_in_staging_checks(self, doc):
        assert "mock" in doc.lower()

    def test_ck_jeh_balanced_in_staging_checks(self, doc):
        assert "ck_jeh_balanced" in doc or "balanced" in doc.lower()

    def test_duplicate_block_in_staging_checks(self, doc):
        assert "POSTING_DUPLICATE_BLOCKED" in doc

    def test_rollback_on_failure_in_staging(self, doc):
        assert "roll" in doc.lower()

    def test_period_lock_in_staging_checks(self, doc):
        assert "period" in doc.lower() and "lock" in doc.lower()

    def test_report_layer_unchanged_in_staging_checks(self, doc):
        assert "report" in doc.lower()


class TestProductionEnableGate:
    def test_production_enable_documented(self, doc):
        assert "production" in doc.lower() and ("enable" in doc.lower() or "enabled" in doc.lower())

    def test_cloud_run_mutation_redacted(self, doc):
        assert "REDACTED" in doc or "redacted" in doc.lower() or "# gcloud" in doc

    def test_no_concurrent_deploys_during_enable(self, doc):
        assert "concurrent" in doc.lower()


class TestPostEnableMonitoring:
    def test_post_enable_monitoring_documented(self, doc):
        assert "30 minute" in doc.lower() or "30-minute" in doc.lower() or "30 min" in doc.lower()

    def test_health_check_in_monitoring(self, doc):
        assert "/health" in doc

    def test_auth_guard_check_in_monitoring(self, doc):
        assert "401" in doc or "without auth" in doc.lower() or "auth" in doc.lower()

    def test_five_xx_check_in_monitoring(self, doc):
        assert "5xx" in doc or "500" in doc

    def test_balance_ge_demo_mode_in_monitoring(self, doc):
        assert "demo_mode" in doc or "Balance.ge" in doc


class TestRollbackStrategy:
    def test_rollback_via_flag_documented(self, doc):
        assert "POSTED_LEDGER_WRITES_ENABLED" in doc
        text = doc.lower()
        assert "false" in text and ("rollback" in text or "roll back" in text or "revert" in text)

    def test_no_delete_on_posted_rows(self, doc):
        text = doc.lower()
        assert "not delete" in text or "never delete" in text or "do not delete" in text or \
               "do NOT delete" in doc or "remain" in text

    def test_correction_pattern_documented(self, doc):
        assert "correction" in doc.lower() or "reversal" in doc.lower()

    def test_correction_is_append_only(self, doc):
        assert "append" in doc.lower() or "append-only" in doc.lower() or "new row" in doc.lower()

    def test_drop_table_last_resort_only(self, doc):
        assert "DROP TABLE" in doc
        assert "last resort" in doc.lower() or "LAST RESORT" in doc

    def test_emergency_approval_required_for_drop(self, doc):
        assert "approval" in doc.lower() or "authoris" in doc.lower()


class TestReportLayerIndependence:
    def test_report_layer_unchanged_documented(self, doc):
        assert "report" in doc.lower()
        text = doc.lower()
        assert "unchanged" in text or "still read" in text or "not change" in text

    def test_journal_drafts_still_read_by_reports(self, doc):
        assert "journal_drafts" in doc

    def test_h71_report_migration_noted(self, doc):
        assert "H6" in doc or "H71" in doc or "separate task" in doc.lower()


class TestNoForbiddenPatterns:
    def test_no_raw_database_url(self, doc):
        assert "postgresql://" not in doc

    def test_no_production_password(self, doc):
        assert "BridgeHub" + "2026x" not in doc

    def test_no_posting_apply_path(self, doc):
        assert "posting/" + "apply" not in doc

    def test_no_live_gcloud_mutation(self, doc):
        # gcloud command must be commented out / redacted in this doc
        assert "# gcloud" in doc or "redacted" in doc.lower() or "REDACTED" in doc

    def test_no_balance_activation_key(self, doc):
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
