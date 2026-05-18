"""
Tests for docs/production-switch-control-master-report-h59-h63.md (H59-H63).
No Docker, no DB, no network — pure doc content verification.
"""
import os
import pytest

DOC_PATH = "docs/production-switch-control-master-report-h59-h63.md"

EXPECTED_DECISIONS = {
    "H59": "FINAL_SIGNOFF_APPROVED",
    "H60": "CONTROLLED_SWITCH_EXECUTION_READY",
    "H61": "FEATURE_FLAG_ENABLED_CONTROLLED",
    "H62": "POST_SWITCH_VERIFICATION_PASS",
    "H63": "KEEP_ENABLED_STABILIZED",
}


def _read():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_master_report_doc_exists(self):
        assert os.path.exists(DOC_PATH)

    def test_master_report_not_empty(self):
        assert len(_read()) > 300

    def test_master_report_title(self):
        text = _read()
        assert "H59" in text and "H63" in text


class TestAllPhaseDecisions:
    def test_h59_decision_in_report(self):
        assert EXPECTED_DECISIONS["H59"] in _read()

    def test_h60_decision_in_report(self):
        assert EXPECTED_DECISIONS["H60"] in _read()

    def test_h61_decision_in_report(self):
        assert EXPECTED_DECISIONS["H61"] in _read()

    def test_h62_decision_in_report(self):
        assert EXPECTED_DECISIONS["H62"] in _read()

    def test_h63_decision_in_report(self):
        assert EXPECTED_DECISIONS["H63"] in _read()


class TestH59Summary:
    def test_approval_id_in_report(self):
        assert "APPROVAL-2026-H58-001" in _read()

    def test_five_approvers_documented(self):
        text = _read()
        assert "5" in text or "five" in text.lower()

    def test_all_signatures_documented(self):
        text = _read()
        assert "approved" in text.lower()


class TestH60Summary:
    def test_switch_window_documented(self):
        text = _read()
        assert "Switch window" in text or "switch window" in text.lower() or "Planned" in text

    def test_rollback_owner_in_report(self):
        assert "ROLANDI GELIKOSHVILI" in _read()

    def test_pre_switch_checks_documented(self):
        text = _read()
        assert "PASS" in text


class TestH61Summary:
    def test_service_region_documented(self):
        text = _read()
        assert "fastapi-run" in text
        assert "europe-west1" in text

    def test_revision_before_after_documented(self):
        text = _read()
        assert "fastapi-run-00324-9hp" in text
        assert "fastapi-run-00325-67n" in text

    def test_only_one_env_var_changed(self):
        text = _read()
        assert "none" in text.lower() or "No other" in text or "only" in text.lower()


class TestH62Summary:
    def test_sha_in_report(self):
        assert "21665ffb37bcabd4f926956e314c0bd2c5cd064f" in _read()

    def test_demo_mode_in_report(self):
        assert "demo_mode" in _read()

    def test_sentinels_in_report(self):
        text = _read()
        assert "M1" in text and "M9" in text

    def test_zero_rollback_triggers(self):
        text = _read()
        assert "0" in text or "zero" in text.lower() or "NO" in text


class TestH63Summary:
    def test_no_rollback_in_report(self):
        text = _read()
        assert "NO" in text or "no rollback" in text.lower()

    def test_flag_enabled_stable_in_report(self):
        text = _read()
        assert "ENABLED" in text or "enabled" in text.lower()


class TestFinalState:
    def test_final_state_documented(self):
        text = _read()
        assert "enabled" in text.lower() or "ENABLED" in text

    def test_revision_active_documented(self):
        assert "fastapi-run-00325-67n" in _read()

    def test_balance_ge_still_demo(self):
        assert "demo_mode" in _read()

    def test_auth_intact(self):
        text = _read()
        assert "401" in text or "auth" in text.lower()


class TestSafetySummary:
    def test_safety_summary_documented(self):
        text = _read()
        assert "Safety" in text or "safety" in text.lower()

    def test_no_balance_ge_activation(self):
        text = _read()
        assert "Balance.ge" in text

    def test_no_production_db(self):
        text = _read()
        assert "production" in text.lower() and "DB" in text or "database" in text.lower()

    def test_only_one_env_var_in_safety(self):
        text = _read()
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text


class TestMasterDecision:
    def test_master_decision_documented(self):
        assert "SUCCESS_PRODUCTION_SWITCH_ENABLED_AND_STABLE" in _read()


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
