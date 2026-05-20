"""tests/unit/test_migration_011_approval_signatures_h69_pre.py

Contract tests for 11C-H69-PRE-R2 — Migration 011 Approval Signatures.
No network, no DB, no app imports.
"""
import pathlib
import re
import pytest

DOC = pathlib.Path(__file__).parents[2] / "docs" / "migration-011-approval-signatures-h69-pre.md"


@pytest.fixture(scope="module")
def doc():
    return DOC.read_text(encoding="utf-8")


class TestDocumentExists:
    def test_approval_signatures_doc_exists(self):
        assert DOC.exists()

    def test_approval_signatures_doc_not_empty(self, doc):
        assert len(doc) > 400

    def test_task_reference(self, doc):
        assert "11C-H69-PRE-R2" in doc


class TestApprovalPacketReference:
    def test_approval_id_present(self, doc):
        assert "APPROVAL-2026-H68-001" in doc

    def test_scope_documented(self, doc):
        assert "production_migration_011_execution_only" in doc

    def test_sha256_present(self, doc):
        assert "3077cec4c3d87fc0167ba02f70b13dcff871c1ce031b6fd0644d32554b3235d0" in doc

    def test_review_decision_referenced(self, doc):
        assert "MIGRATION_011_REVIEW_PASS_ADDITIVE" in doc

    def test_rollback_plan_referenced(self, doc):
        assert "ROLLBACK_PLAN_READY_RESTORE_BASED" in doc

    def test_dry_run_decision_referenced(self, doc):
        assert "DRY_RUN_ALREADY_PASSED_WITH_EVIDENCE" in doc


class TestRequiredSignatureSlots:
    def test_engineering_owner_slot(self, doc):
        assert "Engineering Owner" in doc or "Engineering owner" in doc

    def test_accounting_owner_slot(self, doc):
        assert "Accounting Owner" in doc or "Accounting owner" in doc

    def test_rollback_owner_slot(self, doc):
        assert "Rollback Owner" in doc or "Rollback owner" in doc

    def test_monitoring_owner_slot(self, doc):
        assert "Monitoring Owner" in doc or "Monitoring owner" in doc

    def test_all_pending(self, doc):
        assert doc.count("PENDING") >= 4

    def test_signature_fields_present(self, doc):
        assert "Signature" in doc


class TestRequiredConfirmations:
    def test_no_fixture_load_confirmation(self, doc):
        assert "fixture" in doc.lower() or "no fixture" in doc.lower()

    def test_no_balance_activation_confirmation(self, doc):
        assert "Balance.ge" in doc and "NOT" in doc or \
               "balance.ge" in doc.lower() and "not" in doc.lower()

    def test_restore_based_rollback_confirmation(self, doc):
        assert "restore-based" in doc.lower() or "restore based" in doc.lower()

    def test_no_concurrent_deploy_confirmation(self, doc):
        assert "concurrent" in doc.lower()

    def test_maintenance_window_referenced(self, doc):
        assert "maintenance window" in doc.lower() or "Maintenance window" in doc

    def test_monitoring_window_referenced(self, doc):
        assert "monitoring" in doc.lower()


class TestGateDecision:
    def test_blocked_decision_present(self, doc):
        assert "BLOCKED_APPROVAL_SIGNATURE_MISSING" in doc

    def test_approval_packet_signed_in_closure_instructions(self, doc):
        assert "APPROVAL_PACKET_SIGNED" in doc

    def test_h69_blocked_stated(self, doc):
        assert "H69" in doc
        assert "BLOCKED" in doc or "NOT begin" in doc

    def test_no_production_sql(self, doc):
        assert "No SQL executed" in doc or "No production SQL" in doc or \
               "no production SQL" in doc.lower()


class TestNoForbiddenPatterns:
    def test_no_raw_database_url(self, doc):
        assert "postgresql://" not in doc

    def test_no_production_password(self, doc):
        assert "BridgeHub" + "2026x" not in doc

    def test_no_raw_jwt(self, doc):
        assert not re.search(r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}', doc)

    def test_no_posting_apply(self, doc):
        assert "posting/" + "apply" not in doc

    def test_no_gcloud_mutation(self, doc):
        assert "gcloud run services update" not in doc

    def test_no_balance_activation(self, doc):
        assert "BALANCE_API_KEY=sk" not in doc


class TestNoForbiddenImports:
    def test_no_forbidden_imports(self):
        with open(__file__, encoding="utf-8") as fh:
            lines = fh.readlines()
        forbidden = [
            "import " + "psycopg", "import " + "sqlalchemy",
            "import " + "requests", "import " + "httpx",
            "import " + "socket", "import " + "subprocess",
            "from " + "app.", "from docker" + " import",
        ]
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pat in forbidden:
                assert pat not in stripped, f"Forbidden: {pat!r} in {stripped!r}"
