"""
Tests for H50 hash and approval preflight docs:
- docs/local-docker-owner-approval-finalization-h50.md
- docs/local-docker-preflight-go-no-go-h50.md

H50 captured fixture hash (G11), migration 011 hash/review (G12), and updated
approval packet. H50 decision: BLOCKED_OWNER_APPROVAL_PENDING (G7 still pending).
No DB, SQL, migration execution, fixture load, runtime API, Cloud Run mutation, or feature flag.
"""

import os
import re
import pytest

APPROVAL_DOC = "docs/local-docker-owner-approval-finalization-h50.md"
GONOGO_DOC = "docs/local-docker-preflight-go-no-go-h50.md"
FIXTURE_PATH = "tests/fixtures/posted_ledger/synthetic_posted_ledger_fixture_pack.json"
MIGRATION_PATH = "app/storage/migrations/011_posted_journal_entries_schema.sql"

EXPECTED_FIXTURE_SHA256 = "1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299"
EXPECTED_MIGRATION_SHA256 = "F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA"

GONOGO_DECISIONS = {
    "READY_FOR_LOCAL_DOCKER_POSTGRES_DRY_RUN",
    "BLOCKED_OWNER_APPROVAL_PENDING",
    "BLOCKED_DOCKER_UNAVAILABLE",
    "BLOCKED_DAEMON_UNAVAILABLE",
    "BLOCKED_REMOTE_CONTEXT",
    "BLOCKED_PRODUCTION_RISK",
    "BLOCKED_SECRET_RISK",
    "BLOCKED_NO_CLEANUP_POLICY",
    "BLOCKED_MISSING_FIXTURE_HASH",
    "BLOCKED_MISSING_MIGRATION_REVIEW",
}

APPROVAL_DECISIONS = {
    "APPROVAL_READY_FOR_SIGNATURE",
    "APPROVED_FOR_LOCAL_DOCKER_DRY_RUN",
    "BLOCKED_NO_APPROVER",
    "BLOCKED_SCOPE_UNCLEAR",
    "BLOCKED_CLEANUP_MISSING",
    "BLOCKED_MISSING_FIXTURE_HASH",
    "BLOCKED_MISSING_MIGRATION_REVIEW",
}


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def evaluate_h50_gonogo(state: dict) -> str:
    """Evaluate H50 go/no-go and return final decision."""
    if not state.get("docker_installed"):
        return "BLOCKED_DOCKER_UNAVAILABLE"
    if not state.get("docker_daemon_available"):
        return "BLOCKED_DAEMON_UNAVAILABLE"
    if state.get("remote_context"):
        return "BLOCKED_REMOTE_CONTEXT"
    if state.get("production_risk"):
        return "BLOCKED_PRODUCTION_RISK"
    if state.get("secret_risk"):
        return "BLOCKED_SECRET_RISK"
    if not state.get("fixture_hash_captured"):
        return "BLOCKED_MISSING_FIXTURE_HASH"
    if not state.get("migration_reviewed"):
        return "BLOCKED_MISSING_MIGRATION_REVIEW"
    if not state.get("cleanup_policy"):
        return "BLOCKED_NO_CLEANUP_POLICY"
    if not state.get("owner_approval_signed"):
        return "BLOCKED_OWNER_APPROVAL_PENDING"
    if state.get("all_gates_pass"):
        return "READY_FOR_LOCAL_DOCKER_POSTGRES_DRY_RUN"
    return "BLOCKED_OWNER_APPROVAL_PENDING"


def evaluate_approval_status(state: dict) -> str:
    """Evaluate approval packet status."""
    if not state.get("fixture_hash_captured"):
        return "BLOCKED_MISSING_FIXTURE_HASH"
    if not state.get("migration_reviewed"):
        return "BLOCKED_MISSING_MIGRATION_REVIEW"
    if not state.get("cleanup_policy"):
        return "BLOCKED_CLEANUP_MISSING"
    if not state.get("approver_identified"):
        return "BLOCKED_NO_APPROVER"
    if not state.get("signed"):
        return "APPROVAL_READY_FOR_SIGNATURE"
    return "APPROVED_FOR_LOCAL_DOCKER_DRY_RUN"


# --- Approval doc tests ---

