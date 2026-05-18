"""
Tests for docs/production-switch-no-go-blockers-h58.md (H58).
No Docker, no DB, no network — pure doc content verification.
"""
import os
import pytest

DOC_PATH = "docs/production-switch-no-go-blockers-h58.md"


def _read():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_h58_no_go_doc_exists(self):
        assert os.path.exists(DOC_PATH)

    def test_h58_no_go_doc_not_empty(self):
        assert len(_read()) > 500

    def test_h58_purpose_documented(self):
        assert "Purpose" in _read()


class TestBlockerCount:
    def test_h58_has_at_least_15_blockers(self):
        text = _read()
        count = sum(1 for i in range(1, 25) if f"B{i}" in text)
        assert count >= 15, f"Expected at least 15 blockers, found {count}"

    def test_b1_through_b20_present(self):
        text = _read()
        for i in range(1, 21):
            assert f"B{i}" in text, f"B{i} not documented"


class TestCriticalBlockers:
    def test_h58_feature_flag_blocker_documented(self):
        text = _read()
        assert "B1" in text
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text

    def test_h58_tenant_leakage_blocker_documented(self):
        text = _read()
        assert "B5" in text
        assert "leakage" in text.lower() or "Tenant leakage" in text

    def test_h58_unbalanced_totals_blocker_documented(self):
        text = _read()
        assert "B6" in text
        assert "unbalanced" in text.lower() or "Unbalanced" in text

    def test_h58_auth_failure_blocker_documented(self):
        text = _read()
        assert "B14" in text
        assert "auth" in text.lower() or "401" in text

    def test_h58_secrets_exposed_blocker_documented(self):
        text = _read()
        assert "B15" in text
        assert "secret" in text.lower() or "Secret" in text


class TestProcessBlockers:
    def test_h58_missing_signoff_blocker_documented(self):
        text = _read()
        assert "B11" in text
        assert "sign" in text.lower()

    def test_h58_approval_expired_blocker_documented(self):
        text = _read()
        assert "B12" in text
        assert "expir" in text.lower()

    def test_h58_rollback_owner_missing_blocker(self):
        text = _read()
        assert "B9" in text
        assert "rollback owner" in text.lower()

    def test_h58_monitoring_owner_missing_blocker(self):
        text = _read()
        assert "B10" in text
        assert "monitoring owner" in text.lower()

    def test_h58_incident_response_blocker(self):
        text = _read()
        assert "B20" in text
        assert "incident" in text.lower()


class TestIntegrityBlockers:
    def test_h58_runtime_code_changed_blocker_documented(self):
        text = _read()
        assert "B16" in text
        assert "code" in text.lower() or "SHA" in text

    def test_h58_migration_sql_changed_blocker(self):
        text = _read()
        assert "B17" in text
        assert "migration" in text.lower() or "Migration" in text

    def test_h58_fixture_json_changed_blocker(self):
        text = _read()
        assert "B18" in text
        assert "fixture" in text.lower() or "Fixture" in text

    def test_migration_hash_referenced(self):
        assert "F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA" in _read()

    def test_fixture_hash_referenced(self):
        assert "1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299" in _read()


class TestBlockerActions:
    def test_h58_blocker_actions_documented(self):
        text = _read()
        assert "Required Action" in text or "required action" in text.lower()

    def test_severity_documented(self):
        text = _read()
        assert "CRITICAL" in text
        assert "HIGH" in text

    def test_may_proceed_documented(self):
        text = _read()
        assert "May Proceed" in text or "may proceed" in text.lower()

    def test_no_proceed_for_critical(self):
        text = _read()
        assert "NO" in text


class TestCurrentBlockerAssessment:
    def test_current_assessment_documented(self):
        text = _read()
        assert "Current Assessment" in text or "current" in text.lower()

    def test_demo_mode_confirmed(self):
        assert "demo_mode" in _read()

    def test_live_sha_referenced(self):
        assert "c4fd6b9" in _read()

    def test_h53_comparison_referenced(self):
        text = _read()
        assert "0 mismatches" in text or "12/12" in text


class TestFinalBlockerStatus:
    def test_h58_final_blocker_status_documented(self):
        text = _read()
        assert "NO_GO_BLOCKERS_PENDING_REVIEW" in text or "NO_GO_BLOCKERS_CLEAR" in text

    def test_current_status_is_pending_review(self):
        assert "NO_GO_BLOCKERS_PENDING_REVIEW" in _read()

    def test_clear_option_documented(self):
        assert "NO_GO_BLOCKERS_CLEAR" in _read()

    def test_blocked_option_documented(self):
        assert "BLOCKED_BY_NO_GO" in _read()

    def test_clearance_process_documented(self):
        text = _read()
        assert "clearance" in text.lower() or "Clearance" in text or "clear" in text.lower()


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
