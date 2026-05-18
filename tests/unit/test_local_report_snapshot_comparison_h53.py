"""
Tests for docs/local-report-snapshot-comparison-h53.md (H53).
Also covers docs/local-comparison-cleanup-h53-h57.md.
No Docker, no DB, no network — pure doc content verification.
"""
import os
import pytest

COMPARISON_DOC = "docs/local-report-snapshot-comparison-h53.md"
CLEANUP_DOC    = "docs/local-comparison-cleanup-h53-h57.md"
CAPTURE_DOC    = "docs/local-report-snapshot-capture-h53.md"

FIXTURE_SHA   = "1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299"
MIGRATION_SHA = "F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA"


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestDocumentsExist:
    def test_comparison_doc_exists(self):
        assert os.path.exists(COMPARISON_DOC)

    def test_cleanup_doc_exists(self):
        assert os.path.exists(CLEANUP_DOC)

    def test_capture_doc_exists(self):
        assert os.path.exists(CAPTURE_DOC)


class TestComparisonInput:
    def test_comparison_id_documented(self):
        assert "H53-COMPARISON-2026-001" in _read(COMPARISON_DOC)

    def test_fixture_sha_documented(self):
        assert FIXTURE_SHA in _read(COMPARISON_DOC)

    def test_migration_sha_documented(self):
        assert MIGRATION_SHA in _read(COMPARISON_DOC)

    def test_db_target_documented(self):
        text = _read(COMPARISON_DOC)
        assert "127.0.0.1" in text
        assert "55433" in text

    def test_approval_id_documented(self):
        assert "APPROVAL-2026-H50-001" in _read(COMPARISON_DOC)


class TestCapturedReports:
    def test_reports_count_documented(self):
        text = _read(COMPARISON_DOC)
        assert "12" in text

    def test_standard_net_volume_documented(self):
        assert "23,945.00" in _read(COMPARISON_DOC)

    def test_pl_documented(self):
        text = _read(COMPARISON_DOC)
        assert "2,300.00" in text
        assert "3,525.00" in text
        assert "-1,225.00" in text

    def test_balance_sheet_documented(self):
        text = _read(COMPARISON_DOC)
        assert "10,955.00" in text
        assert "2,180.00" in text

    def test_vat_documented(self):
        text = _read(COMPARISON_DOC)
        assert "180.00" in text
        assert "VAT" in text


class TestMismatchClassifier:
    def test_mismatch_classifier_documented(self):
        assert "Mismatch" in _read(COMPARISON_DOC)

    def test_severity_levels_documented(self):
        text = _read(COMPARISON_DOC)
        assert "critical" in text.lower()
        assert "high" in text.lower()
        assert "medium" in text.lower()
        assert "low" in text.lower()

    def test_zero_mismatches(self):
        text = _read(COMPARISON_DOC)
        assert "Total mismatches: 0" in text or '"total_mismatches": 0' in text or "reports_failed: 0" in text


class TestSeverityCounts:
    def test_severity_counts_documented(self):
        text = _read(COMPARISON_DOC)
        assert "severity_counts" in text or "Severity" in text

    def test_all_zero(self):
        text = _read(COMPARISON_DOC)
        assert '"critical": 0' in text or "critical | 0" in text


class TestTenantLeakageCheck:
    def test_tenant_leakage_documented(self):
        text = _read(COMPARISON_DOC)
        assert "leakage" in text.lower() or "isolation" in text.lower()

    def test_tenant_beta_isolation(self):
        text = _read(COMPARISON_DOC)
        assert "tenant_beta" in text
        assert "leakage" in text.lower() or "isolated" in text.lower() or "absent" in text.lower()

    def test_no_cross_tenant_leakage(self):
        text = _read(COMPARISON_DOC)
        assert "No cross-tenant" in text or "no cross-tenant" in text.lower()


class TestFinalComparisonDecision:
    def test_decision_documented(self):
        assert "SUCCESS_LOCAL_REPORT_SNAPSHOT_COMPARISON_PASS" in _read(COMPARISON_DOC)

    def test_reports_passed_documented(self):
        text = _read(COMPARISON_DOC)
        assert "12" in text and "PASS" in text

    def test_next_phase_h54(self):
        assert "H54" in _read(COMPARISON_DOC)


class TestCleanupComplete:
    def test_cleanup_decision_documented(self):
        assert "CLEANUP_COMPLETE" in _read(CLEANUP_DOC)

    def test_container_removed(self):
        text = _read(CLEANUP_DOC)
        assert "bridge-hub-h53-postgres" in text
        assert "Completed" in text or "removed" in text.lower()

    def test_volume_removed(self):
        text = _read(CLEANUP_DOC)
        assert "bridge-hub-h53-pgdata" in text
        assert "Completed" in text or "removed" in text.lower()

    def test_verification_documented(self):
        text = _read(CLEANUP_DOC)
        assert "absent" in text.lower()

    def test_no_db_remains(self):
        text = _read(CLEANUP_DOC)
        assert "removed" in text.lower() or "absent" in text.lower()

    def test_h54_h57_no_docker(self):
        text = _read(CLEANUP_DOC)
        assert "H54" in text and "H55" in text and "H56" in text and "H57" in text


class TestNoRawPassword:
    def test_no_raw_password_in_docs(self):
        for path in [COMPARISON_DOC, CLEANUP_DOC, CAPTURE_DOC]:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            assert "bridge_hub_h53_local_only" not in content, f"Raw password in {path}"

    def test_no_raw_password_in_helper(self):
        helper = "scripts/capture_h53_local_report_snapshots.py"
        if not os.path.exists(helper):
            pytest.skip("Helper not present")
        with open(helper, encoding="utf-8") as f:
            content = f.read()
        assert "bridge_hub_h53_local_only" not in content


class TestNoRuntimeApiOrCloudRunMutation:
    def test_no_forbidden_production_content(self):
        for path in [COMPARISON_DOC, CLEANUP_DOC]:
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
            forbidden = [
                "POSTED_LEDGER_REPORTS_ENABLED=true",
                "POSTED_LEDGER_REPORTS_ENABLED=1",
                "gcloud run services update",
            ]
            for line in lines:
                for needle in forbidden:
                    assert needle not in line, f"Forbidden content in {path}: {line.strip()}"

    def test_helper_safety(self):
        helper = "scripts/capture_h53_local_report_snapshots.py"
        if not os.path.exists(helper):
            pytest.skip("Helper not present")
        with open(helper, encoding="utf-8") as f:
            content = f.read()
        assert "H53_LOCAL_DRY_RUN" in content
        assert "ALLOWED_HOSTS" in content
        assert "55433" in content
        assert "sha256" in content.lower() or "SHA256" in content

    def test_helper_no_app_import(self):
        helper = "scripts/capture_h53_local_report_snapshots.py"
        if not os.path.exists(helper):
            pytest.skip("Helper not present")
        with open(helper, encoding="utf-8") as f:
            lines = f.readlines()
        _fapi = "from " + "fastapi"
        _app  = "from " + "app."
        for line in lines:
            s = line.strip()
            if s.startswith("#"): continue
            assert _fapi not in s.lower(), f"FastAPI import: {s}"
            assert _app not in s, f"App import: {s}"


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
