"""
Tests for docs/local-docker-postgres-dry-run-evidence-h52.md and
         docs/local-docker-postgres-dry-run-cleanup-h52.md (H52).

H52 evidence and cleanup docs record:
- Approval APPROVAL-2026-H50-001 signed by ROLANDI GELIKOSHVILI
- Container bridge-hub-h52-postgres removed
- Volume bridge-hub-h52-pgdata removed
- 52 synthetic rows loaded and verified
- No secrets committed
- Final decision: SUCCESS_LOCAL_DOCKER_POSTGRES_DRY_RUN_COMPLETE
No Docker SDK, no DB imports, no network, no subprocess in this test file.
"""

import os
import pytest

EVIDENCE_DOC = "docs/local-docker-postgres-dry-run-evidence-h52.md"
CLEANUP_DOC = "docs/local-docker-postgres-dry-run-cleanup-h52.md"
LOADER_PATH = "scripts/load_h52_synthetic_fixture_local_only.py"

EXPECTED_APPROVAL_ID = "APPROVAL-2026-H50-001"
EXPECTED_FIXTURE_SHA256 = "1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299"
EXPECTED_MIGRATION_SHA256 = "F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA"
FORBIDDEN_SECRETS = [
    "bridge_hub_h52_local_only",
]


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# --- tests ---

class TestDocumentsExist:
    def test_h52_evidence_doc_exists(self):
        assert os.path.exists(EVIDENCE_DOC), f"Expected {EVIDENCE_DOC}"

    def test_h52_cleanup_doc_exists(self):
        assert os.path.exists(CLEANUP_DOC), f"Expected {CLEANUP_DOC}"

    def test_h52_loader_script_exists(self):
        assert os.path.exists(LOADER_PATH), f"Expected {LOADER_PATH}"


class TestEvidenceApprovalId:
    def test_evidence_contains_approval_id(self):
        text = _read(EVIDENCE_DOC)
        assert EXPECTED_APPROVAL_ID in text

    def test_evidence_contains_approved_by(self):
        text = _read(EVIDENCE_DOC)
        assert "ROLANDI GELIKOSHVILI" in text

    def test_evidence_contains_expires_at(self):
        text = _read(EVIDENCE_DOC)
        assert "2026-05-25" in text


class TestEvidenceDockerContext:
    def test_evidence_contains_docker_context(self):
        text = _read(EVIDENCE_DOC)
        assert "desktop-linux" in text

    def test_evidence_contains_container_name(self):
        text = _read(EVIDENCE_DOC)
        assert "bridge-hub-h52-postgres" in text

    def test_evidence_contains_volume_name(self):
        text = _read(EVIDENCE_DOC)
        assert "bridge-hub-h52-pgdata" in text

    def test_evidence_remote_context_false(self):
        text = _read(EVIDENCE_DOC)
        assert "remote_context" in text and "false" in text.lower()

    def test_evidence_production_risk_false(self):
        text = _read(EVIDENCE_DOC)
        assert "production_risk" in text and "false" in text.lower()


class TestEvidenceLocalDbProof:
    def test_evidence_contains_local_db_proof(self):
        text = _read(EVIDENCE_DOC)
        assert "127.0.0.1" in text

    def test_evidence_contains_port_55432(self):
        text = _read(EVIDENCE_DOC)
        assert "55432" in text

    def test_evidence_db_host_is_local(self):
        text = _read(EVIDENCE_DOC)
        assert "127.0.0.1" in text or "localhost" in text

    def test_evidence_no_remote_db(self):
        text = _read(EVIDENCE_DOC)
        assert "NOT connected" in text or "not connected" in text.lower() or "NOT USED" in text or "NOT connect" in text


class TestEvidenceFixtureHash:
    def test_evidence_contains_fixture_hash(self):
        text = _read(EVIDENCE_DOC)
        assert EXPECTED_FIXTURE_SHA256 in text

    def test_evidence_fixture_type_synthetic(self):
        text = _read(EVIDENCE_DOC)
        assert "synthetic" in text.lower()

    def test_evidence_no_production_data(self):
        text = _read(EVIDENCE_DOC)
        assert "production_data" in text and "false" in text.lower()

    def test_evidence_row_counts_present(self):
        text = _read(EVIDENCE_DOC)
        assert "15" in text
        assert "33" in text
        assert "52" in text


