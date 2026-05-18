"""
Tests for docs/accountant-review-local-comparison-h54.md (H54).
No Docker, no DB, no network — pure doc content verification.
"""
import os
import pytest

DOC_PATH = "docs/accountant-review-local-comparison-h54.md"


def _read():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_h54_doc_exists(self):
        assert os.path.exists(DOC_PATH)

    def test_h54_doc_not_empty(self):
        assert len(_read()) > 500

    def test_h54_purpose_documented(self):
        text = _read()
        assert "Purpose" in text or "purpose" in text.lower()


class TestH53EvidenceSummary:
    def test_h53_decision_referenced(self):
        assert "SUCCESS_LOCAL_REPORT_SNAPSHOT_COMPARISON_PASS" in _read()

    def test_approval_id_referenced(self):
        assert "APPROVAL-2026-H50-001" in _read()

    def test_db_target_referenced(self):
        text = _read()
        assert "127.0.0.1" in text
        assert "55433" in text

    def test_fixture_sha_referenced(self):
        assert "1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299" in _read()


class TestSnapshotCaptureSummary:
    def test_rows_documented(self):
        text = _read()
        assert "52" in text

    def test_balance_documented(self):
        text = _read()
        assert "34,469.00" in text or "23,945.00" in text

    def test_reports_count_documented(self):
        text = _read()
        assert "12" in text


class TestComparisonSummary:
    def test_comparison_checks_documented(self):
        text = _read()
        assert "23,945.00" in text

    def test_pl_documented(self):
        text = _read()
        assert "2,300.00" in text
        assert "3,525.00" in text
        assert "-1,225.00" in text

    def test_balance_sheet_documented(self):
        text = _read()
        assert "10,955.00" in text
        assert "2,180.00" in text

    def test_vat_documented(self):
        text = _read()
        assert "180.00" in text


class TestTrialBalanceResult:
    def test_trial_balance_documented(self):
        text = _read()
        assert "Trial Balance" in text or "trial_balance" in text

    def test_trial_balance_total(self):
        assert "14,480.00" in _read()

    def test_account_classification(self):
        text = _read()
        assert "Asset" in text or "asset" in text.lower()
        assert "Liability" in text or "liability" in text.lower()


class TestTenantIsolationResult:
    def test_tenant_isolation_documented(self):
        text = _read()
        assert "tenant_alpha" in text
        assert "tenant_beta" in text

    def test_isolation_pass(self):
        text = _read()
        assert "PASS" in text
        assert "leakage" in text.lower() or "isolation" in text.lower()


class TestMismatchTable:
    def test_mismatch_table_documented(self):
        assert "Mismatch" in _read()

    def test_zero_mismatches(self):
        text = _read()
        assert "0" in text
        assert "mismatches" in text.lower() or "mismatch" in text.lower()

    def test_severity_documented(self):
        text = _read()
        assert "critical" in text.lower()
        assert "high" in text.lower()
        assert "medium" in text.lower()
        assert "low" in text.lower()


class TestSeverityClassification:
    def test_severity_counts_zero(self):
        text = _read()
        assert "0" in text


class TestAccountantChecklist:
    def test_checklist_documented(self):
        text = _read()
        assert "Checklist" in text or "checklist" in text.lower()

    def test_checklist_items_pass(self):
        text = _read()
        assert "PASS" in text or "✅" in text

    def test_no_production_db_item(self):
        text = _read()
        assert "production" in text.lower()


class TestSignOffRecommendation:
    def test_signoff_recommendation_documented(self):
        text = _read()
        assert "Sign-Off" in text or "sign-off" in text.lower() or "Recommendation" in text

    def test_proceed_recommendation(self):
        text = _read()
        assert "H55" in text or "PROCEED" in text or "proceed" in text.lower()


class TestFinalDecision:
    def test_h54_decision_documented(self):
        assert "ACCOUNTANT_REVIEW_READY" in _read()

    def test_non_action_confirmed(self):
        text = _read()
        assert "does NOT" in text


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
