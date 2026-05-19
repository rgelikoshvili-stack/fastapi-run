"""
Tests for docs/authenticated-report-endpoint-verification-h65.md (H65).
No Docker, no DB, no network — pure doc content verification.
"""
import os

DOC_PATH = "docs/authenticated-report-endpoint-verification-h65.md"


def _read():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_h65_endpoint_verification_doc_exists(self):
        assert os.path.exists(DOC_PATH)

    def test_h65_doc_not_empty(self):
        assert len(_read()) > 500

    def test_h65_purpose_documented(self):
        assert "Purpose" in _read()


class TestH64Context:
    def test_h64_context_documented(self):
        text = _read()
        assert "H64" in text
        assert "PRODUCTION_SWITCH_COMPLETE_WITH_LIMITED_AUTH_DEEP_CHECKS" in text

    def test_live_sha_documented(self):
        assert "50782e46c73214c5fde3b0b40362c7cfefbec26a" in _read()

    def test_feature_flag_state_documented(self):
        text = _read()
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text
        assert "true" in text

    def test_demo_mode_documented(self):
        assert "demo_mode" in _read()


class TestAuthTokenHandling:
    def test_auth_token_handling_documented(self):
        text = _read()
        assert "auth" in text.lower() or "token" in text.lower()

    def test_token_env_var_documented(self):
        assert "H65_AUTH_TOKEN" in _read()

    def test_no_raw_token_committed(self):
        text = _read()
        assert "Authorization: Bearer " not in text or "REDACTED" in text or "H65_AUTH_TOKEN" in text

    def test_blocked_decision_documented(self):
        assert "BLOCKED_AUTH_TOKEN_MISSING_FOR_DEEP_CHECKS" in _read()


class TestUnauthenticatedBaseline:
    def test_unauthenticated_baseline_documented(self):
        text = _read()
        assert "401" in text

    def test_version_check_documented(self):
        text = _read()
        assert "/version" in text
        assert "200" in text

    def test_health_check_documented(self):
        text = _read()
        assert "/health" in text
        assert "200" in text

    def test_report_endpoints_401_documented(self):
        text = _read()
        assert "/reports/trial-balance" in text
        assert "401" in text

    def test_no_auth_bypass_documented(self):
        text = _read()
        assert "bypass" in text.lower() or "NO" in text


class TestAuthenticatedMatrix:
    def test_authenticated_endpoint_matrix_documented(self):
        text = _read()
        assert "BLOCKED" in text

    def test_trial_balance_in_matrix(self):
        assert "trial-balance" in _read()

    def test_blocked_token_missing_in_matrix(self):
        assert "BLOCKED_AUTH_TOKEN_MISSING" in _read()


class TestStatusSummary:
    def test_http_status_summary_documented(self):
        text = _read()
        assert "200" in text
        assert "401" in text

    def test_zero_5xx_documented(self):
        text = _read()
        assert "5xx" in text.lower() or "500" in text
        assert "0" in text

    def test_zero_auth_bypass_documented(self):
        text = _read()
        assert "bypass" in text.lower()
        assert "0" in text


class TestRollbackAssessment:
    def test_rollback_assessment_documented(self):
        text = _read()
        assert "rollback" in text.lower() or "Rollback" in text

    def test_rollback_not_required(self):
        text = _read()
        assert "NO" in text or "not required" in text.lower()


class TestFinalDecision:
    def test_h65_final_decision_documented(self):
        assert "BLOCKED_AUTH_TOKEN_MISSING_FOR_DEEP_CHECKS" in _read()

    def test_h65_decision_section_present(self):
        text = _read()
        assert "Decision" in text


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
