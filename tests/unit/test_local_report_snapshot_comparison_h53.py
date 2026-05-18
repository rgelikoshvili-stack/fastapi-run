"""
Tests for docs/local-report-snapshot-comparison-h53.md (H53).
Also tests docs/local-report-snapshot-cleanup-h53.md.

H53 compares local report snapshots against expected_reports in the approved
synthetic fixture. Decision: SUCCESS_LOCAL_REPORT_SNAPSHOT_COMPARISON_PASS.
No production DB. No Cloud Run mutation. No feature flag.
"""

import os
import pytest

COMPARISON_DOC = "docs/local-report-snapshot-comparison-h53.md"
CLEANUP_DOC    = "docs/local-report-snapshot-cleanup-h53.md"
CAPTURE_DOC    = "docs/local-report-snapshot-capture-h53.md"

EXPECTED_FIXTURE_SHA256   = "1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299"
EXPECTED_MIGRATION_SHA256 = "F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA"


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestDocumentsExist:
    def test_h53_comparison_doc_exists(self):
        assert os.path.exists(COMPARISON_DOC), f"Expected {COMPARISON_DOC} to exist"

    def test_h53_cleanup_doc_exists(self):
        assert os.path.exists(CLEANUP_DOC), f"Expected {CLEANUP_DOC} to exist"

    def test_h53_capture_doc_exists(self):
        assert os.path.exists(CAPTURE_DOC), f"Expected {CAPTURE_DOC} to exist"

    def test_h53_comparison_doc_not_empty(self):
        text = _read(COMPARISON_DOC)
        assert len(text) > 500

    def test_h53_cleanup_doc_not_empty(self):
        text = _read(CLEANUP_DOC)
        assert len(text) > 200


class TestComparisonInput:
    def test_comparison_input_documented(self):
        text = _read(COMPARISON_DOC)
        assert "H53-COMPARISON-2026-001" in text or "comparison_id" in text

    def test_fixture_sha_in_comparison(self):
        text = _read(COMPARISON_DOC)
        assert EXPECTED_FIXTURE_SHA256 in text

    def test_migration_sha_in_comparison(self):
        text = _read(COMPARISON_DOC)
        assert EXPECTED_MIGRATION_SHA256 in text

    def test_db_target_in_comparison(self):
        text = _read(COMPARISON_DOC)
        assert "127.0.0.1" in text
        assert "55433" in text

    def test_approval_id_in_comparison(self):
        text = _read(COMPARISON_DOC)
        assert "APPROVAL-2026-H50-001" in text


class TestExpectedReportSource:
    def test_expected_report_source_documented(self):
        text = _read(COMPARISON_DOC)
        assert "expected_reports" in text or "expected report" in text.lower()

    def test_standard_net_filter_documented(self):
        text = _read(COMPARISON_DOC)
        assert "posted" in text
        assert "correction" in text

    def test_tenant_alpha_filter_documented(self):
        text = _read(COMPARISON_DOC)
        assert "tenant_alpha" in text


class TestCapturedReports:
    def test_captured_reports_documented(self):
        text = _read(COMPARISON_DOC)
        assert "reports_compared" in text or "Reports Compared" in text
        assert "7" in text

    def test_trial_balance_comparison_documented(self):
        text = _read(COMPARISON_DOC)
        assert "Trial Balance" in text or "trial_balance" in text
        assert "14,480.00" in text

    def test_total_volume_comparison_documented(self):
        text = _read(COMPARISON_DOC)
        assert "23,945.00" in text

    def test_pl_comparison_documented(self):
        text = _read(COMPARISON_DOC)
        assert "2,300.00" in text
        assert "3,525.00" in text
        assert "-1,225.00" in text

    def test_balance_sheet_comparison_documented(self):
        text = _read(COMPARISON_DOC)
        assert "10,955.00" in text
        assert "2,180.00" in text
        assert "8,775.00" in text

    def test_vat_comparison_documented(self):
        text = _read(COMPARISON_DOC)
        assert "180.00" in text
        assert "VAT" in text or "vat" in text.lower()


class TestMismatchClassifier:
    def test_mismatch_classifier_documented(self):
        text = _read(COMPARISON_DOC)
        assert "Mismatch" in text or "mismatch" in text.lower()

    def test_severity_levels_documented(self):
        text = _read(COMPARISON_DOC)
        assert "critical" in text.lower()
        assert "high" in text.lower()
        assert "medium" in text.lower()
        assert "low" in text.lower()

    def test_zero_mismatches_documented(self):
        text = _read(COMPARISON_DOC)
        assert "Total mismatches: 0" in text or '"total_mismatches": 0' in text or "0 mismatches" in text.lower()


class TestSeverityCounts:
    def test_severity_counts_documented(self):
        text = _read(COMPARISON_DOC)
        assert "severity_counts" in text or "Severity" in text

    def test_all_severity_counts_zero(self):
        text = _read(COMPARISON_DOC)
        assert '"critical": 0' in text or "critical | 0" in text
        assert '"high": 0' in text or "high | 0" in text


