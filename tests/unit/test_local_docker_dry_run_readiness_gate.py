"""
Tests for docs/local-docker-dry-run-readiness-gate.md (H38).

H38 is docs/tests only. No Docker is executed. No DB is created.
No SQL is run. No migration is run. No fixture is loaded into any DB.
No runtime API calls are made. No Cloud Run env vars are mutated.
No feature flags are enabled. No Balance.ge connector is activated.
DATABASE_URL stays empty during all local test runs.
"""

import re
import os
import pytest

DOC_PATH = "docs/local-docker-dry-run-readiness-gate.md"

PRODUCTION_URL_MARKERS = [
    "production",
    "prod-",
    "-prod",
    "cloudsql",
    "rgelikoshvili",
    "europe-west1.run.app",
    "sql.goog",
]

REQUIRED_GATES = [
    "G1", "G2", "G3", "G4", "G5",
    "G6", "G7", "G8", "G9", "G10",
    "G11", "G12",
]

DECISION_OUTPUTS = {
    "READY_FOR_DRY_RUN_EXECUTION",
    "BLOCKED_MISSING_H37_EVIDENCE",
    "BLOCKED_DOCKER_UNAVAILABLE",
    "BLOCKED_NO_OWNER_APPROVAL",
    "BLOCKED_PRODUCTION_RISK",
    "BLOCKED_RAW_SECRET_RISK",
    "BLOCKED_NO_CLEANUP_PLAN",
}

REQUIRED_PACKET_FIELDS = [
    "execution_id",
    "h37_evidence_id",
    "docker_image",
    "container_name",
    "db_name",
    "host",
    "port",
    "redacted_connection_proof",
    "owner_approval_id",
    "cleanup_policy",
    "allowed_operations",
    "forbidden_operations",
    "feature_flag_plan",
    "rollback_reference",
    "gates_passed",
    "go_decision",
    "created_at",
]

REQUIRED_ALLOWED_OPERATIONS = [
    "docker_pull_postgres",
    "docker_run_disposable_container",
    "run_migration_011_local_only",
    "load_synthetic_fixture_local_only",
    "capture_reports_flag_off_local_only",
    "capture_reports_flag_on_local_only",
    "normalize_report_outputs",
    "compare_report_outputs",
    "docker_stop",
    "docker_rm",
    "docker_volume_rm",
]

REQUIRED_FORBIDDEN_OPERATIONS = [
    "connect_to_production_db",
    "mutate_cloud_run_env",
    "enable_posted_ledger_reports_enabled_in_production",
    "load_real_tenant_data",
    "activate_balance_ge_live_connector",
    "commit_credentials",
    "push_real_database_url",
]

# --- helpers ---

def _read_doc():
    with open(DOC_PATH, "r", encoding="utf-8") as f:
        return f.read()

def evaluate_h38_gate(state: dict) -> str:
    """Evaluate H38 readiness gate state and return decision output."""
    if not state.get("h37_packet_complete"):
        return "BLOCKED_MISSING_H37_EVIDENCE"
    if not state.get("docker_available"):
        return "BLOCKED_DOCKER_UNAVAILABLE"
    if not state.get("owner_approval_valid"):
        return "BLOCKED_NO_OWNER_APPROVAL"
    url = state.get("database_url", "")
    if any(m in url for m in PRODUCTION_URL_MARKERS):
        return "BLOCKED_PRODUCTION_RISK"
    if re.search(r"://[^:]+:[^*@][^@]*@", url):
        return "BLOCKED_RAW_SECRET_RISK"
    if not state.get("cleanup_plan_confirmed"):
        return "BLOCKED_NO_CLEANUP_PLAN"
    if state.get("all_gates_pass"):
        return "READY_FOR_DRY_RUN_EXECUTION"
    return "BLOCKED_MISSING_H37_EVIDENCE"

def validate_execution_packet(packet: dict) -> list:
    """Validate an H38 execution packet. Returns list of errors."""
    errors = []
    for field in REQUIRED_PACKET_FIELDS:
        if field not in packet:
            errors.append(f"missing field: {field}")
    if packet.get("host") not in ("localhost", "127.0.0.1"):
        errors.append("host must be localhost or 127.0.0.1")
    if packet.get("go_decision") not in ("go", "no_go"):
        errors.append("go_decision must be 'go' or 'no_go'")
    conn = packet.get("redacted_connection_proof", "")
    if "***" not in conn:
        errors.append("redacted_connection_proof must use *** for password")
    if not any(m in conn for m in ["disposable", "nonprod"]):
        errors.append("redacted_connection_proof must include disposable/nonprod marker")
    allowed = packet.get("allowed_operations", [])
    forbidden = packet.get("forbidden_operations", [])
    overlap = set(allowed) & set(forbidden)
    if overlap:
        errors.append(f"operations in both allowed and forbidden: {overlap}")
    if "connect_to_production_db" in allowed:
        errors.append("connect_to_production_db must not be in allowed_operations")
    if "mutate_cloud_run_env" in allowed:
        errors.append("mutate_cloud_run_env must not be in allowed_operations")
    return errors

