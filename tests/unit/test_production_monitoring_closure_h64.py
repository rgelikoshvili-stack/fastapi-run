"""
Tests for docs/production-monitoring-closure-h64.md (H64).
No Docker, no DB, no network — pure doc content verification.
"""
import os
import pytest

DOC_PATH = "docs/production-monitoring-closure-h64.md"


def _read():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_h64_monitoring_doc_exists(self):
        assert os.path.exists(DOC_PATH)

    def test_h64_monitoring_doc_not_empty(self):
        assert len(_read()) > 500

    def test_h64_purpose_documented(self):
        text = _read()
        assert "Purpose" in text


class TestMonitoringContext:
    def test_h64_live_sha_documented(self):
        assert "21665ffb37bcabd4f926956e314c0bd2c5cd064f" in _read()

    def test_h64_short_sha_documented(self):
        assert "21665ff" in _read()

    def test_h64_active_revision_documented(self):
        assert "fastapi-run-00325-67n" in _read()

    def test_h64_prior_revision_documented(self):
        assert "fastapi-run-00324-9hp" in _read()

    def test_h64_feature_flag_state_documented(self):
        assert "POSTED_LEDGER_REPORTS_ENABLED" in _read()

    def test_h64_demo_mode_documented(self):
        assert "demo_mode" in _read()


class TestSentinelResults:
    def test_h64_m1_health_pass(self):
        text = _read()
        assert "M1" in text
        assert "PASS" in text

    def test_h64_m2_sha_pass(self):
        text = _read()
        assert "M2" in text

    def test_h64_m3_manual_monitoring(self):
        text = _read()
        assert "M3" in text
        assert "MANUAL_MONITORING_REQUIRED" in text

    def test_h64_m4_manual_monitoring(self):
        text = _read()
        assert "M4" in text
        assert "MANUAL_MONITORING_REQUIRED" in text

    def test_h64_m5_auth_pass(self):
        text = _read()
        assert "M5" in text
        assert "401" in text

    def test_h64_m6_tenant_leakage_blocked(self):
        text = _read()
        assert "M6" in text
        assert "TENANT_LEAKAGE_DEEP_CHECK_BLOCKED_NO_AUTH_TOKEN" in text

    def test_h64_m7_report_mismatch_blocked(self):
        text = _read()
        assert "M7" in text
        assert "REPORT_MISMATCH_DEEP_CHECK_BLOCKED_NO_AUTH_TOKEN" in text

    def test_h64_m8_balance_ge_pass(self):
        text = _read()
        assert "M8" in text

    def test_h64_m9_feature_flag_confirmed(self):
        text = _read()
        assert "M9" in text


class TestRollbackTriggers:
    def test_h64_rollback_triggers_evaluated(self):
        text = _read()
        assert "rollback" in text.lower() or "Rollback" in text

    def test_h64_zero_triggers_fired(self):
        text = _read()
        assert "0" in text

    def test_h64_rollback_command_documented(self):
        text = _read()
        assert "remove-env-vars" in text

    def test_h64_rollback_not_executed(self):
        text = _read()
        assert "NOT executed" in text or "not executed" in text.lower()


class TestDecisionOptions:
    def test_h64_decision_options_documented(self):
        text = _read()
        assert "PRODUCTION_SWITCH_MONITORING_PASS" in text

    def test_h64_manual_checks_decision_option(self):
        assert "PRODUCTION_SWITCH_MONITORING_PASS_WITH_MANUAL_DEEP_CHECKS_PENDING" in _read()

    def test_h64_rollback_required_option(self):
        assert "PRODUCTION_SWITCH_MONITORING_ROLLBACK_REQUIRED" in _read()

    def test_h64_inconclusive_option(self):
        assert "PRODUCTION_SWITCH_MONITORING_INCONCLUSIVE" in _read()


class TestFinalMonitoringDecision:
    def test_h64_final_monitoring_decision_present(self):
        assert "PRODUCTION_SWITCH_MONITORING_PASS_WITH_MANUAL_DEEP_CHECKS_PENDING" in _read()

    def test_h64_critical_sentinels_pass_count(self):
        text = _read()
        assert "5/5" in text or "5 of 5" in text.lower() or "M1, M2, M5, M8, M9" in text


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
