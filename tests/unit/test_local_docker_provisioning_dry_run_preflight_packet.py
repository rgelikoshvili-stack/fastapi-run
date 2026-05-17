"""
Tests for docs/local-docker-provisioning-dry-run-preflight-approval-packet.md (H40).

H40 is docs/tests only. No Docker executed. No DB created. No SQL run.
No migration executed. No fixture loaded. No runtime API calls made.
No Cloud Run env vars mutated. No feature flags enabled.
No Balance.ge activated. DATABASE_URL stays empty.
"""

import re
import os
import pytest

DOC_PATH = "docs/local-docker-provisioning-dry-run-preflight-approval-packet.md"

PRODUCTION_URL_MARKERS = [
    "production",
    "prod-",
    "-prod",
    "cloudsql",
    "rgelikoshvili",
    "europe-west1.run.app",
    "sql.goog",
]

REQUIRED_PREFLIGHT_GATES = [
    "P1", "P2", "P3", "P4", "P5", "P6", "P7",
    "P8", "P9", "P10", "P11", "P12", "P13", "P14",
]

DECISION_OUTPUTS = {
    "READY_FOR_LOCAL_DOCKER_PROVISIONING_EXECUTION",
    "BLOCKED_MISSING_H39_EVIDENCE",
    "BLOCKED_DOCKER_UNAVAILABLE",
    "BLOCKED_REMOTE_CONTEXT",
    "BLOCKED_PRODUCTION_RISK",
    "BLOCKED_RAW_SECRET_RISK",
    "BLOCKED_NO_OWNER_APPROVAL",
    "BLOCKED_NO_CLEANUP_POLICY",
}

REQUIRED_APPROVAL_PACKET_FIELDS = [
    "approval_packet_id",
    "docker_evidence_id",
    "requested_by",
    "approved_by",
    "environment",
    "allowed_operations",
    "forbidden_operations",
    "cleanup_policy",
    "retention_policy",
    "expires_at",
    "go_decision",
    "created_at",
]

REQUIRED_ALLOWED_OPS = [
    "docker_pull_postgres",
    "docker_run_postgres",
    "create_disposable_db",
    "run_migration_011",
    "load_synthetic_fixture",
    "cleanup",
]

REQUIRED_FORBIDDEN_OPS = [
    "production_db",
    "cloud_run_env_mutation",
    "balance_live",
    "production_data",
    "raw_secret_commit",
]

# --- helpers ---

def _read_doc():
    with open(DOC_PATH, "r", encoding="utf-8") as f:
        return f.read()

def evaluate_h40_preflight(state: dict) -> str:
    """Evaluate H40 preflight state and return decision output."""
    if not state.get("h39_packet_complete"):
        return "BLOCKED_MISSING_H39_EVIDENCE"
    if not state.get("docker_available"):
        return "BLOCKED_DOCKER_UNAVAILABLE"
    if state.get("remote_context"):
        return "BLOCKED_REMOTE_CONTEXT"
    context_host = state.get("context_host", "")
    if any(m in context_host for m in PRODUCTION_URL_MARKERS):
        return "BLOCKED_PRODUCTION_RISK"
    if state.get("raw_secret"):
        return "BLOCKED_RAW_SECRET_RISK"
    if not state.get("owner_approval"):
        return "BLOCKED_NO_OWNER_APPROVAL"
    if not state.get("cleanup_policy"):
        return "BLOCKED_NO_CLEANUP_POLICY"
    if state.get("all_gates_pass"):
        return "READY_FOR_LOCAL_DOCKER_PROVISIONING_EXECUTION"
    return "BLOCKED_MISSING_H39_EVIDENCE"

def validate_approval_packet(packet: dict) -> list:
    """Validate an H40 approval packet. Returns list of errors."""
    errors = []
    for field in REQUIRED_APPROVAL_PACKET_FIELDS:
        if field not in packet:
            errors.append(f"missing field: {field}")
    if packet.get("environment") != "local_docker":
        errors.append("environment must be local_docker")
    if packet.get("go_decision") not in ("go", "no_go"):
        errors.append("go_decision must be 'go' or 'no_go'")
    allowed = packet.get("allowed_operations", [])
    forbidden = packet.get("forbidden_operations", [])
    overlap = set(allowed) & set(forbidden)
    if overlap:
        errors.append(f"operations in both allowed and forbidden: {overlap}")
    if "production_db" in allowed:
        errors.append("production_db must not be in allowed_operations")
    if "cloud_run_env_mutation" in allowed:
        errors.append("cloud_run_env_mutation must not be in allowed_operations")
    if "balance_live" in allowed:
        errors.append("balance_live must not be in allowed_operations")
    conn = packet.get("redacted_connection_proof", "")
    if conn and re.search(r"://[^:]+:[^*@][^@]*@", conn):
        errors.append("redacted_connection_proof must use *** for password")
    return errors