# --- tests ---

class TestDocumentExists:
    def test_doc_file_exists(self):
        assert os.path.exists(DOC_PATH), f"Expected {DOC_PATH} to exist"

    def test_doc_is_not_empty(self):
        text = _read_doc()
        assert len(text) > 500

    def test_doc_title_present(self):
        text = _read_doc()
        assert "H38" in text
        assert "Readiness Gate" in text or "readiness-gate" in DOC_PATH


class TestH38NonActionStatement:
    def test_h38_is_docs_tests_only(self):
        text = _read_doc()
        assert "docs/tests only" in text.lower() or "H38 is docs" in text

    def test_h38_does_not_execute_docker(self):
        text = _read_doc()
        assert "does NOT execute Docker" in text or "NOT execute Docker" in text

    def test_h38_does_not_create_db(self):
        text = _read_doc()
        assert "does NOT create a DB" in text or "NOT create a DB" in text

    def test_posted_ledger_flag_remains_off(self):
        text = _read_doc()
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text
        assert "remains OFF" in text or "remain OFF" in text


class TestH37Dependency:
    def test_h37_dependency_documented(self):
        text = _read_doc()
        assert "H37" in text
        assert "ready_for_h38" in text

    def test_h37_incomplete_blocks_h38(self):
        result = evaluate_h38_gate({"h37_packet_complete": False})
        assert result == "BLOCKED_MISSING_H37_EVIDENCE"

    def test_current_h38_decision_blocked(self):
        text = _read_doc()
        assert "BLOCKED_MISSING_H37_EVIDENCE" in text


class TestReadinessGates:
    def test_all_gates_documented(self):
        text = _read_doc()
        for gate in REQUIRED_GATES:
            assert gate in text, f"Gate {gate} not found in doc"

    def test_g1_docker_availability(self):
        text = _read_doc()
        assert "G1" in text
        assert "Docker" in text

    def test_g2_h37_evidence_packet(self):
        text = _read_doc()
        assert "G2" in text
        assert "evidence packet" in text.lower()

    def test_g7_no_production_indicators(self):
        text = _read_doc()
        assert "G7" in text
        assert "production" in text.lower()

    def test_g8_no_raw_secrets(self):
        text = _read_doc()
        assert "G8" in text
        assert "secret" in text.lower() or "password" in text.lower()

    def test_g11_cleanup_plan(self):
        text = _read_doc()
        assert "G11" in text
        assert "cleanup" in text.lower()

    def test_g12_rollback_reference(self):
        text = _read_doc()
        assert "G12" in text
        assert "rollback" in text.lower()


class TestExecutionPacketContract:
    def _make_packet(self):
        return {
            "execution_id": "DRY-RUN-2026-001",
            "h37_evidence_id": "DOCKER-PROV-2026-001",
            "docker_image": "postgres:16",
            "container_name": "bridgehub_disposable_h37",
            "db_name": "bridgehub_disposable_h37",
            "host": "localhost",
            "port": 5432,
            "redacted_connection_proof": "postgresql://bridgehub_nonprod_user:***@localhost:5432/bridgehub_disposable_h37",
            "owner_approval_id": "approval-001",
            "cleanup_policy": "container_remove",
            "allowed_operations": REQUIRED_ALLOWED_OPERATIONS,
            "forbidden_operations": REQUIRED_FORBIDDEN_OPERATIONS,
            "feature_flag_plan": "local shell only; reset before docker stop",
            "rollback_reference": "docs/rollback-monitoring-post-switch-safety-contract.md",
            "gates_passed": REQUIRED_GATES,
            "go_decision": "go",
            "created_at": "2026-01-01T00:00:00Z",
        }

    def test_complete_packet_valid(self):
        errors = validate_execution_packet(self._make_packet())
        assert errors == []

    def test_packet_missing_field_detected(self):
        packet = self._make_packet()
        del packet["rollback_reference"]
        errors = validate_execution_packet(packet)
        assert any("rollback_reference" in e for e in errors)

    def test_remote_host_rejected(self):
        packet = self._make_packet()
        packet["host"] = "production.cloudsql.example.com"
        errors = validate_execution_packet(packet)
        assert any("host" in e for e in errors)

    def test_invalid_go_decision_rejected(self):
        packet = self._make_packet()
        packet["go_decision"] = "maybe"
        errors = validate_execution_packet(packet)
        assert any("go_decision" in e for e in errors)

    def test_production_connect_in_allowed_rejected(self):
        packet = self._make_packet()
        packet["allowed_operations"] = REQUIRED_ALLOWED_OPERATIONS + ["connect_to_production_db"]
        errors = validate_execution_packet(packet)
        assert any("connect_to_production_db" in e for e in errors)

    def test_allowed_and_forbidden_overlap_rejected(self):
        packet = self._make_packet()
        packet["allowed_operations"] = REQUIRED_ALLOWED_OPERATIONS + ["mutate_cloud_run_env"]
        errors = validate_execution_packet(packet)
        assert len(errors) > 0

    def test_raw_password_in_conn_rejected(self):
        packet = self._make_packet()
        packet["redacted_connection_proof"] = (
            "postgresql://user:realpassword@localhost:5432/bridgehub_disposable_h37"
        )
        errors = validate_execution_packet(packet)
        assert any("***" in e or "password" in e for e in errors)


