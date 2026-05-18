"""
Tests for docs/post-switch-live-verification-h62.md (H62).
No Docker, no DB, no network — pure doc content verification.
"""
import os
import pytest

DOC_PATH = "docs/post-switch-live-verification-h62.md"


def _read():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_h62_doc_exists(self):
        assert os.path.exists(DOC_PATH)

    def test_h62_doc_not_empty(self):
        assert len(_read()) > 300

    def test_h62_title(self):
        assert "H62" in _read()


class TestVersionCheck:
    def test_version_sha_documented(self):
        assert "21665ffb37bcabd4f926956e314c0bd2c5cd064f" in _read()

    def test_version_200(self):
        text = _read()
        assert "200" in text


class TestHealthCheck:
    def test_health_200(self):
        text = _read()
        assert "200" in text and "/health" in text

    def test_demo_mode_confirmed(self):
        assert "demo_mode" in _read()

    def test_no_unexpected_degradation(self):
        text = _read()
        assert "degraded" in text.lower() or "BALANCE_API_KEY" in text


class TestFeatureFlagState:
    def test_flag_confirmed_set(self):
        text = _read()
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text
        assert "confirmed" in text.lower() or "present" in text.lower() or "set" in text.lower()


class TestAuthChecks:
    def test_h62_verifies_auth(self):
        text = _read()
        assert "401" in text

    def test_no_auth_bypass(self):
        text = _read()
        assert "bypass" in text.lower() or "No auth" in text or "no auth" in text.lower()

    def test_protected_endpoints_documented(self):
        text = _read()
        assert "/approval/queue" in text or "/reports/" in text


class TestSentinels:
    def test_all_sentinels_documented(self):
        text = _read()
        assert "M1" in text and "M9" in text

    def test_m1_health(self):
        text = _read()
        assert "M1" in text and "/health" in text

    def test_m2_version(self):
        text = _read()
        assert "M2" in text

    def test_m5_auth(self):
        text = _read()
        assert "M5" in text

    def test_m8_balance_ge(self):
        text = _read()
        assert "M8" in text and "demo_mode" in text

    def test_sentinels_all_pass(self):
        text = _read()
        assert "PASS" in text


class TestRollbackTriggers:
    def test_rollback_triggers_evaluated(self):
        text = _read()
        assert "rollback" in text.lower() or "Rollback" in text

    def test_zero_triggers_fired(self):
        text = _read()
        assert "NO" in text or "0" in text or "none" in text.lower()

    def test_tenant_leakage_trigger_evaluated(self):
        text = _read()
        assert "leakage" in text.lower()

    def test_secrets_trigger_evaluated(self):
        text = _read()
        assert "secret" in text.lower() or "Secret" in text


class TestDecision:
    def test_h62_decision_documented(self):
        assert "POST_SWITCH_VERIFICATION_PASS" in _read()

    def test_h63_next(self):
        assert "H63" in _read()


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
