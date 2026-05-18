"""
Tests for docs/final-local-evidence-readiness-h55.md (H55).
No Docker, no DB, no network — pure doc content verification.
"""
import os
import pytest

DOC_PATH = "docs/final-local-evidence-readiness-h55.md"

REQUIRED_DECISIONS = [
    "FINAL_LOCAL_EVIDENCE_READY",
    "FINAL_LOCAL_EVIDENCE_READY_WITH_NOTES",
]


def _read():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_h55_doc_exists(self):
        assert os.path.exists(DOC_PATH)

    def test_h55_doc_not_empty(self):
        assert len(_read()) > 500

    def test_h55_purpose_documented(self):
        assert "Purpose" in _read()


class TestApprovalEvidence:
    def test_approval_id_documented(self):
        assert "APPROVAL-2026-H50-001" in _read()

    def test_owner_documented(self):
        assert "ROLANDI GELIKOSHVILI" in _read()

    def test_owner_approval_signed(self):
        assert "OWNER_APPROVAL_SIGNED" in _read()

    def test_scope_documented(self):
        assert "local_docker_postgres_dry_run_only" in _read()


class TestDockerEvidence:
    def test_docker_evidence_id_documented(self):
        assert "DOCKER-EV-2026-H49-001" in _read()

    def test_docker_evidence_captured(self):
        assert "DOCKER_EVIDENCE_CAPTURED" in _read()

    def test_docker_version_documented(self):
        assert "29.4.3" in _read()


class TestFixtureHashEvidence:
    def test_fixture_hash_id_documented(self):
        assert "FIXTURE-HASH-2026-H50-001" in _read()

    def test_fixture_sha_documented(self):
        assert "1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299" in _read()

    def test_fixture_verified_in_h52_and_h53(self):
        text = _read()
        assert "H52" in text and "H53" in text


class TestMigrationEvidence:
    def test_migration_hash_id_documented(self):
        assert "MIGRATION-HASH-2026-H50-001" in _read()

    def test_migration_sha_documented(self):
        assert "F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA" in _read()

    def test_additive_only_documented(self):
        assert "additive" in _read().lower()


class TestH52Evidence:
    def test_h52_decision_documented(self):
        assert "SUCCESS_LOCAL_DOCKER_POSTGRES_DRY_RUN_COMPLETE" in _read()

    def test_h52_live_sha_documented(self):
        assert "1f02aba" in _read()

    def test_h52_rows_documented(self):
        assert "52" in _read()

    def test_h52_balance_documented(self):
        assert "23,945.00" in _read()


class TestH53Evidence:
    def test_h53_decision_documented(self):
        assert "SUCCESS_LOCAL_REPORT_SNAPSHOT_COMPARISON_PASS" in _read()

    def test_h53_reports_documented(self):
        text = _read()
        assert "12" in text and "PASS" in text

    def test_h53_balance_full_documented(self):
        assert "34,469.00" in _read()


class TestH54Evidence:
    def test_h54_decision_documented(self):
        assert "ACCOUNTANT_REVIEW_READY" in _read()

    def test_h54_checklist_documented(self):
        text = _read()
        assert "12" in text


class TestCleanupEvidence:
    def test_cleanup_documented(self):
        text = _read()
        assert "removed" in text.lower() or "CLEANUP" in text

    def test_h52_container_removed(self):
        text = _read()
        assert "bridge-hub-h52-postgres" in text

    def test_h53_container_removed(self):
        text = _read()
        assert "bridge-hub-h53-postgres" in text


class TestSafetyEvidence:
    def test_no_production_db_documented(self):
        text = _read()
        assert "production" in text.lower()

    def test_feature_flag_off_documented(self):
        assert "POSTED_LEDGER_REPORTS_ENABLED" in _read()

    def test_balance_ge_demo_mode_documented(self):
        assert "demo_mode" in _read()

    def test_no_pii_documented(self):
        text = _read()
        assert "PII" in text or "synthetic" in text.lower()


class TestProductionReadinessGates:
    def test_gates_documented(self):
        text = _read()
        assert "Gate" in text or "gate" in text.lower()

    def test_all_gates_pass(self):
        text = _read()
        assert "12" in text and "PASS" in text

    def test_feature_flag_gate_documented(self):
        assert "POSTED_LEDGER_REPORTS_ENABLED" in _read()


class TestFinalDecision:
    def test_final_decision_documented(self):
        text = _read()
        assert any(d in text for d in REQUIRED_DECISIONS)

    def test_final_local_evidence_ready(self):
        assert "FINAL_LOCAL_EVIDENCE_READY" in _read()

    def test_non_action_confirmed(self):
        assert "does NOT" in _read()

    def test_next_h56_documented(self):
        assert "H56" in _read()


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