class TestDecisionOutputs:
    def test_all_decision_outputs_documented(self):
        text = _read_doc()
        for output in DECISION_OUTPUTS:
            assert output in text, f"Decision output {output} not found in doc"

    def test_evaluator_blocked_missing_h37(self):
        result = evaluate_h38_gate({})
        assert result == "BLOCKED_MISSING_H37_EVIDENCE"

    def test_evaluator_blocked_docker_unavailable(self):
        result = evaluate_h38_gate({"h37_packet_complete": True, "docker_available": False})
        assert result == "BLOCKED_DOCKER_UNAVAILABLE"

    def test_evaluator_blocked_no_approval(self):
        result = evaluate_h38_gate({
            "h37_packet_complete": True,
            "docker_available": True,
            "owner_approval_valid": False,
        })
        assert result == "BLOCKED_NO_OWNER_APPROVAL"

    def test_evaluator_production_risk(self):
        result = evaluate_h38_gate({
            "h37_packet_complete": True,
            "docker_available": True,
            "owner_approval_valid": True,
            "database_url": "postgresql://user:***@production.cloudsql.example.com:5432/bridge",
        })
        assert result == "BLOCKED_PRODUCTION_RISK"

    def test_evaluator_blocked_no_cleanup(self):
        result = evaluate_h38_gate({
            "h37_packet_complete": True,
            "docker_available": True,
            "owner_approval_valid": True,
            "database_url": "postgresql://user:***@localhost:5432/bridgehub_disposable_h37",
            "cleanup_plan_confirmed": False,
        })
        assert result == "BLOCKED_NO_CLEANUP_PLAN"

    def test_evaluator_ready_when_all_pass(self):
        result = evaluate_h38_gate({
            "h37_packet_complete": True,
            "docker_available": True,
            "owner_approval_valid": True,
            "database_url": "postgresql://user:***@localhost:5432/bridgehub_disposable_h37",
            "cleanup_plan_confirmed": True,
            "all_gates_pass": True,
        })
        assert result == "READY_FOR_DRY_RUN_EXECUTION"


class TestAllowedAndForbiddenOperations:
    def test_allowed_operations_documented(self):
        text = _read_doc()
        for op in REQUIRED_ALLOWED_OPERATIONS:
            assert op in text, f"Allowed operation {op} not found in doc"

    def test_forbidden_operations_documented(self):
        text = _read_doc()
        for op in REQUIRED_FORBIDDEN_OPERATIONS:
            assert op in text, f"Forbidden operation {op} not found in doc"

    def test_connect_to_production_db_is_forbidden(self):
        text = _read_doc()
        assert "connect_to_production_db" in text
        assert "forbidden" in text.lower() or "Forbidden" in text

    def test_mutate_cloud_run_env_is_forbidden(self):
        text = _read_doc()
        assert "mutate_cloud_run_env" in text


class TestNoForbiddenExecutionInDoc:
    def test_no_docker_run_outside_future_block(self):
        """docker run must only appear inside [NOT EXECUTED IN H38] labeled sections."""
        with open(DOC_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        in_future_block = False
        for line in lines:
            if "[NOT EXECUTED IN H38]" in line or "[FUTURE]" in line:
                in_future_block = True
            if in_future_block and line.strip() == "```":
                in_future_block = False
            if not in_future_block:
                assert not re.match(r"^\s*docker\s+run\b", line), (
                    f"docker run found outside future block: {line.rstrip()}"
                )

    def test_no_real_password_in_doc(self):
        text = _read_doc()
        lines = text.splitlines()
        for line in lines:
            assert not re.search(r"postgresql://[^:]+:[^*\s]{4,}@", line), (
                f"Possible real password in line: {line.rstrip()}"
            )
