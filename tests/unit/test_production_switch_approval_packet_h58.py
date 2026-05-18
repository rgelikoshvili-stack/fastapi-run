"""
Tests for docs/production-switch-approval-packet-h58.md (H58).
No Docker, no DB, no network — pure doc content verification.
"""
import os
import pytest

DOC_PATH = "docs/production-switch-approval-packet-h58.md"


def _read():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_h58_approval_packet_doc_exists(self):
        assert os.path.exists(DOC_PATH)

    def test_h58_doc_not_empty(self):
        assert len(_read()) > 500

    def test_h58_purpose_section(self):
        text = _read()
        assert "Purpose" in text or "Approval Packet" in text


class TestNonActionStatement:
    def test_h58_non_action_statement_present(self):
        text = _read()
        assert "does NOT" in text

    def test_feature_flag_not_enabled(self):
        assert "POSTED_LEDGER_REPORTS_ENABLED" in _read()

    def test_no_cloud_run_mutation(self):
        text = _read()
        assert "Cloud Run" in text

    def test_no_production_db_touch(self):
        text = _read()
        assert "production" in text.lower()

    def test_h58_does_not_enable_feature_flag(self):
        text = _read()
        assert "does NOT enable" in text or "does NOT change" in text
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text


class TestEvidenceChain:
    def test_h58_evidence_chain_h49_to_h57_documented(self):
        text = _read()
        assert "H49" in text
        assert "H57" in text

    def test_h49_decision_present(self):
        assert "DOCKER_EVIDENCE_CAPTURED" in _read()

    def test_h52_decision_present(self):
        assert "SUCCESS_LOCAL_DOCKER_POSTGRES_DRY_RUN_COMPLETE" in _read()

    def test_h53_decision_present(self):
        assert "SUCCESS_LOCAL_REPORT_SNAPSHOT_COMPARISON_PASS" in _read()

    def test_h54_decision_present(self):
        assert "ACCOUNTANT_REVIEW_READY" in _read()

    def test_h55_decision_present(self):
        assert "FINAL_LOCAL_EVIDENCE_READY" in _read()

    def test_h56_decision_present(self):
        assert "READY_FOR_PRODUCTION_SWITCH_PREPARATION_PLAN" in _read()

    def test_h57_decision_present(self):
        assert "PRODUCTION_SWITCH_PLAN_READY" in _read()


class TestLiveState:
    def test_h58_live_state_documented(self):
        text = _read()
        assert "c4fd6b9" in text

    def test_live_sha_documented(self):
        assert "c4fd6b919ed30e49e0eeb1b4da4ff3cfc8fd0af5" in _read()

    def test_feature_flag_off_in_live_state(self):
        text = _read()
        assert "OFF" in text or "absent" in text.lower()

    def test_demo_mode_documented(self):
        assert "demo_mode" in _read()

    def test_auth_required_documented(self):
        text = _read()
        assert "401" in text or "auth" in text.lower()


class TestRequiredApprovers:
    def test_h58_required_approvers_documented(self):
        text = _read()
        assert "engineering owner" in text.lower() or "Engineering owner" in text

    def test_accounting_reviewer_documented(self):
        text = _read()
        assert "Accounting" in text or "accounting" in text.lower()

    def test_rollback_owner_documented(self):
        text = _read()
        assert "rollback owner" in text.lower() or "Rollback owner" in text

    def test_monitoring_owner_documented(self):
        text = _read()
        assert "monitoring owner" in text.lower() or "Monitoring owner" in text

    def test_owner_name_documented(self):
        assert "ROLANDI GELIKOSHVILI" in _read()


class TestApprovalFields:
    def test_h58_approval_fields_documented(self):
        text = _read()
        assert "approval_id" in text

    def test_approval_id_value(self):
        assert "APPROVAL-2026-H58-001" in _read()

    def test_scope_field_documented(self):
        assert "scope" in _read()

    def test_feature_flag_field_documented(self):
        assert "feature_flag" in _read()

    def test_decision_field_documented(self):
        assert "decision" in _read()

    def test_expires_at_field_documented(self):
        assert "expires_at" in _read()

    def test_rollback_owner_field_documented(self):
        assert "rollback_owner" in _read()

    def test_evidence_refs_field_documented(self):
        assert "evidence_refs" in _read()


class TestApprovalScope:
    def test_h58_scope_excludes_execution(self):
        text = _read()
        assert "NOT allow" in text or "not allowed" in text.lower() or "Explicitly NOT" in text

    def test_flag_enablement_not_allowed(self):
        text = _read()
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text

    def test_db_migration_not_allowed(self):
        text = _read()
        assert "migration" in text.lower()

    def test_balance_ge_not_allowed(self):
        text = _read()
        assert "Balance.ge" in text


class TestExpirationRule:
    def test_h58_expiration_rule_documented(self):
        text = _read()
        assert "expir" in text.lower()

    def test_7_day_rule_documented(self):
        text = _read()
        assert "7 days" in text or "7-day" in text

    def test_expiration_date_documented(self):
        assert "2026-05-25" in _read()

    def test_refresh_condition_documented(self):
        text = _read()
        assert "refresh" in text.lower() or "reissued" in text.lower()


class TestDecisionOptions:
    def test_h58_decision_options_documented(self):
        text = _read()
        assert "FINAL_SIGNOFF_READY" in text

    def test_pending_signatures_decision(self):
        assert "FINAL_SIGNOFF_READY_PENDING_SIGNATURES" in _read()

    def test_blocked_options_documented(self):
        text = _read()
        assert "BLOCKED" in text

    def test_blocked_missing_approver(self):
        assert "BLOCKED_MISSING_APPROVER" in _read()

    def test_blocked_expired(self):
        assert "BLOCKED_EXPIRED_APPROVAL" in _read()

    def test_blocked_no_go(self):
        assert "BLOCKED_NO_GO_BLOCKER" in _read()


class TestFinalDecision:
    def test_current_decision_is_pending(self):
        assert "FINAL_SIGNOFF_READY_PENDING_SIGNATURES" in _read()

    def test_h59_next_documented(self):
        assert "H59" in _read()


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
            if s.startswith("#"): continue
            for imp in forbidden:
                assert imp not in s, f"Forbidden import: {s}"
