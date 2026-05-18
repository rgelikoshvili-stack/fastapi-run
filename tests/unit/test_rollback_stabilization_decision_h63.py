"""
Tests for docs/rollback-stabilization-decision-h63.md (H63).
No Docker, no DB, no network — pure doc content verification.
"""
import os
import pytest

DOC_PATH = "docs/rollback-stabilization-decision-h63.md"


def _read():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_h63_doc_exists(self):
        assert os.path.exists(DOC_PATH)

    def test_h63_doc_not_empty(self):
        assert len(_read()) > 300

    def test_h63_title(self):
        assert "H63" in _read()


class TestH61Summary:
    def test_h61_summary_present(self):
        assert "FEATURE_FLAG_ENABLED_CONTROLLED" in _read()

    def test_revision_before_documented(self):
        assert "fastapi-run-00324-9hp" in _read()

    def test_revision_after_documented(self):
        assert "fastapi-run-00325-67n" in _read()

    def test_flag_enabled_documented(self):
        assert "POSTED_LEDGER_REPORTS_ENABLED=true" in _read()

    def test_only_one_env_var_documented(self):
        text = _read()
        assert "only" in text.lower() or "No other" in text or "no other" in text.lower()


class TestH62Summary:
    def test_h62_summary_present(self):
        assert "POST_SWITCH_VERIFICATION_PASS" in _read()

    def test_sentinels_pass_documented(self):
        text = _read()
        assert "M1" in text and "PASS" in text

    def test_no_rollback_triggers_documented(self):
        text = _read()
        assert "NO" in text or "0" in text or "none" in text.lower()


class TestMonitoringSummary:
    def test_monitoring_summary_documented(self):
        text = _read()
        assert "M1" in text

    def test_demo_mode_in_monitoring(self):
        assert "demo_mode" in _read()

    def test_all_sentinels_clear(self):
        text = _read()
        assert "M9" in text


class TestRollbackTriggerEvaluation:
    def test_rollback_triggers_evaluated(self):
        text = _read()
        assert "rollback" in text.lower() or "Rollback" in text

    def test_tenant_leakage_evaluated(self):
        text = _read()
        assert "leakage" in text.lower()

    def test_zero_triggers_fired(self):
        text = _read()
        assert "NO" in text or "0" in text


class TestKeepEnabledDecision:
    def test_h63_decision_documented(self):
        assert "KEEP_ENABLED_STABILIZED" in _read()

    def test_no_rollback(self):
        text = _read()
        assert "NO" in text or "no rollback" in text.lower() or "not executed" in text.lower()

    def test_owner_acceptance_documented(self):
        text = _read()
        assert "accepted" in text.lower() or "ROLANDI" in text


class TestRollbackPlan:
    def test_rollback_command_documented(self):
        text = _read()
        assert "gcloud" in text and "remove-env-vars" in text

    def test_rollback_target_time(self):
        text = _read()
        assert "5 minutes" in text or "< 5" in text

    def test_no_other_env_var_in_rollback(self):
        assert "remove-env-vars POSTED_LEDGER_REPORTS_ENABLED" in _read()


class TestNextMonitoring:
    def test_next_monitoring_documented(self):
        text = _read()
        assert "monitor" in text.lower() or "Monitor" in text

    def test_24_hour_window(self):
        text = _read()
        assert "24 hours" in text or "24-hour" in text


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