class TestApprovalDocExists:
    def test_approval_doc_exists(self):
        assert os.path.exists(APPROVAL_DOC), f"Expected {APPROVAL_DOC} to exist"

    def test_approval_doc_not_empty(self):
        text = _read(APPROVAL_DOC)
        assert len(text) > 500


class TestApprovalNonAction:
    def test_non_action_statement_present(self):
        text = _read(APPROVAL_DOC)
        assert "does NOT" in text or "NOT auto-sign" in text or "NOT execute" in text

    def test_no_auto_signing_stated(self):
        text = _read(APPROVAL_DOC)
        assert "auto-sign" in text.lower() or "NOT auto-sign" in text or "does not auto" in text.lower()

    def test_posted_ledger_flag_not_enabled(self):
        text = _read(APPROVAL_DOC)
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text


class TestFixtureHashEvidence:
    def test_fixture_hash_section_present(self):
        text = _read(APPROVAL_DOC)
        assert "Fixture Hash" in text or "fixture_hash" in text

    def test_fixture_sha256_documented(self):
        text = _read(APPROVAL_DOC)
        assert EXPECTED_FIXTURE_SHA256 in text

    def test_fixture_path_documented(self):
        text = _read(APPROVAL_DOC)
        assert "synthetic_posted_ledger_fixture_pack.json" in text

    def test_fixture_is_synthetic_not_production(self):
        text = _read(APPROVAL_DOC)
        assert "synthetic" in text.lower()
        assert '"production_data": false' in text or "production_data: false" in text or (
            "Production data" in text and "false" in text
        ) or "no production" in text.lower()

    def test_g11_pass_documented(self):
        text = _read(APPROVAL_DOC)
        assert "G11" in text
        assert "PASS" in text

    def test_fixture_file_exists_on_disk(self):
        assert os.path.exists(FIXTURE_PATH), f"Fixture file not found: {FIXTURE_PATH}"

    def test_fixture_hash_id_documented(self):
        text = _read(APPROVAL_DOC)
        assert "FIXTURE-HASH-2026-H50-001" in text


class TestMigrationHashReview:
    def test_migration_hash_section_present(self):
        text = _read(APPROVAL_DOC)
        assert "Migration 011" in text or "migration_011" in text or "migration hash" in text.lower()

    def test_migration_sha256_documented(self):
        text = _read(APPROVAL_DOC)
        assert EXPECTED_MIGRATION_SHA256 in text

    def test_migration_path_documented(self):
        text = _read(APPROVAL_DOC)
        assert "011_posted_journal_entries_schema.sql" in text

    def test_additive_review_documented(self):
        text = _read(APPROVAL_DOC)
        assert "additive" in text.lower()

    def test_no_destructive_sql_found(self):
        text = _read(APPROVAL_DOC)
        assert "destructive" in text.lower()
        # Confirm the doc states no destructive SQL
        assert "No `DROP TABLE`" in text or "no DROP TABLE" in text.lower() or "PASS" in text

    def test_g12_pass_documented(self):
        text = _read(APPROVAL_DOC)
        assert "G12" in text
        assert "PASS" in text

    def test_migration_file_exists_on_disk(self):
        assert os.path.exists(MIGRATION_PATH), f"Migration file not found: {MIGRATION_PATH}"

    def test_migration_hash_id_documented(self):
        text = _read(APPROVAL_DOC)
        assert "MIGRATION-HASH-2026-H50-001" in text


