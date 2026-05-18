"""
Tests for docs/final-human-signoff-checklist-h58.md (H58).
No Docker, no DB, no network — pure doc content verification.
"""
import os
import pytest

DOC_PATH = "docs/final-human-signoff-checklist-h58.md"


def _read():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_h58_signoff_doc_exists(self):
        assert os.path.exists(DOC_PATH)

    def test_h58_signoff_doc_not_empty(self):
        assert len(_read()) > 500

    def test_h58_purpose_documented(self):
        text = _read()
        assert "Purpose" in text or "purpose" in text.lower()


class TestChecklist:
    def test_h58_checklist_has_at_least_20_items(self):
        text = _read()
        count = sum(1 for i in range(1, 25) if f"S{i}" in text)
        assert count >= 20, f"Expected at least 20 checklist items, found {count}"

    def test_s1_evidence_chain_item(self):
        text = _read()
        assert "S1" in text

    def test_s2_h53_comparison_item(self):
        assert "S2" in _read()

    def test_s3_h54_accountant_item(self):
        assert "S3" in _read()

    def test_s6_feature_flag_off_item(self):
        text = _read()
        assert "S6" in text
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text

    def test_s7_demo_mode_item(self):
        text = _read()
        assert "S7" in text
        assert "demo_mode" in text

    def test_s17_rollback_under_5_min(self):
        text = _read()
        assert "S17" in text
        assert "5 minutes" in text or "5 min" in text

    def test_s18_no_go_blockers_item(self):
        text = _read()
        assert "S18" in text

    def test_s20_h59_blocked_without_approvals(self):
        text = _read()
        assert "S20" in text
        assert "H59" in text


class TestFeatureFlagCheck:
    def test_h58_feature_flag_off_check_documented(self):
        assert "POSTED_LEDGER_REPORTS_ENABLED" in _read()

    def test_flag_off_required(self):
        text = _read()
        assert "OFF" in text or "absent" in text.lower()


class TestRequiredSignatures:
    def test_h58_required_signatures_documented(self):
        text = _read()
        assert "Signature" in text or "signature" in text.lower()

    def test_engineering_owner_signature(self):
        text = _read()
        assert "Engineering owner" in text or "engineering owner" in text.lower()

    def test_accounting_reviewer_signature(self):
        text = _read()
        assert "Accounting reviewer" in text or "accounting" in text.lower()

    def test_product_owner_signature(self):
        text = _read()
        assert "Product" in text or "product" in text.lower()

    def test_owner_name_in_signatures(self):
        assert "ROLANDI GELIKOSHVILI" in _read()


class TestSignatureStatus:
    def test_h58_signature_status_values_documented(self):
        text = _read()
        assert "pending" in text.lower()

    def test_approved_status_documented(self):
        text = _read()
        assert "approved" in text.lower()

    def test_rejected_status_documented(self):
        text = _read()
        assert "rejected" in text.lower()

    def test_expired_status_documented(self):
        text = _read()
        assert "expired" in text.lower()


class TestMonitoringAndRollback:
    def test_h58_monitoring_and_rollback_owners_documented(self):
        text = _read()
        assert "monitoring owner" in text.lower() or "Monitoring owner" in text

    def test_rollback_owner_documented(self):
        text = _read()
        assert "rollback owner" in text.lower() or "Rollback owner" in text

    def test_switch_window_documented(self):
        text = _read()
        assert "switch window" in text.lower() or "Switch window" in text


class TestH59Blocked:
    def test_h59_blocked_without_approvals(self):
        text = _read()
        assert "H59" in text
        assert "signatures" in text.lower() or "sign" in text.lower()


class TestSignoffDecision:
    def test_h58_signoff_decision_documented(self):
        text = _read()
        assert "SIGNOFF_PENDING" in text or "SIGNOFF_READY" in text

    def test_current_decision_is_pending(self):
        assert "SIGNOFF_PENDING" in _read()

    def test_signoff_ready_option_documented(self):
        assert "SIGNOFF_READY" in _read()

    def test_signoff_rejected_option_documented(self):
        assert "SIGNOFF_REJECTED" in _read()

    def test_signoff_expired_option_documented(self):
        assert "SIGNOFF_EXPIRED" in _read()

    def test_signoff_blocked_option_documented(self):
        assert "SIGNOFF_BLOCKED" in _read()


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
