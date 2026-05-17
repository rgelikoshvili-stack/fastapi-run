"""
Tests for docs/local-docker-owner-approval-packet.md (H43).

H43 defines the owner approval packet for local Docker PostgreSQL provisioning.
Current status: APPROVAL_PACKET_READY_PENDING_SIGNATURE.
Docker not installed (H41: BLOCKED_DOCKER_UNAVAILABLE).
No Docker, DB, SQL, migration, fixture, runtime API, Cloud Run mutation, or feature flag.
"""

import re
import os
import pytest

DOC_PATH = "docs/local-docker-owner-approval-packet.md"

DECISION_OUTPUTS = {
    "APPROVAL_PACKET_READY_PENDING_SIGNATURE",
    "APPROVED_FOR_LOCAL_DOCKER_DRY_RUN",
    "BLOCKED_NO_APPROVER",
    "BLOCKED_SCOPE_UNCLEAR",
    "BLOCKED_CLEANUP_MISSING",
    "BLOCKED_MISSING_H42_SANITIZATION",
}

REQUIRED_ALLOWED_OPS = [
    "docker_pull_postgres_16",
    "docker_run_disposable_container",
    "create_disposable_local_db",
    "run_migration_011_local_only",
    "load_synthetic_fixture_local_only",
    "cleanup_container_and_volume",
]

REQUIRED_FORBIDDEN_OPS = [
    "connect_to_production_db",
    "mutate_cloud_run_env_vars",
    "activate_balance_ge_live",
    "load_production_data",
    "commit_raw_secrets",
]

REQUIRED_PACKET_FIELDS = [
    "approval_id",
    "approved_by",
    "requested_by",
    "scope",
    "environment",
    "allowed_operations",
    "forbidden_operations",
    "cleanup_policy",
    "retention_policy",
    "expires_at",
    "status",
]

# --- helpers ---

def _read_doc():
    with open(DOC_PATH, "r", encoding="utf-8") as f:
        return f.read()

def evaluate_approval_packet(state: dict) -> str:
    """Evaluate H43 approval packet state and return decision."""
    if not state.get("h42_sanitized"):
        return "BLOCKED_MISSING_H42_SANITIZATION"
    if not state.get("cleanup_policy"):
        return "BLOCKED_CLEANUP_MISSING"
    if not state.get("approver"):
        return "BLOCKED_NO_APPROVER"
    if not state.get("scope_defined"):
        return "BLOCKED_SCOPE_UNCLEAR"
    if state.get("signed"):
        return "APPROVED_FOR_LOCAL_DOCKER_DRY_RUN"
    return "APPROVAL_PACKET_READY_PENDING_SIGNATURE"

def validate_approval_packet(packet: dict) -> list:
    """Validate an H43 approval packet. Returns list of errors."""
    errors = []
    for field in REQUIRED_PACKET_FIELDS:
        if field not in packet:
            errors.append(f"missing field: {field}")
    if packet.get("environment") != "local_only":
        errors.append("environment must be local_only")
    allowed = packet.get("allowed_operations", [])
    forbidden = packet.get("forbidden_operations", [])
    overlap = set(allowed) & set(forbidden)
    if overlap:
        errors.append(f"operations in both allowed and forbidden: {overlap}")
    if "connect_to_production_db" in allowed:
        errors.append("connect_to_production_db must not be in allowed_operations")
    if "mutate_cloud_run_env_vars" in allowed:
        errors.append("mutate_cloud_run_env_vars must not be in allowed_operations")
    conn = packet.get("redacted_connection_proof", "")
    if conn and re.search(r"://[^:]+:[^*@][^@]*@", conn):
        errors.append("redacted_connection_proof must use *** for password")
    return errors

# --- tests ---

class TestDocumentExists:
    def test_h43_doc_exists(self):
        assert os.path.exists(DOC_PATH), f"Expected {DOC_PATH} to exist"


class TestH43Purpose:
    def test_h43_purpose_documented(self):
        text = _read_doc()
        assert "approval" in text.lower()
        assert "H43" in text or "owner" in text.lower()

    def test_h43_no_docker_execution(self):
        text = _read_doc()
        assert "does NOT execute Docker" in text or "NOT execute Docker" in text


class TestH42Dependency:
    def test_h42_dependency_documented(self):
        text = _read_doc()
        assert "H42" in text
        assert "EVIDENCE_SANITIZED" in text or "sanitized" in text.lower()

    def test_approval_blocked_missing_h42(self):
        result = evaluate_approval_packet({"h42_sanitized": False})
        assert result == "BLOCKED_MISSING_H42_SANITIZATION"


