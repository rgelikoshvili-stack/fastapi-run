"""
Tests for docs/authenticated-report-deep-check-completion-h65b.md (H65B).
No Docker, no DB, no network — pure doc content verification.
"""
import os

DOC_PATH = "docs/authenticated-report-deep-check-completion-h65b.md"


def _read():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_h65b_doc_exists(self):
        assert os.path.exists(DOC_PATH)

    def test_h65b_doc_not_empty(self):
        assert len(_read()) > 500

    def test_h65b_purpose_documented(self):
        assert "Purpose" in _read()


class TestAuthTokenStatus:
    def test_token_not_committed(self):
        text = _read()
        assert "NO" in text
        assert "committed" in text.lower()

    def test_token_validity_confirmed(self):
        text = _read()
        assert "ok: true" in text.lower() or "ok:true" in text.lower() or "/auth/me" in text


class TestEndpointResults:
    def test_trial_balance_result_documented(self):
        text = _read()
        assert "trial-balance" in text
        assert "POSTED_LEDGER_UNAVAILABLE" in text

    def test_balance_sheet_result_documented(self):
        text = _read()
        assert "balance-sheet" in text

    def test_root_cause_documented(self):
        text = _read()
        assert "journal_entry_lines" in text

    def test_no_5xx_documented(self):
        text = _read()
        assert "5xx" in text.lower() or "500" in text


class TestM6TenantLeakage:
    def test_m6_decision_documented(self):
        assert "TENANT_LEAKAGE_DEEP_CHECK_PASS" in _read()

    def test_m6_unauthenticated_401_confirmed(self):
        text = _read()
        assert "401" in text

    def test_m6_no_cross_tenant_data(self):
        text = _read()
        assert "cross-tenant" in text.lower() or "leakage" in text.lower()


class TestM7ReportMismatch:
    def test_m7_decision_documented(self):
        assert "REPORT_MISMATCH_DEEP_CHECK_BLOCKED_NO_REPORT_DATA" in _read()

    def test_h53_baseline_referenced(self):
        text = _read()
        assert "H53" in text
        assert "14,480" in text or "34,469" in text

    def test_graceful_degradation_documented(self):
        text = _read()
        assert "graceful" in text.lower()


class TestRollbackAssessment:
    def test_rollback_not_required(self):
        text = _read()
        assert "Rollback required: NO" in text or "NO" in text

    def test_no_rollback_triggers_fired(self):
        text = _read()
        assert "NO ✅" in text or "no rollback" in text.lower()


class TestKeyFinding:
    def test_db_migration_finding_documented(self):
        text = _read()
        assert "journal_entry_lines" in text
        assert "migrat" in text.lower()

    def test_flag_enabled_confirmed(self):
        text = _read()
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text
        assert "true" in text


class TestUpdatedDecisions:
    def test_h65b_final_decision_documented(self):
        assert "AUTHENTICATED_REPORT_ENDPOINT_VERIFICATION_PASS_WITH_LIMITATIONS" in _read()

    def test_m6_updated_decision(self):
        assert "TENANT_LEAKAGE_DEEP_CHECK_PASS" in _read()

    def test_m7_updated_decision(self):
        assert "REPORT_MISMATCH_DEEP_CHECK_BLOCKED_NO_REPORT_DATA" in _read()

    def test_previous_blocked_decisions_referenced(self):
        text = _read()
        assert "BLOCKED_AUTH_TOKEN_MISSING" in text or "H65" in text


class TestNextTask:
    def test_next_task_documented(self):
        text = _read()
        assert "H66" in text
        assert "migrat" in text.lower()


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