class TestTenantLeakageCheck:
    def test_tenant_leakage_check_documented(self):
        text = _read(COMPARISON_DOC)
        assert "Tenant" in text or "tenant" in text.lower()
        assert "leakage" in text.lower() or "isolation" in text.lower()

    def test_tenant_beta_isolation_documented(self):
        text = _read(COMPARISON_DOC)
        assert "tenant_beta" in text
        assert "isolated" in text.lower() or "isolation" in text.lower() or "must not appear" in text.lower() or "NOT appear" in text

    def test_no_cross_tenant_leakage(self):
        text = _read(COMPARISON_DOC)
        assert "No cross-tenant" in text or "no cross-tenant" in text.lower() or "No tenant leakage" in text


class TestFinalComparisonDecision:
    def test_final_comparison_decision_documented(self):
        text = _read(COMPARISON_DOC)
        assert "SUCCESS_LOCAL_REPORT_SNAPSHOT_COMPARISON_PASS" in text

    def test_reports_passed_7_documented(self):
        text = _read(COMPARISON_DOC)
        assert "reports_passed: 7" in text or '"reports_passed": 7' in text or "7 of 7" in text

    def test_reports_failed_0_documented(self):
        text = _read(COMPARISON_DOC)
        assert "reports_failed: 0" in text or '"reports_failed": 0' in text

    def test_next_task_h54_documented(self):
        text = _read(COMPARISON_DOC)
        assert "H54" in text


class TestCleanupComplete:
    def test_cleanup_complete_documented(self):
        text = _read(CLEANUP_DOC)
        assert "CLEANUP_COMPLETE" in text

    def test_container_removed_documented(self):
        text = _read(CLEANUP_DOC)
        assert "bridge-hub-h53-postgres" in text
        assert "Completed" in text or "removed" in text.lower()

    def test_volume_removed_documented(self):
        text = _read(CLEANUP_DOC)
        assert "bridge-hub-h53-pgdata" in text
        assert "Completed" in text or "removed" in text.lower()

    def test_cleanup_verification_documented(self):
        text = _read(CLEANUP_DOC)
        assert "absent" in text.lower() or "no container" in text.lower()

    def test_no_db_remains(self):
        text = _read(CLEANUP_DOC)
        assert "No local DB remains" in text or "local DB" in text.lower()
        assert "removed" in text.lower() or "absent" in text.lower()


class TestNoRawPassword:
    def test_no_raw_password_committed(self):
        for path in [COMPARISON_DOC, CLEANUP_DOC, CAPTURE_DOC]:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "bridge_hub_h53_local_only" not in content, (
                f"Raw password found in {path}"
            )

    def test_helper_no_raw_password_committed(self):
        helper = "scripts/capture_h53_local_report_snapshots.py"
        if not os.path.exists(helper):
            pytest.skip("Helper not present")
        with open(helper, "r", encoding="utf-8") as f:
            content = f.read()
        assert "bridge_hub_h53_local_only" not in content, "Raw password found in helper"


class TestNoRuntimeApiOrCloudRunMutation:
    def test_no_runtime_api_or_cloud_run_mutation(self):
        for path in [COMPARISON_DOC, CLEANUP_DOC, CAPTURE_DOC]:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            _forbidden = [
                "POSTED_LEDGER_REPORTS_ENABLED=true",
                "POSTED_LEDGER_REPORTS_ENABLED=1",
                "gcloud run services update",
                "kubectl set env",
            ]
            for line in lines:
                for needle in _forbidden:
                    assert needle not in line, f"Forbidden content in {path}: {line.strip()}"

    def test_helper_safety_properties(self):
        helper = "scripts/capture_h53_local_report_snapshots.py"
        if not os.path.exists(helper):
            pytest.skip("Helper not present")
        with open(helper, "r", encoding="utf-8") as f:
            content = f.read()
        assert "H53_LOCAL_DRY_RUN" in content
        assert "ALLOWED_HOSTS" in content
        assert "55433" in content
        assert "sha256" in content.lower() or "SHA256" in content

    def test_helper_no_app_import(self):
        helper = "scripts/capture_h53_local_report_snapshots.py"
        if not os.path.exists(helper):
            pytest.skip("Helper not present")
        with open(helper, "r", encoding="utf-8") as f:
            lines = f.readlines()
        _fapi = "from " + "fastapi"
        _app  = "from " + "app."
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert _fapi not in stripped.lower(), f"FastAPI import in helper: {stripped}"
            assert _app not in stripped, f"App import in helper: {stripped}"

    def test_helper_no_external_network(self):
        helper = "scripts/capture_h53_local_report_snapshots.py"
        if not os.path.exists(helper):
            pytest.skip("Helper not present")
        with open(helper, "r", encoding="utf-8") as f:
            lines = f.readlines()
        _forbidden = [
            "import " + "requests",
            "import " + "httpx",
            "import " + "urllib.request",
            "import " + "socket",
        ]
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for imp in _forbidden:
                assert imp not in stripped, f"Forbidden import in helper: {stripped}"


class TestNoForbiddenImports:
    def test_no_db_docker_execution_imports(self):
        with open(__file__, "r", encoding="utf-8") as f:
            lines = f.readlines()
        _forbidden = [
            "import " + "psycopg",
            "import " + "sqlalchemy",
            "import " + "requests",
            "import " + "httpx",
            "import " + "socket",
            "import " + "subprocess",
            "from " + "app.",
            "from docker" + " import",
        ]
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for imp in _forbidden:
                assert imp not in stripped, f"Forbidden import: {stripped}"