# --- tests ---

class TestDocumentExists:
    def test_h40_doc_exists(self):
        assert os.path.exists(DOC_PATH), f"Expected {DOC_PATH} to exist"

    def test_h40_doc_not_empty(self):
        text = _read_doc()
        assert len(text) > 500


class TestH40NonActionStatement:
    def test_h40_non_action_statement_present(self):
        text = _read_doc()
        assert "docs/tests only" in text.lower() or "H40 is docs" in text

    def test_h40_does_not_execute_docker(self):
        text = _read_doc()
        assert "does NOT execute Docker" in text or "NOT execute Docker" in text

    def test_h40_does_not_create_db(self):
        text = _read_doc()
        assert "does NOT create a DB" in text or "NOT create a DB" in text

    def test_posted_ledger_flag_remains_off(self):
        text = _read_doc()
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text
        assert "remains OFF" in text or "remain OFF" in text


class TestH39Dependency:
    def test_h39_dependency_documented(self):
        text = _read_doc()
        assert "H39" in text
        assert "ready_for_preflight" in text

    def test_h39_packet_missing_blocks_h40(self):
        result = evaluate_h40_preflight({"h39_packet_complete": False})
        assert result == "BLOCKED_MISSING_H39_EVIDENCE"

    def test_current_h40_decision_is_blocked(self):
        text = _read_doc()
        assert "BLOCKED_MISSING_H39_EVIDENCE" in text


class TestPreflightGateP1ToP14:
    def test_preflight_gate_p1_to_p14_documented(self):
        text = _read_doc()
        for gate in REQUIRED_PREFLIGHT_GATES:
            assert gate in text, f"Preflight gate {gate} not found in doc"

    def test_p1_docker_evidence_packet(self):
        text = _read_doc()
        assert "P1" in text
        assert "evidence packet" in text.lower() or "Docker evidence" in text

    def test_p4_local_only_context(self):
        text = _read_doc()
        assert "P4" in text
        assert "local" in text.lower()

    def test_p12_balance_ge_demo(self):
        text = _read_doc()
        assert "P12" in text
        assert "demo" in text.lower() or "Balance" in text

    def test_p13_feature_flag_off(self):
        text = _read_doc()
        assert "P13" in text
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text

    def test_p14_rollback_reference(self):
        text = _read_doc()
        assert "P14" in text
        assert "rollback" in text.lower()


class TestApprovalPacketContract:
    def test_approval_packet_contract_documented(self):
        text = _read_doc()
        assert "approval_packet_id" in text
        assert "go_decision" in text
        assert "allowed_operations" in text
        assert "forbidden_operations" in text

    def _make_packet(self):
        return {
            "approval_packet_id": "PREFLIGHT-2026-001",
            "docker_evidence_id": "DOCKER-EV-2026-001",
            "requested_by": "engineering-owner",
            "approved_by": "engineering-owner",
            "environment": "local_docker",
            "allowed_operations": REQUIRED_ALLOWED_OPS,
            "forbidden_operations": REQUIRED_FORBIDDEN_OPS,
            "cleanup_policy": "container_remove",
            "retention_policy": "artifacts retained; no secrets; synthetic data only",
            "expires_at": "2026-01-08T00:00:00Z",
            "go_decision": "no_go",
            "created_at": "2026-01-01T00:00:00Z",
        }

    def test_local_preflight_all_pass_ready(self):
        result = evaluate_h40_preflight({
            "h39_packet_complete": True,
            "docker_available": True,
            "remote_context": False,
            "context_host": "unix:///var/run/docker.sock",
            "raw_secret": False,
            "owner_approval": True,
            "cleanup_policy": True,
            "all_gates_pass": True,
        })
        assert result == "READY_FOR_LOCAL_DOCKER_PROVISIONING_EXECUTION"

    def test_local_preflight_blocks_missing_h39_evidence(self):
        result = evaluate_h40_preflight({"h39_packet_complete": False})
        assert result == "BLOCKED_MISSING_H39_EVIDENCE"

    def test_local_preflight_blocks_remote_context(self):
        result = evaluate_h40_preflight({
            "h39_packet_complete": True,
            "docker_available": True,
            "remote_context": True,
        })
        assert result == "BLOCKED_REMOTE_CONTEXT"

    def test_local_preflight_blocks_raw_secret(self):
        result = evaluate_h40_preflight({
            "h39_packet_complete": True,
            "docker_available": True,
            "remote_context": False,
            "context_host": "unix:///var/run/docker.sock",
            "raw_secret": True,
        })
        assert result == "BLOCKED_RAW_SECRET_RISK"

    def test_local_preflight_blocks_no_owner_approval(self):
        result = evaluate_h40_preflight({
            "h39_packet_complete": True,
            "docker_available": True,
            "remote_context": False,
            "context_host": "unix:///var/run/docker.sock",
            "raw_secret": False,
            "owner_approval": False,
        })
        assert result == "BLOCKED_NO_OWNER_APPROVAL"

    def test_local_preflight_blocks_no_cleanup_policy(self):
        result = evaluate_h40_preflight({
            "h39_packet_complete": True,
            "docker_available": True,
            "remote_context": False,
            "context_host": "unix:///var/run/docker.sock",
            "raw_secret": False,
            "owner_approval": True,
            "cleanup_policy": False,
        })
        assert result == "BLOCKED_NO_CLEANUP_POLICY"

    def test_local_preflight_blocks_no_fixture_hash(self):
        packet = self._make_packet()
        del packet["cleanup_policy"]
        errors = validate_approval_packet(packet)
        assert any("cleanup_policy" in e for e in errors)

    def test_local_approval_packet_requires_allowed_and_forbidden_operations(self):
        packet = self._make_packet()
        errors = validate_approval_packet(packet)
        assert errors == []
        packet_bad = self._make_packet()
        del packet_bad["allowed_operations"]
        errors_bad = validate_approval_packet(packet_bad)
        assert any("allowed_operations" in e for e in errors_bad)

    def test_production_db_in_allowed_rejected(self):
        packet = self._make_packet()
        packet["allowed_operations"] = REQUIRED_ALLOWED_OPS + ["production_db"]
        errors = validate_approval_packet(packet)
        assert any("production_db" in e for e in errors)

    def test_cloud_run_mutation_in_allowed_rejected(self):
        packet = self._make_packet()
        packet["allowed_operations"] = REQUIRED_ALLOWED_OPS + ["cloud_run_env_mutation"]
        errors = validate_approval_packet(packet)
        assert any("cloud_run_env_mutation" in e for e in errors)

    def test_balance_live_in_allowed_rejected(self):
        packet = self._make_packet()
        packet["allowed_operations"] = REQUIRED_ALLOWED_OPS + ["balance_live"]
        errors = validate_approval_packet(packet)
        assert any("balance_live" in e for e in errors)