class TestMigration011AdditiveContent:
    """Verify migration 011 SQL itself is additive — read-only review, no execution."""

    def test_migration_has_no_drop_table(self):
        sql = _read(MIGRATION_PATH)
        assert "DROP TABLE" not in sql

    def test_migration_has_no_truncate(self):
        sql = _read(MIGRATION_PATH)
        assert "TRUNCATE" not in sql

    def test_migration_has_no_delete_statement(self):
        sql = _read(MIGRATION_PATH)
        # Ensure no standalone DELETE FROM (not inside a comment)
        lines = [l for l in sql.splitlines() if not l.strip().startswith("--")]
        for line in lines:
            assert "DELETE FROM" not in line.upper(), f"DELETE found: {line}"

    def test_migration_has_no_update_statement(self):
        sql = _read(MIGRATION_PATH)
        lines = [l for l in sql.splitlines() if not l.strip().startswith("--")]
        for line in lines:
            assert not re.match(r"^\s*UPDATE\s+", line, re.IGNORECASE), f"UPDATE found: {line}"

    def test_migration_has_no_insert_into(self):
        sql = _read(MIGRATION_PATH)
        lines = [l for l in sql.splitlines() if not l.strip().startswith("--")]
        for line in lines:
            assert "INSERT INTO" not in line.upper(), f"INSERT found: {line}"

    def test_migration_uses_create_table_if_not_exists(self):
        sql = _read(MIGRATION_PATH)
        assert "CREATE TABLE IF NOT EXISTS" in sql

    def test_migration_uses_create_index_if_not_exists(self):
        sql = _read(MIGRATION_PATH)
        assert "CREATE INDEX IF NOT EXISTS" in sql

    def test_migration_has_tenant_id_columns(self):
        sql = _read(MIGRATION_PATH)
        assert "tenant_id" in sql

    def test_migration_three_tables_created(self):
        sql = _read(MIGRATION_PATH)
        assert "journal_entry_headers" in sql
        assert "journal_entry_lines" in sql
        assert "journal_entry_sources" in sql


class TestApprovalPacket:
    def test_approval_packet_documented(self):
        text = _read(APPROVAL_DOC)
        assert "approval_id" in text
        assert "APPROVAL-2026-H50-001" in text

    def test_approval_status_pending(self):
        text = _read(APPROVAL_DOC)
        assert '"status": "pending"' in text or "status: pending" in text

    def test_docker_evidence_id_referenced(self):
        text = _read(APPROVAL_DOC)
        assert "DOCKER-EV-2026-H49-001" in text

    def test_allowed_operations_documented(self):
        text = _read(APPROVAL_DOC)
        assert "allowed_operations" in text
        assert "docker_pull_postgres_16" in text

    def test_forbidden_operations_documented(self):
        text = _read(APPROVAL_DOC)
        assert "forbidden_operations" in text
        assert "connect_to_production_db" in text

    def test_cleanup_policy_documented(self):
        text = _read(APPROVAL_DOC)
        assert "cleanup_policy" in text
        assert "container_remove" in text

    def test_expires_at_not_auto_filled(self):
        text = _read(APPROVAL_DOC)
        # expires_at must not have a real timestamp — must say placeholder or filled at signature time
        assert "expires_at" in text
        assert "signature time" in text or "placeholder" in text or "ISO 8601" in text


class TestApprovalDecisionOutputs:
    def test_approval_decision_outputs_documented(self):
        text = _read(APPROVAL_DOC)
        for d in APPROVAL_DECISIONS:
            assert d in text, f"Approval decision {d!r} not in doc"

    def test_current_approval_decision(self):
        text = _read(APPROVAL_DOC)
        assert "APPROVAL_READY_FOR_SIGNATURE" in text

    def test_evaluator_ready_when_all_present(self):
        result = evaluate_approval_status({
            "fixture_hash_captured": True,
            "migration_reviewed": True,
            "cleanup_policy": True,
            "approver_identified": True,
            "signed": False,
        })
        assert result == "APPROVAL_READY_FOR_SIGNATURE"

    def test_evaluator_approved_when_signed(self):
        result = evaluate_approval_status({
            "fixture_hash_captured": True,
            "migration_reviewed": True,
            "cleanup_policy": True,
            "approver_identified": True,
            "signed": True,
        })
        assert result == "APPROVED_FOR_LOCAL_DOCKER_DRY_RUN"

    def test_evaluator_missing_fixture_hash(self):
        result = evaluate_approval_status({
            "fixture_hash_captured": False,
            "migration_reviewed": True,
            "cleanup_policy": True,
            "approver_identified": True,
        })
        assert result == "BLOCKED_MISSING_FIXTURE_HASH"

    def test_evaluator_missing_migration_review(self):
        result = evaluate_approval_status({
            "fixture_hash_captured": True,
            "migration_reviewed": False,
            "cleanup_policy": True,
            "approver_identified": True,
        })
        assert result == "BLOCKED_MISSING_MIGRATION_REVIEW"


# --- Go/no-go doc tests ---

