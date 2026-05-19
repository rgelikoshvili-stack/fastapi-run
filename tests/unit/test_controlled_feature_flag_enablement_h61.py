"""
Tests for docs/controlled-feature-flag-enablement-h61.md (H61).
No Docker, no DB, no network — pure doc content verification.
"""
import os
import pytest

DOC_PATH = "docs/controlled-feature-flag-enablement-h61.md"


def _read():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_h61_doc_exists(self):
        assert os.path.exists(DOC_PATH)

    def test_h61_doc_not_empty(self):
        assert len(_read()) > 300

    def test_h61_title(self):
        assert "H61" in _read()


class TestPreSwitchVerification:
    def test_pre_switch_checks_documented(self):
        text = _read()
        assert "Pre-Switch" in text or "pre-switch" in text.lower()

    def test_version_check_pass(self):
        assert "21665ffb37bcabd4f926956e314c0bd2c5cd064f" in _read()

    def test_health_check_pass(self):
        text = _read()
        assert "/health" in text

    def test_flag_absent_before(self):
        text = _read()
        assert "absent" in text.lower() or "OFF" in text

    def test_demo_mode_before(self):
        assert "demo_mode" in _read()

    def test_auth_401_before(self):
        text = _read()
        assert "401" in text


class TestEnablementExecution:
    def test_command_documented(self):
        text = _read()
        assert "gcloud run services update" in text

    def test_update_env_vars_flag(self):
        assert "--update-env-vars" in _read()

    def test_flag_set_to_true(self):
        assert "POSTED_LEDGER_REPORTS_ENABLED=true" in _read()

    def test_service_documented(self):
        assert "fastapi-run" in _read()

    def test_region_documented(self):
        assert "europe-west1" in _read()

    def test_operator_documented(self):
        assert "ROLANDI GELIKOSHVILI" in _read()


class TestSingleEnvVarOnly:
    def test_h61_documents_single_env_var_mutation_only(self):
        text = _read()
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text

    def test_h61_documents_no_other_env_var_changes(self):
        text = _read()
        assert "No other" in text or "no other" in text.lower() or "only" in text.lower()


class TestRevisions:
    def test_revision_before_documented(self):
        assert "fastapi-run-00324-9hp" in _read()

    def test_revision_after_documented(self):
        assert "fastapi-run-00325-67n" in _read()

    def test_traffic_routing_documented(self):
        text = _read()
        assert "100" in text or "traffic" in text.lower()


class TestDecision:
    def test_h61_decision_documented(self):
        assert "FEATURE_FLAG_ENABLED_CONTROLLED" in _read()

    def test_h62_next(self):
        assert "H62" in _read()

    def test_blocked_options_documented(self):
        text = _read()
        assert "BLOCKED" in text or "blocked" in text.lower()


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
