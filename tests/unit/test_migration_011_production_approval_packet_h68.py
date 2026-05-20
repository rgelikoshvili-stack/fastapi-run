"""tests/unit/test_migration_011_production_approval_packet_h68.py

Contract tests for 11C-H68 — Migration 011 Production Approval Packet.
No network, no DB, no app imports.
"""
import pathlib
import re
import pytest

DOC = pathlib.Path(__file__).parents[2] / "docs" / "migration-011-production-approval-packet-h68.md"


@pytest.fixture(scope="module")
def doc():
    return DOC.read_text(encoding="utf-8")


class TestDocumentExists:
    def test_approval_packet_doc_exists(self):
        assert DOC.exists()

    def test_approval_packet_not_empty(self, doc):
        assert len(doc) > 400

    def test_task_reference(self, doc):
        assert "11C-H68" in doc

    def test_approval_id_present(self, doc):
        assert "APPROVAL-2026-H68-001" in doc


class TestApprovalScope:
    def test_scope_documented(self, doc):
        assert "production_migration_011_execution_only" in doc

    def test_migration_path_documented(self, doc):
        assert "011_posted_journal_entries_schema.sql" in doc

    def test_sha256_documented(self, doc):
        assert "3077cec4c3d87fc0167ba02f70b13dcff871c1ce031b6fd0644d32554b3235d0" in doc

    def test_environment_production(self, doc):
        assert "production" in doc

    def test_additive_only_noted(self, doc):
        assert "additive" in doc.lower()

    def test_no_destructive_sql_confirmed(self, doc):
        assert "None" in doc or "no destructive" in doc.lower() or "Not found" in doc


class TestBusinessJustification:
    def test_justification_documented(self, doc):
        assert "Business Justification" in doc or "business justification" in doc.lower() or "Justification" in doc

    def test_posted_ledger_purpose_documented(self, doc):
        assert "posted-ledger" in doc.lower() or "Posted-ledger" in doc or "posted ledger" in doc.lower()

    def test_missing_tables_impact_documented(self, doc):
        assert "POSTED_LEDGER_UNAVAILABLE" in doc


class TestRequiredApprovals:
    def test_engineering_approval_slot(self, doc):
        assert "Engineering Owner" in doc or "Engineering owner" in doc

    def test_accounting_approval_slot(self, doc):
        assert "Accounting Owner" in doc or "Accounting owner" in doc

    def test_rollback_approval_slot(self, doc):
        assert "Rollback Owner" in doc or "Rollback owner" in doc

    def test_monitoring_approval_slot(self, doc):
        assert "Monitoring Owner" in doc or "Monitoring owner" in doc

    def test_all_approvals_pending(self, doc):
        assert "PENDING" in doc

    def test_signatures_required(self, doc):
        assert "Signature" in doc or "signature" in doc.lower()


class TestPrerequisiteConfirmation:
    def test_backup_pitr_prerequisite(self, doc):
        assert "PITR" in doc or "backup" in doc.lower()

    def test_dry_run_prerequisite(self, doc):
        assert "dry-run" in doc.lower() or "dry run" in doc.lower() or "Staging" in doc

    def test_maintenance_window_prerequisite(self, doc):
        assert "Maintenance window" in doc or "maintenance window" in doc.lower()

    def test_credentials_vault_documented(self, doc):
        assert "vault" in doc.lower() or "secret" in doc.lower() or "redact" in doc.lower()


class TestExecutionAuthorization:
    def test_execution_authorization_section(self, doc):
        assert "EXECUTION AUTHORIZED" in doc or "Execution Authorization" in doc

    def test_h69_referenced(self, doc):
        assert "H69" in doc

    def test_h69_blocked_until_signed(self, doc):
        # Must state H69 is blocked until packet is signed
        assert "signed" in doc.lower() or "prerequisites are met" in doc.lower()


class TestH68Decision:
    def test_approval_decision_documented(self, doc):
        assert "APPROVAL_READY_FOR_SIGNATURE_AFTER_BACKUP_AND_DRY_RUN" in doc

    def test_packet_status_pending(self, doc):
        assert "PENDING" in doc

    def test_no_production_sql(self, doc):
        assert "No production SQL" in doc or "No SQL executed" in doc or "no production SQL" in doc.lower()


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