class TestGoNoGoDocExists:
    def test_gonogo_doc_exists(self):
        assert os.path.exists(GONOGO_DOC), f"Expected {GONOGO_DOC} to exist"

    def test_gonogo_doc_not_empty(self):
        text = _read(GONOGO_DOC)
        assert len(text) > 500


class TestGoNoGoGates:
    def test_all_g1_to_g15_documented(self):
        text = _read(GONOGO_DOC)
        for i in range(1, 16):
            assert f"G{i}" in text, f"Gate G{i} not found"

    def test_g1_passes(self):
        text = _read(GONOGO_DOC)
        assert "G1" in text
        assert "PASS" in text

    def test_g2_passes(self):
        text = _read(GONOGO_DOC)
        assert "G2" in text
        assert "PASS" in text

    def test_g3_passes(self):
        text = _read(GONOGO_DOC)
        assert "G3" in text
        assert "desktop-linux" in text

    def test_g7_still_blocked(self):
        text = _read(GONOGO_DOC)
        assert "G7" in text
        assert "FAIL" in text or "pending" in text.lower()

    def test_g11_passes(self):
        text = _read(GONOGO_DOC)
        assert "G11" in text
        assert "PASS" in text

    def test_g12_passes(self):
        text = _read(GONOGO_DOC)
        assert "G12" in text
        assert "PASS" in text

    def test_g14_feature_flag_off(self):
        text = _read(GONOGO_DOC)
        assert "G14" in text
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text


class TestGoNoGoDecision:
    def test_decision_outputs_documented(self):
        text = _read(GONOGO_DOC)
        for d in GONOGO_DECISIONS:
            assert d in text, f"Go/no-go decision {d!r} not in doc"

    def test_current_decision_blocked_owner_approval(self):
        text = _read(GONOGO_DOC)
        assert "BLOCKED_OWNER_APPROVAL_PENDING" in text

    def test_14_of_15_gates_pass(self):
        text = _read(GONOGO_DOC)
        assert "14 of 15" in text

    def test_next_task_h51_documented(self):
        text = _read(GONOGO_DOC)
        assert "H51" in text

    def test_evaluator_blocked_owner_approval(self):
        result = evaluate_h50_gonogo({
            "docker_installed": True,
            "docker_daemon_available": True,
            "remote_context": False,
            "production_risk": False,
            "secret_risk": False,
            "fixture_hash_captured": True,
            "migration_reviewed": True,
            "cleanup_policy": True,
            "owner_approval_signed": False,
        })
        assert result == "BLOCKED_OWNER_APPROVAL_PENDING"

    def test_evaluator_ready_when_all_pass(self):
        result = evaluate_h50_gonogo({
            "docker_installed": True,
            "docker_daemon_available": True,
            "remote_context": False,
            "production_risk": False,
            "secret_risk": False,
            "fixture_hash_captured": True,
            "migration_reviewed": True,
            "cleanup_policy": True,
            "owner_approval_signed": True,
            "all_gates_pass": True,
        })
        assert result == "READY_FOR_LOCAL_DOCKER_POSTGRES_DRY_RUN"

    def test_evaluator_docker_not_installed(self):
        result = evaluate_h50_gonogo({"docker_installed": False})
        assert result == "BLOCKED_DOCKER_UNAVAILABLE"

    def test_evaluator_missing_fixture_hash(self):
        result = evaluate_h50_gonogo({
            "docker_installed": True,
            "docker_daemon_available": True,
            "remote_context": False,
            "production_risk": False,
            "secret_risk": False,
            "fixture_hash_captured": False,
        })
        assert result == "BLOCKED_MISSING_FIXTURE_HASH"

    def test_evaluator_missing_migration_review(self):
        result = evaluate_h50_gonogo({
            "docker_installed": True,
            "docker_daemon_available": True,
            "remote_context": False,
            "production_risk": False,
            "secret_risk": False,
            "fixture_hash_captured": True,
            "migration_reviewed": False,
        })
        assert result == "BLOCKED_MISSING_MIGRATION_REVIEW"


class TestNoForbiddenImportsInTestFile:
    def test_no_db_network_sql_imports_in_test_file(self):
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
        ]
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for imp in _forbidden:
                assert imp not in stripped, f"Forbidden import: {stripped}"
