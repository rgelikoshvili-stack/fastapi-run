"""
Tests for docs/local-docker-provisioning-go-no-go-decision.md (H44).

H44 evaluates go/no-go for local Docker PostgreSQL provisioning.
H41: BLOCKED_DOCKER_UNAVAILABLE (Docker not installed).
H42: EVIDENCE_SANITIZED.
H43: APPROVAL_PACKET_READY_PENDING_SIGNATURE.
H44 final decision: BLOCKED_DOCKER_UNAVAILABLE (G1, G2, G3 fail).
No Docker, DB, SQL, migration, fixture, runtime API, Cloud Run mutation, or feature flag.
"""

import re
import os
import pytest

DOC_PATH = "docs/local-docker-provisioning-go-no-go-decision.md"

REQUIRED_GATES = [
    "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8",
    "G9", "G10", "G11", "G12", "G13", "G14", "G15",
]

DECISION_OUTPUTS = {
    "READY_FOR_LOCAL_DOCKER_PROVISIONING_DRY_RUN",
    "BLOCKED_DOCKER_UNAVAILABLE",
    "BLOCKED_DAEMON_UNAVAILABLE",
    "BLOCKED_REMOTE_CONTEXT",
    "BLOCKED_PRODUCTION_RISK",
    "BLOCKED_SECRET_RISK",
    "BLOCKED_NO_OWNER_APPROVAL",
    "BLOCKED_NO_CLEANUP_POLICY",
    "BLOCKED_MISSING_FIXTURE_HASH",
    "BLOCKED_MISSING_MIGRATION_REVIEW",
}

PRODUCTION_URL_MARKERS = [
    "production",
    "prod-",
    "-prod",
    "cloudsql",
    "rgelikoshvili",
    "europe-west1.run.app",
    "sql.goog",
]

# --- helpers ---

def _read_doc():
    with open(DOC_PATH, "r", encoding="utf-8") as f:
        return f.read()

def evaluate_go_no_go(state: dict) -> str:
    """Evaluate H44 go/no-go gate state and return final decision."""
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
    if not state.get("owner_approval"):
        return "BLOCKED_NO_OWNER_APPROVAL"
    if not state.get("cleanup_policy"):
        return "BLOCKED_NO_CLEANUP_POLICY"
    if not state.get("fixture_hash"):
        return "BLOCKED_MISSING_FIXTURE_HASH"
    if not state.get("migration_reviewed"):
        return "BLOCKED_MISSING_MIGRATION_REVIEW"
    if state.get("all_gates_pass"):
        return "READY_FOR_LOCAL_DOCKER_PROVISIONING_DRY_RUN"
    return "BLOCKED_DOCKER_UNAVAILABLE"

# --- tests ---

class TestDocumentExists:
    def test_h44_doc_exists(self):
        assert os.path.exists(DOC_PATH), f"Expected {DOC_PATH} to exist"


class TestH44Purpose:
    def test_h44_purpose_documented(self):
        text = _read_doc()
        assert "Go/No-Go" in text or "go/no-go" in text.lower() or "go-no-go" in text.lower()

    def test_h44_no_provisioning_executed(self):
        text = _read_doc()
        assert "NOT execute" in text or "does NOT" in text or "not executed" in text.lower()


class TestDependencies:
    def test_dependencies_documented(self):
        text = _read_doc()
        assert "H41" in text
        assert "H42" in text
        assert "H43" in text

    def test_h41_dependency_present(self):
        text = _read_doc()
        assert "DOCKER-EV-2026-H41-001" in text or "BLOCKED_DOCKER_UNAVAILABLE" in text

    def test_h42_dependency_present(self):
        text = _read_doc()
        assert "SANITIZATION-2026-H42-001" in text or "EVIDENCE_SANITIZED" in text

    def test_h43_dependency_present(self):
        text = _read_doc()
        assert "APPROVAL-2026-H43-001" in text or "APPROVAL_PACKET_READY_PENDING_SIGNATURE" in text


