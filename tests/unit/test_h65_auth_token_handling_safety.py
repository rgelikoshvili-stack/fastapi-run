"""
Tests for docs/h65-auth-token-handling-safety.md (H65).
No Docker, no DB, no network — pure doc content verification.
"""
import os

DOC_PATH = "docs/h65-auth-token-handling-safety.md"


def _read():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_h65_safety_doc_exists(self):
        assert os.path.exists(DOC_PATH)

    def test_h65_safety_doc_not_empty(self):
        assert len(_read()) > 300

    def test_h65_purpose_documented(self):
        assert "Purpose" in _read()


class TestTokenSource:
    def test_token_source_env_var_documented(self):
        assert "H65_AUTH_TOKEN" in _read()

    def test_env_var_only_source_documented(self):
        text = _read()
        assert "environment variable" in text.lower() or "env" in text.lower()

    def test_no_other_token_source_allowed(self):
        text = _read()
        assert "only" in text.lower()


class TestRedactionRules:
    def test_redaction_rules_documented(self):
        text = _read()
        assert "Redact" in text or "redact" in text.lower() or "REDACTED" in text

    def test_no_print_token_rule(self):
        text = _read()
        assert "print" in text.lower() or "echo" in text.lower() or "never" in text.lower()

    def test_authorization_header_redaction_documented(self):
        text = _read()
        assert "Authorization" in text


class TestForbiddenStorage:
    def test_forbidden_storage_documented(self):
        text = _read()
        assert "Forbidden" in text or "forbidden" in text.lower()

    def test_env_file_forbidden(self):
        text = _read()
        assert ".env" in text

    def test_committed_file_forbidden(self):
        text = _read()
        assert "committed" in text.lower() or "commit" in text.lower()

    def test_docs_forbidden(self):
        text = _read()
        assert "docs" in text.lower()


class TestForbiddenEndpoints:
    def test_write_endpoints_forbidden(self):
        text = _read()
        assert "POST" in text or "write" in text.lower()

    def test_posting_apply_forbidden(self):
        text = _read()
        assert "posting" in text.lower() or "apply" in text.lower()

    def test_balance_ge_activation_forbidden(self):
        text = _read()
        assert "Balance.ge" in text or "activat" in text.lower()


class TestReadOnlyScope:
    def test_read_only_scope_documented(self):
        text = _read()
        assert "read-only" in text.lower() or "Read-Only" in text or "Read-only" in text

    def test_get_endpoints_permitted(self):
        text = _read()
        assert "GET" in text

    def test_reports_trial_balance_permitted(self):
        text = _read()
        assert "trial-balance" in text or "reports" in text.lower()


class TestSafetyDecision:
    def test_h65_safety_decision_documented(self):
        text = _read()
        assert "TOKEN_HANDLING_SAFE" in text or "SAFE" in text

    def test_no_token_available_documented(self):
        text = _read()
        assert "NOT AVAILABLE" in text or "not available" in text.lower() or "missing" in text.lower()


class TestNoRawTokensInFile:
    def test_no_raw_auth_token_in_test_file(self):
        with open(__file__, encoding="utf-8") as f:
            lines = f.readlines()
        raw_bearer = "Authorization: " + "Bearer eyJ"
        for line in lines:
            assert raw_bearer not in line, f"Raw token found: {line.strip()}"

    def test_no_production_database_url(self):
        with open(__file__, encoding="utf-8") as f:
            content = f.read()
        pg_url = "postgresql" + "://"
        assert pg_url not in content


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
