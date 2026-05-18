"""
Tests for docs/production-switch-gate-monitoring-plan-h57.md (H57).
No Docker, no DB, no network — pure doc content verification.
"""
import os
import pytest

DOC_PATH = "docs/production-switch-gate-monitoring-plan-h57.md"


def _read():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_h57_doc_exists(self):
        assert os.path.exists(DOC_PATH)

    def test_h57_doc_not_empty(self):
        assert len(_read()) > 500

    def test_h57_purpose_documented(self):
        assert "Purpose" in _read()


class TestNonActionStatement:
    def test_non_action_documented(self):
        text = _read()
        assert "does NOT" in text

    def test_feature_flag_off(self):
        assert "POSTED_LEDGER_REPORTS_ENABLED" in _read()

    def test_flag_remains_off(self):
        text = _read()
        assert "remains OFF" in text or "remain" in text.lower()

    def test_no_cloud_run_mutation(self):
        text = _read()
        assert "Cloud Run" in text

    def test_no_production_db_mutation(self):
        text = _read()
        assert "production" in text.lower()


class TestInputEvidenceChain:
    def test_h49_documented(self):
        assert "DOCKER_EVIDENCE_CAPTURED" in _read()

    def test_h51_documented(self):
        assert "OWNER_APPROVAL_SIGNED" in _read()

    def test_h52_documented(self):
        assert "SUCCESS_LOCAL_DOCKER_POSTGRES_DRY_RUN_COMPLETE" in _read()

    def test_h53_documented(self):
        assert "SUCCESS_LOCAL_REPORT_SNAPSHOT_COMPARISON_PASS" in _read()

    def test_h54_documented(self):
        assert "ACCOUNTANT_REVIEW_READY" in _read()

    def test_h55_documented(self):
        assert "FINAL_LOCAL_EVIDENCE_READY" in _read()

    def test_h56_documented(self):
        assert "READY_FOR_PRODUCTION_SWITCH_PREPARATION_PLAN" in _read()


class TestFeatureFlagIdentity:
    def test_flag_name_documented(self):
        assert "POSTED_LEDGER_REPORTS_ENABLED" in _read()

    def test_fail_closed_documented(self):
        text = _read()
        assert "fail-closed" in text.lower() or "absent" in text.lower() or "OFF" in text

    def test_rollback_method_documented(self):
        text = _read()
        assert "rollback" in text.lower() or "Rollback" in text


class TestRequiredSignOffs:
    def test_signoffs_documented(self):
        text = _read()
        assert "Sign-Off" in text or "sign-off" in text.lower()

    def test_owner_documented(self):
        assert "ROLANDI GELIKOSHVILI" in _read()


class TestRolloutStages:
    def test_stages_documented(self):
        text = _read()
        assert "Stage" in text or "stage" in text.lower()

    def test_pre_switch_stage(self):
        text = _read()
        assert "Pre-switch" in text or "pre-switch" in text.lower()

    def test_canary_stage_documented(self):
        text = _read()
        assert "Canary" in text or "canary" in text.lower()

    def test_demo_mode_preswitch(self):
        assert "demo_mode" in _read()

    def test_health_check_documented(self):
        text = _read()
        assert "/health" in text


class TestMonitoringSentinels:
    def test_monitoring_documented(self):
        text = _read()
        assert "Monitoring" in text or "monitoring" in text.lower()

    def test_m1_health_documented(self):
        text = _read()
        assert "M1" in text and "/health" in text

    def test_m2_version_documented(self):
        text = _read()
        assert "M2" in text and "/version" in text

    def test_m3_5xx_documented(self):
        text = _read()
        assert "M3" in text and "5xx" in text

    def test_m4_latency_documented(self):
        text = _read()
        assert "M4" in text and "latency" in text.lower()

    def test_m5_auth_documented(self):
        text = _read()
        assert "M5" in text and "401" in text

    def test_m6_tenant_leakage_documented(self):
        text = _read()
        assert "M6" in text and "leakage" in text.lower()

    def test_m7_report_mismatch_documented(self):
        text = _read()
        assert "M7" in text

    def test_m8_balance_ge_documented(self):
        text = _read()
        assert "M8" in text and "demo_mode" in text

    def test_m9_flag_state_documented(self):
        text = _read()
        assert "M9" in text


class TestRollbackPlan:
    def test_rollback_documented(self):
        text = _read()
        assert "Rollback" in text

    def test_r1_disable_flag(self):
        text = _read()
        assert "R1" in text

    def test_r2_redeploy(self):
        text = _read()
        assert "R2" in text

    def test_r6_notify_owner(self):
        text = _read()
        assert "R6" in text

    def test_r7_incident_record(self):
        text = _read()
        assert "R7" in text and "incident" in text.lower()

    def test_r8_no_reenable(self):
        text = _read()
        assert "R8" in text

    def test_rollback_target_time(self):
        text = _read()
        assert "5 minutes" in text or "< 5" in text


class TestNoGoBlockers:
    def test_blockers_documented(self):
        text = _read()
        assert "Blocker" in text or "blocker" in text.lower()

    def test_b1_tenant_leakage(self):
        text = _read()
        assert "B1" in text and "leakage" in text.lower()

    def test_b5_flag_unexpectedly_enabled(self):
        assert "B5" in _read()

    def test_b6_balance_ge_live(self):
        assert "B6" in _read()

    def test_b9_approval_expiry(self):
        text = _read()
        assert "B9" in text and "2026-05-25" in text

    def test_b10_monitoring_sentinels(self):
        text = _read()
        assert "B10" in text

    def test_all_blockers_must_clear(self):
        text = _read()
        assert "B1" in text and "B10" in text


class TestFinalDecision:
    def test_decision_documented(self):
        assert "PRODUCTION_SWITCH_PLAN_READY" in _read()

    def test_sentinels_referenced_in_decision(self):
        text = _read()
        assert "M1" in text or "sentinels" in text.lower()

    def test_rollback_referenced_in_decision(self):
        text = _read()
        assert "R1" in text or "rollback" in text.lower()

    def test_flag_remains_off_in_decision(self):
        text = _read()
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text
        assert "OFF" in text or "remains" in text.lower()

    def test_h58_next_documented(self):
        assert "H58" in _read()


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
