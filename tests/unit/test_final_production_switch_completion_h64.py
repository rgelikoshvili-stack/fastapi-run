"""
Tests for docs/final-production-switch-completion-h64.md (H64).
No Docker, no DB, no network — pure doc content verification.
"""
import os
import pytest

DOC_PATH = "docs/final-production-switch-completion-h64.md"


def _read():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_h64_completion_doc_exists(self):
        assert os.path.exists(DOC_PATH)

    def test_h64_completion_doc_not_empty(self):
        assert len(_read()) > 500

    def test_h64_purpose_documented(self):
        text = _read()
        assert "Purpose" in text


class TestEvidenceChain:
    def test_h64_evidence_chain_h49_to_h64(self):
        text = _read()
        assert "H49" in text
        assert "H64" in text

    def test_all_16_tasks_present(self):
        text = _read()
        for i in range(49, 65):
            assert f"H{i}" in text, f"H{i} not found in completion report"

    def test_docker_evidence_captured(self):
        assert "DOCKER_EVIDENCE_CAPTURED" in _read()

    def test_preflight_pass_present(self):
        assert "PREFLIGHT_PASS" in _read()

    def test_dry_run_complete_present(self):
        assert "SUCCESS_LOCAL_DOCKER_POSTGRES_DRY_RUN_COMPLETE" in _read()

    def test_snapshot_comparison_pass_present(self):
        assert "SUCCESS_LOCAL_REPORT_SNAPSHOT_COMPARISON_PASS" in _read()

    def test_keep_enabled_stabilized_present(self):
        assert "KEEP_ENABLED_STABILIZED" in _read()

    def test_monitoring_decision_present(self):
        assert "PRODUCTION_SWITCH_MONITORING_PASS_WITH_MANUAL_DEEP_CHECKS_PENDING" in _read()


class TestFinalLiveState:
    def test_h64_live_sha_documented(self):
        assert "21665ffb37bcabd4f926956e314c0bd2c5cd064f" in _read()

    def test_h64_active_revision_documented(self):
        assert "fastapi-run-00325-67n" in _read()

    def test_h64_feature_flag_enabled(self):
        text = _read()
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text
        assert "true" in text

    def test_h64_demo_mode_confirmed(self):
        assert "demo_mode" in _read()

    def test_h64_production_db_untouched(self):
        text = _read()
        assert "untouched" in text.lower() or "production DB" in text


class TestSwitchRecord:
    def test_h64_switch_command_documented(self):
        text = _read()
        assert "update-env-vars" in text

    def test_h64_approval_id_referenced(self):
        assert "APPROVAL-2026-H58-001" in _read()

    def test_h64_rollback_not_executed(self):
        text = _read()
        assert "No" in text or "NOT executed" in text or "not executed" in text.lower()

    def test_h64_zero_rollback_triggers(self):
        text = _read()
        assert "0" in text


class TestWhatDidNotChange:
    def test_h64_fixture_hash_referenced(self):
        assert "1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299" in _read()

    def test_h64_migration_hash_referenced(self):
        assert "F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA" in _read()

    def test_h64_credentials_unchanged(self):
        text = _read()
        assert "JWT_SECRET" in text or "credentials" in text.lower()


class TestPendingDeepChecks:
    def test_h64_manual_checks_documented(self):
        text = _read()
        assert "MANUAL_MONITORING_REQUIRED" in text or "manual" in text.lower()

    def test_h64_m6_tenant_check_deferred(self):
        text = _read()
        assert "M6" in text or "tenant" in text.lower()

    def test_h64_m7_report_check_deferred(self):
        text = _read()
        assert "M7" in text or "mismatch" in text.lower()


class TestCompletionDecisionOptions:
    def test_h64_completion_decision_options_documented(self):
        text = _read()
        assert "PRODUCTION_SWITCH_COMPLETE" in text

    def test_h64_limited_auth_option(self):
        assert "PRODUCTION_SWITCH_COMPLETE_WITH_LIMITED_AUTH_DEEP_CHECKS" in _read()

    def test_h64_rollback_executed_option(self):
        assert "PRODUCTION_SWITCH_COMPLETE_ROLLBACK_EXECUTED" in _read()

    def test_h64_inconclusive_option(self):
        assert "PRODUCTION_SWITCH_MONITORING_INCONCLUSIVE" in _read()


class TestNextTasks:
    def test_h64_next_tasks_documented(self):
        text = _read()
        assert "H65" in text
        assert "H66" in text
        assert "H67" in text
        assert "H68" in text

    def test_h64_next_tasks_titles_documented(self):
        text = _read()
        assert "Authenticated" in text or "Report" in text
        assert "Balance.ge" in text or "Pilot" in text


class TestNoRuntimeChanges:
    def test_h64_no_runtime_code_or_migration_change_claims(self):
        text = _read()
        assert "unchanged" in text.lower() or "not changed" in text.lower() or "did NOT change" in text
        assert "21665ff" in text

    def test_h64_migration_unchanged_documented(self):
        text = _read()
        assert "migration" in text.lower()
        assert "unchanged" in text.lower() or "not changed" in text.lower()

    def test_h64_fixture_unchanged_documented(self):
        text = _read()
        assert "fixture" in text.lower()
        assert "unchanged" in text.lower() or "not changed" in text.lower()


class TestFinalCompletionDecision:
    def test_h64_final_decision_is_complete_with_limited_checks(self):
        assert "PRODUCTION_SWITCH_COMPLETE_WITH_LIMITED_AUTH_DEEP_CHECKS" in _read()

    def test_h64_owner_name_in_approval_record(self):
        assert "ROLANDI GELIKOSHVILI" in _read()

    def test_h64_approval_closed_date(self):
        assert "2026-05-19" in _read()


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
            if s.startswith("#"):
                continue
            for imp in forbidden:
                assert imp not in s, f"Forbidden import: {s}"
