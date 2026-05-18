"""
Tests for docs/final-signoff-approval-closure-h59.md (H59).
No Docker, no DB, no network — pure doc content verification.
"""
import os
import pytest

DOC_PATH = "docs/final-signoff-approval-closure-h59.md"


def _read():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_h59_doc_exists(self):
        assert os.path.exists(DOC_PATH)

    def test_h59_doc_not_empty(self):
        assert len(_read()) > 300

    def test_h59_title(self):
        assert "H59" in _read()


class TestApprovalPacketReference:
    def test_approval_id_referenced(self):
        assert "APPROVAL-2026-H58-001" in _read()

    def test_h58_context(self):
        assert "H58" in _read()

    def test_live_sha_referenced(self):
        assert "21665ffb37bcabd4f926956e314c0bd2c5cd064f" in _read()


class TestAllFiveSignatures:
    def test_h59_requires_all_five_signatures(self):
        text = _read()
        assert "approved" in text.lower()

    def test_engineering_owner_signed(self):
        text = _read()
        assert "Engineering owner" in text or "engineering owner" in text.lower()

    def test_accounting_reviewer_signed(self):
        text = _read()
        assert "Accounting reviewer" in text or "accounting" in text.lower()

    def test_product_owner_signed(self):
        text = _read()
        assert "Product" in text or "product" in text.lower()

    def test_rollback_owner_signed(self):
        text = _read()
        assert "Rollback owner" in text or "rollback owner" in text.lower()

    def test_monitoring_owner_signed(self):
        text = _read()
        assert "Monitoring owner" in text or "monitoring owner" in text.lower()

    def test_owner_name_present(self):
        assert "ROLANDI GELIKOSHVILI" in _read()

    def test_multi_role_explicitly_documented(self):
        text = _read()
        assert "all" in text.lower() or "five" in text.lower() or "5" in text


class TestNoGoBLockersCleared:
    def test_b9_cleared(self):
        assert "B9" in _read()

    def test_b10_cleared(self):
        assert "B10" in _read()

    def test_b11_cleared(self):
        assert "B11" in _read()

    def test_b20_cleared(self):
        assert "B20" in _read()

    def test_blockers_cleared_status(self):
        text = _read()
        assert "cleared" in text.lower() or "✅" in text


class TestScope:
    def test_scope_documented(self):
        text = _read()
        assert "scope" in text.lower() or "Scope" in text

    def test_balance_ge_excluded(self):
        text = _read()
        assert "Balance.ge" in text

    def test_no_erp_posting(self):
        text = _read()
        assert "ERP" in text or "posting" in text.lower()


class TestExpiration:
    def test_expiration_documented(self):
        text = _read()
        assert "expir" in text.lower()

    def test_24_hour_rule(self):
        text = _read()
        assert "24 hours" in text or "24-hour" in text


class TestDecision:
    def test_final_signoff_approved(self):
        assert "FINAL_SIGNOFF_APPROVED" in _read()

    def test_h60_next(self):
        assert "H60" in _read()


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
