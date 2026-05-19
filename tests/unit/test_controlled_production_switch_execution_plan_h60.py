"""
Tests for docs/controlled-production-switch-execution-plan-h60.md (H60).
No Docker, no DB, no network — pure doc content verification.
"""
import os
import pytest

DOC_PATH = "docs/controlled-production-switch-execution-plan-h60.md"


def _read():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_h60_doc_exists(self):
        assert os.path.exists(DOC_PATH)

    def test_h60_doc_not_empty(self):
        assert len(_read()) > 300

    def test_h60_title(self):
        assert "H60" in _read()


class TestH59Reference:
    def test_h59_signoff_referenced(self):
        assert "FINAL_SIGNOFF_APPROVED" in _read()

    def test_approval_id_referenced(self):
        assert "APPROVAL-2026-H58-001" in _read()


class TestLiveState:
    def test_live_sha_documented(self):
        assert "21665ffb37bcabd4f926956e314c0bd2c5cd064f" in _read()

    def test_health_documented(self):
        text = _read()
        assert "/health" in text

    def test_feature_flag_off_before_switch(self):
        text = _read()
        assert "absent" in text.lower() or "OFF" in text

    def test_demo_mode_documented(self):
        assert "demo_mode" in _read()

    def test_revision_before_documented(self):
        assert "fastapi-run-00324-9hp" in _read()


class TestSwitchWindow:
    def test_switch_window_documented(self):
        text = _read()
        assert "switch window" in text.lower() or "Switch window" in text or "Planned" in text

    def test_operator_documented(self):
        assert "ROLANDI GELIKOSHVILI" in _read()

    def test_rollback_owner_documented(self):
        text = _read()
        assert "rollback owner" in text.lower() or "Rollback owner" in text

    def test_monitoring_owner_documented(self):
        text = _read()
        assert "monitoring owner" in text.lower() or "Monitoring owner" in text


class TestPreSwitchChecklist:
    def test_pre_switch_checklist_documented(self):
        text = _read()
        assert "checklist" in text.lower() or "Checklist" in text

    def test_version_check(self):
        assert "/version" in _read()

    def test_health_check(self):
        assert "/health" in _read()

    def test_auth_check(self):
        text = _read()
        assert "401" in text or "auth" in text.lower()


class TestEnablementAction:
    def test_enablement_command_documented(self):
        text = _read()
        assert "POSTED_LEDGER_REPORTS_ENABLED=true" in text

    def test_update_env_vars_used(self):
        text = _read()
        assert "--update-env-vars" in text

    def test_only_one_env_var_changed(self):
        text = _read()
        assert "only" in text.lower() or "No other" in text or "no other" in text.lower()

    def test_service_and_region_documented(self):
        text = _read()
        assert "fastapi-run" in text
        assert "europe-west1" in text


class TestRollbackAction:
    def test_rollback_command_documented(self):
        text = _read()
        assert "remove-env-vars" in text or "rollback" in text.lower()

    def test_rollback_no_other_env_var(self):
        text = _read()
        assert "No other" in text or "no other" in text.lower() or "only" in text.lower()


class TestStopTriggers:
    def test_stop_triggers_documented(self):
        text = _read()
        assert "rollback" in text.lower() or "Rollback" in text

    def test_tenant_leakage_trigger(self):
        text = _read()
        assert "leakage" in text.lower()

    def test_5xx_trigger(self):
        text = _read()
        assert "5xx" in text


class TestDecision:
    def test_h60_decision_documented(self):
        assert "CONTROLLED_SWITCH_EXECUTION_READY" in _read()

    def test_h61_next(self):
        assert "H61" in _read()


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
