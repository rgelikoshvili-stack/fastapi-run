"""
Tests for docs/report-mismatch-deep-check-h65.md (H65).
No Docker, no DB, no network — pure doc content verification.
"""
import os

DOC_PATH = "docs/report-mismatch-deep-check-h65.md"


def _read():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_h65_mismatch_doc_exists(self):
        assert os.path.exists(DOC_PATH)

    def test_h65_mismatch_doc_not_empty(self):
        assert len(_read()) > 300

    def test_h65_purpose_documented(self):
        assert "Purpose" in _read()


class TestH53Baseline:
    def test_h53_baseline_documented(self):
        text = _read()
        assert "H53" in text

    def test_trial_balance_baseline_documented(self):
        text = _read()
        assert "14,480" in text or "14480" in text

    def test_dr_cr_equality_documented(self):
        text = _read()
        assert "DR" in text and "CR" in text

    def test_total_balance_baseline_documented(self):
        text = _read()
        assert "34,469" in text or "34469" in text

    def test_pl_baseline_documented(self):
        text = _read()
        assert "2,300" in text or "income" in text.lower()

    def test_balance_sheet_baseline_documented(self):
        text = _read()
        assert "assets" in text.lower() or "10,955" in text

    def test_vat_baseline_documented(self):
        text = _read()
        assert "VAT" in text or "vat" in text.lower()


class TestComparisonMethod:
    def test_comparison_method_documented(self):
        text = _read()
        assert "exact_match" in text or "structural_match" in text

    def test_blocked_classification_documented(self):
        assert "blocked_if_no_auth" in _read()

    def test_rollback_condition_documented(self):
        text = _read()
        assert "rollback" in text.lower()


class TestInvariantChecks:
    def test_invariant_checks_documented(self):
        text = _read()
        assert "I1" in text or "Invariant" in text or "invariant" in text.lower()

    def test_dr_cr_invariant_documented(self):
        text = _read()
        assert "DR" in text and "CR" in text

    def test_no_5xx_invariant_documented(self):
        text = _read()
        assert "5xx" in text.lower() or "500" in text

    def test_no_secrets_invariant_documented(self):
        text = _read()
        assert "secret" in text.lower()


class TestFinalDecision:
    def test_h65_mismatch_decision_documented(self):
        assert "REPORT_MISMATCH_DEEP_CHECK_BLOCKED_NO_AUTH_TOKEN" in _read()

    def test_rollback_not_triggered(self):
        text = _read()
        assert "ROLLBACK_REQUIRED_CRITICAL_REPORT_MISMATCH" not in text or "deferred" in text.lower()


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