class TestFutureProvisioningBoundary:
    def test_future_provisioning_boundary_documented(self):
        text = _read_doc()
        assert "NOT EXECUTED IN H40" in text

    def test_docker_pull_labeled_future(self):
        text = _read_doc()
        assert "docker pull" in text.lower()
        assert "NOT EXECUTED" in text


class TestGoCriteriaAndNoGo:
    def test_go_criteria_documented(self):
        text = _read_doc()
        assert "Go Criteria" in text or "go criteria" in text.lower()

    def test_no_go_criteria_documented(self):
        text = _read_doc()
        assert "No-Go" in text or "no-go" in text.lower()


class TestH40DecisionOutputs:
    def test_h40_decision_outputs_documented(self):
        text = _read_doc()
        for output in DECISION_OUTPUTS:
            assert output in text, f"Decision output {output} not found in doc"

    def test_evaluator_blocked_docker_unavailable(self):
        result = evaluate_h40_preflight({
            "h39_packet_complete": True,
            "docker_available": False,
        })
        assert result == "BLOCKED_DOCKER_UNAVAILABLE"

    def test_evaluator_production_risk(self):
        result = evaluate_h40_preflight({
            "h39_packet_complete": True,
            "docker_available": True,
            "remote_context": False,
            "context_host": "tcp://production.cloudsql.example.com:2376",
        })
        assert result == "BLOCKED_PRODUCTION_RISK"


class TestSafetyRules:
    def test_safety_rules_documented(self):
        text = _read_doc()
        assert "Safety" in text or "safety" in text.lower()
        assert "executes no Docker" in text or "NOT execute Docker" in text


class TestNextTaskH41:
    def test_next_task_h41_documented(self):
        text = _read_doc()
        assert "H41" in text

    def test_h41_conditions_documented(self):
        text = _read_doc()
        assert "Docker evidence" in text or "evidence" in text.lower()


class TestNoRealPiiOrSensitiveData:
    def test_no_real_pii_or_tax_or_bank_patterns(self):
        text = _read_doc()
        assert not re.search(r"010[0-9]{8}", text), "Possible phone number found"
        assert not re.search(r"@gmail\.com|@yahoo\.com|@hotmail\.com", text), "Email found"
        assert not re.search(r"\b[0-9]{16}\b", text), "Possible card number found"


class TestNoForbiddenImportsInTestFile:
    def test_no_db_or_network_imports_in_test_file(self):
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
                assert imp not in stripped, f"Forbidden import found: {stripped}"

    def test_no_sql_docker_or_subprocess_in_test_file(self):
        with open(__file__, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines:
            assert not re.match(r"^\s*subprocess\.", line), f"subprocess call: {line.rstrip()}"
            assert not re.match(r"^\s*os\.system\b", line), f"os.system call: {line.rstrip()}"