class TestApprovalScope:
    def test_approval_scope_documented(self):
        text = _read_doc()
        assert "scope" in text.lower()
        assert "local" in text.lower()

    def test_allowed_operations_documented(self):
        text = _read_doc()
        for op in REQUIRED_ALLOWED_OPS:
            assert op in text, f"Allowed operation {op!r} not found in doc"

    def test_forbidden_operations_documented(self):
        text = _read_doc()
        for op in REQUIRED_FORBIDDEN_OPS:
            assert op in text, f"Forbidden operation {op!r} not found in doc"

    def test_production_db_forbidden(self):
        text = _read_doc()
        assert "connect_to_production_db" in text

    def test_cloud_run_mutation_forbidden(self):
        text = _read_doc()
        assert "mutate_cloud_run_env_vars" in text or "mutate_cloud_run" in text


class TestOwnerApprovalJson:
    def test_owner_approval_json_documented(self):
        text = _read_doc()
        assert "approval_id" in text
        assert "status" in text
        assert "expires_at" in text

    def _make_packet(self):
        return {
            "approval_id": "APPROVAL-2026-H43-001",
            "approved_by": "placeholder",
            "requested_by": "Bridge Hub",
            "scope": "local_docker_postgres_dry_run",
            "environment": "local_only",
            "allowed_operations": REQUIRED_ALLOWED_OPS,
            "forbidden_operations": REQUIRED_FORBIDDEN_OPS,
            "cleanup_policy": "container_remove",
            "retention_policy": "artifacts retained",
            "expires_at": "pending",
            "status": "pending",
        }

    def test_approval_packet_ready_pending_signature(self):
        result = evaluate_approval_packet({
            "h42_sanitized": True,
            "cleanup_policy": True,
            "approver": True,
            "scope_defined": True,
            "signed": False,
        })
        assert result == "APPROVAL_PACKET_READY_PENDING_SIGNATURE"

    def test_approval_packet_blocks_missing_cleanup(self):
        result = evaluate_approval_packet({
            "h42_sanitized": True,
            "cleanup_policy": False,
        })
        assert result == "BLOCKED_CLEANUP_MISSING"

    def test_approval_packet_blocks_missing_approver(self):
        result = evaluate_approval_packet({
            "h42_sanitized": True,
            "cleanup_policy": True,
            "approver": False,
        })
        assert result == "BLOCKED_NO_APPROVER"

    def test_packet_valid_when_complete(self):
        errors = validate_approval_packet(self._make_packet())
        assert errors == []

    def test_production_db_in_allowed_rejected(self):
        packet = self._make_packet()
        packet["allowed_operations"] = REQUIRED_ALLOWED_OPS + ["connect_to_production_db"]
        errors = validate_approval_packet(packet)
        assert any("connect_to_production_db" in e for e in errors)

    def test_cloud_run_in_allowed_rejected(self):
        packet = self._make_packet()
        packet["allowed_operations"] = REQUIRED_ALLOWED_OPS + ["mutate_cloud_run_env_vars"]
        errors = validate_approval_packet(packet)
        assert any("mutate_cloud_run_env_vars" in e for e in errors)


class TestCleanupCommitment:
    def test_cleanup_commitment_documented(self):
        text = _read_doc()
        assert "Cleanup" in text or "cleanup" in text.lower()
        assert "container" in text.lower()

    def test_container_stop_in_cleanup(self):
        text = _read_doc()
        assert "docker stop" in text.lower() or "container stop" in text.lower()

    def test_volume_remove_in_cleanup(self):
        text = _read_doc()
        assert "volume" in text.lower()


class TestH43DecisionOutputs:
    def test_h43_decision_outputs_documented(self):
        text = _read_doc()
        for output in DECISION_OUTPUTS:
            assert output in text, f"Decision output {output!r} not found in doc"

    def test_current_decision_pending(self):
        text = _read_doc()
        assert "APPROVAL_PACKET_READY_PENDING_SIGNATURE" in text

    def test_evaluator_approved_when_signed(self):
        result = evaluate_approval_packet({
            "h42_sanitized": True,
            "cleanup_policy": True,
            "approver": True,
            "scope_defined": True,
            "signed": True,
        })
        assert result == "APPROVED_FOR_LOCAL_DOCKER_DRY_RUN"


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
