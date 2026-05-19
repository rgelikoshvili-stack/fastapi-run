"""
Tests for docs/report-tenant-leakage-deep-check-h65.md (H65).
No Docker, no DB, no network — pure doc content verification.
"""
import os

DOC_PATH = "docs/report-tenant-leakage-deep-check-h65.md"


def _read():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_h65_leakage_doc_exists(self):
        assert os.path.exists(DOC_PATH)

    def test_h65_leakage_doc_not_empty(self):
        assert len(_read()) > 300

    def test_h65_purpose_documented(self):
        assert "Purpose" in _read()


class TestTenantContext:
    def test_tenant_context_documented(self):
        text = _read()
        assert "tenant" in text.lower()

    def test_tenant_middleware_referenced(self):
        text = _read()
        assert "tenant_middleware" in text or "tenant_id" in text

    def test_tenant_isolation_mechanism_documented(self):
        text = _read()
        assert "WHERE" in text or "isolation" in text.lower() or "middleware" in text.lower()


class TestLeakageCriteria:
    def test_leakage_criteria_documented(self):
        text = _read()
        assert "L1" in text or "criteria" in text.lower() or "leakage" in text.lower()

    def test_l4_unauthenticated_access_criterion(self):
        text = _read()
        assert "L4" in text or "unauthenticated" in text.lower()

    def test_401_unauthenticated_check_documented(self):
        assert "401" in _read()


class TestFindings:
    def test_findings_documented(self):
        text = _read()
        assert "Finding" in text or "finding" in text.lower() or "Findings" in text

    def test_blocked_decision_documented(self):
        assert "BLOCKED_AUTH_TOKEN_MISSING" in _read() or "BLOCKED_NO_AUTH_TOKEN" in _read()

    def test_l4_pass_documented(self):
        text = _read()
        assert "L4" in text
        assert "401" in text


class TestLimitations:
    def test_limitations_documented(self):
        text = _read()
        assert "Limitation" in text or "limitation" in text.lower()

    def test_auth_token_limitation_documented(self):
        text = _read()
        assert "H65_AUTH_TOKEN" in text or "token" in text.lower()


class TestFinalDecision:
    def test_h65_leakage_decision_documented(self):
        assert "TENANT_LEAKAGE_DEEP_CHECK_BLOCKED_NO_AUTH_TOKEN" in _read()

    def test_rollback_not_required(self):
        text = _read()
        assert "ROLLBACK_REQUIRED_TENANT_LEAKAGE" not in text or "not required" in text.lower()


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