class TestGoGates:
    def test_go_gates_g1_to_g15_documented(self):
        text = _read_doc()
        for gate in REQUIRED_GATES:
            assert gate in text, f"Gate {gate} not found in doc"

    def test_g1_docker_installed(self):
        text = _read_doc()
        assert "G1" in text
        assert "Docker installed" in text or "docker installed" in text.lower()

    def test_g7_owner_approval(self):
        text = _read_doc()
        assert "G7" in text
        assert "approval" in text.lower()

    def test_g13_balance_ge_demo(self):
        text = _read_doc()
        assert "G13" in text
        assert "demo" in text.lower() or "Balance" in text

    def test_g14_feature_flag_off(self):
        text = _read_doc()
        assert "G14" in text
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text

    def test_g15_rollback_reference(self):
        text = _read_doc()
        assert "G15" in text
        assert "rollback" in text.lower()


class TestNoGoCriteria:
    def test_no_go_criteria_documented(self):
        text = _read_doc()
        assert "No-Go" in text or "no-go" in text.lower()

    def test_docker_not_installed_triggers_no_go(self):
        text = _read_doc()
        assert "Docker not installed" in text or "BLOCKED_DOCKER_UNAVAILABLE" in text


class TestFinalDecisionOutputs:
    def test_final_decision_outputs_documented(self):
        text = _read_doc()
        for output in DECISION_OUTPUTS:
            assert output in text, f"Decision output {output} not found in doc"

    def test_current_decision_blocked(self):
        text = _read_doc()
        assert "BLOCKED_DOCKER_UNAVAILABLE" in text

    def test_go_no_go_ready_when_all_gates_pass(self):
        result = evaluate_go_no_go({
            "docker_installed": True,
            "docker_daemon_available": True,
            "remote_context": False,
            "production_risk": False,
            "secret_risk": False,
            "owner_approval": True,
            "cleanup_policy": True,
            "fixture_hash": True,
            "migration_reviewed": True,
            "all_gates_pass": True,
        })
        assert result == "READY_FOR_LOCAL_DOCKER_PROVISIONING_DRY_RUN"

    def test_go_no_go_blocks_missing_owner_approval(self):
        result = evaluate_go_no_go({
            "docker_installed": True,
            "docker_daemon_available": True,
            "remote_context": False,
            "production_risk": False,
            "secret_risk": False,
            "owner_approval": False,
        })
        assert result == "BLOCKED_NO_OWNER_APPROVAL"

    def test_go_no_go_blocks_missing_cleanup_policy(self):
        result = evaluate_go_no_go({
            "docker_installed": True,
            "docker_daemon_available": True,
            "remote_context": False,
            "production_risk": False,
            "secret_risk": False,
            "owner_approval": True,
            "cleanup_policy": False,
        })
        assert result == "BLOCKED_NO_CLEANUP_POLICY"

    def test_go_no_go_blocks_production_risk(self):
        result = evaluate_go_no_go({
            "docker_installed": True,
            "docker_daemon_available": True,
            "remote_context": False,
            "production_risk": True,
        })
        assert result == "BLOCKED_PRODUCTION_RISK"

    def test_go_no_go_blocks_secret_risk(self):
        result = evaluate_go_no_go({
            "docker_installed": True,
            "docker_daemon_available": True,
            "remote_context": False,
            "production_risk": False,
            "secret_risk": True,
        })
        assert result == "BLOCKED_SECRET_RISK"

    def test_evaluator_docker_not_installed(self):
        result = evaluate_go_no_go({"docker_installed": False})
        assert result == "BLOCKED_DOCKER_UNAVAILABLE"

    def test_evaluator_missing_fixture_hash(self):
        result = evaluate_go_no_go({
            "docker_installed": True,
            "docker_daemon_available": True,
            "remote_context": False,
            "production_risk": False,
            "secret_risk": False,
            "owner_approval": True,
            "cleanup_policy": True,
            "fixture_hash": False,
        })
        assert result == "BLOCKED_MISSING_FIXTURE_HASH"

    def test_evaluator_missing_migration_review(self):
        result = evaluate_go_no_go({
            "docker_installed": True,
            "docker_daemon_available": True,
            "remote_context": False,
            "production_risk": False,
            "secret_risk": False,
            "owner_approval": True,
            "cleanup_policy": True,
            "fixture_hash": True,
            "migration_reviewed": False,
        })
        assert result == "BLOCKED_MISSING_MIGRATION_REVIEW"


class TestNextTask:
    def test_next_task_documented(self):
        text = _read_doc()
        assert "H45" in text

    def test_blocker_resolution_path_documented(self):
        text = _read_doc()
        assert "Blocker" in text or "blocker" in text.lower() or "resolution" in text.lower()


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