class TestEvidenceMigrationHash:
    def test_evidence_contains_migration_hash(self):
        text = _read(EVIDENCE_DOC)
        assert EXPECTED_MIGRATION_SHA256 in text

    def test_evidence_migration_status_success(self):
        text = _read(EVIDENCE_DOC)
        assert "SUCCESS" in text or "success" in text.lower()

    def test_evidence_tables_created(self):
        text = _read(EVIDENCE_DOC)
        assert "journal_entry_headers" in text
        assert "journal_entry_lines" in text
        assert "journal_entry_sources" in text


class TestNoSecretStatement:
    def test_evidence_contains_no_secret_statement(self):
        text = _read(EVIDENCE_DOC)
        assert "no_secrets_committed" in text or "No secrets" in text or "not committed" in text.lower()

    def test_no_raw_password_committed(self):
        ev_text = _read(EVIDENCE_DOC)
        cl_text = _read(CLEANUP_DOC)
        for secret in FORBIDDEN_SECRETS:
            assert secret not in ev_text, f"Raw secret '{secret}' found in evidence doc"
            assert secret not in cl_text, f"Raw secret '{secret}' found in cleanup doc"

    def test_loader_no_raw_password_committed(self):
        loader_text = _read(LOADER_PATH)
        for secret in FORBIDDEN_SECRETS:
            assert secret not in loader_text, f"Raw secret '{secret}' found in loader script"


class TestCleanupStatus:
    def test_cleanup_status_documented(self):
        text = _read(CLEANUP_DOC)
        assert "Cleanup" in text

    def test_container_removed_documented(self):
        text = _read(CLEANUP_DOC)
        assert "bridge-hub-h52-postgres" in text
        assert "Completed" in text or "removed" in text.lower()

    def test_volume_removed_documented(self):
        text = _read(CLEANUP_DOC)
        assert "bridge-hub-h52-pgdata" in text
        assert "Completed" in text or "removed" in text.lower()

    def test_cleanup_complete_decision(self):
        text = _read(CLEANUP_DOC)
        assert "CLEANUP_COMPLETE" in text or "Completed" in text


class TestCleanupCommands:
    def test_cleanup_commands_documented(self):
        text = _read(CLEANUP_DOC)
        assert "docker stop" in text
        assert "docker rm" in text
        assert "docker volume rm" in text

    def test_cleanup_verification_documented(self):
        text = _read(CLEANUP_DOC)
        assert "absent" in text.lower() or "no container" in text.lower() or "no rows" in text.lower() or "Verified" in text


class TestNoRuntimeApiOrCloudRunMutation:
    def test_no_runtime_api_or_cloud_run_mutation(self):
        ev_text = _read(EVIDENCE_DOC)
        assert "no_cloud_run_env_mutation" in ev_text or "no Cloud Run" in ev_text
        assert "no_balance_ge_activation" in ev_text or "Balance.ge" in ev_text
        assert "no_posted_ledger_reports_enabled_in_production" in ev_text or "POSTED_LEDGER_REPORTS_ENABLED" in ev_text


class TestLoaderSafetyProperties:
    def test_loader_requires_guard_var(self):
        text = _read(LOADER_PATH)
        assert "H52_LOCAL_DRY_RUN" in text

    def test_loader_checks_localhost_only(self):
        text = _read(LOADER_PATH)
        assert "127.0.0.1" in text or "localhost" in text

    def test_loader_verifies_sha256(self):
        text = _read(LOADER_PATH)
        assert "SHA256" in text or "sha256" in text or "EXPECTED_SHA256" in text

    def test_loader_no_fastapi_import(self):
        text = _read(LOADER_PATH)
        lines = text.splitlines()
        _fapi = "from " + "fastapi"
        _app = "from " + "app."
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert _fapi not in stripped.lower(), f"FastAPI import in loader: {stripped}"
            assert _app not in stripped, f"App import in loader: {stripped}"

    def test_loader_no_external_network(self):
        text = _read(LOADER_PATH)
        lines = text.splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "import " + "requests" not in stripped
            assert "import " + "httpx" not in stripped


class TestNoForbiddenImports:
    def test_no_runtime_api_or_cloud_run_mutation(self):
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
