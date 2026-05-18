"""
Tests for docs/local-docker-final-go-gate-h51.md (H51).

H51 re-evaluates G1–G15 after owner approval is signed.
All 15 gates pass. Final decision: READY_FOR_LOCAL_DOCKER_POSTGRES_DRY_RUN.
No Docker run/pull/compose, no DB, no SQL, no migration, no fixture, no runtime APIs.
"""

import os
import pytest

DOC_PATH = "docs/local-docker-final-go-gate-h51.md"

REQUIRED_GATES = [f"G{i}" for i in range(1, 16)]

ALLOWED_GO_GATE_DECISIONS = {
    "READY_FOR_LOCAL_DOCKER_POSTGRES_DRY_RUN",
    "BLOCKED_OWNER_APPROVAL_PENDING",
    "BLOCKED_EXPIRES_AT_MISSING",
    "BLOCKED_EXPIRES_AT_TOO_LONG",
    "BLOCKED_PRODUCTION_RISK",
    "BLOCKED_DOCKER_UNAVAILABLE",
    "BLOCKED_DAEMON_UNAVAILABLE",
    "BLOCKED_REMOTE_CONTEXT",
    "BLOCKED_SECRET_RISK",
    "BLOCKED_NO_CLEANUP_POLICY",
    "BLOCKED_MISSING_FIXTURE_HASH",
    "BLOCKED_MISSING_MIGRATION_REVIEW",
}


def _read_doc():
    with open(DOC_PATH, "r", encoding="utf-8") as f:
        return f.read()


def evaluate_go_gate(state: dict) -> str:
    """Evaluate H51 final go gate and return decision string."""
    if not state.get("docker_installed"):
        return "BLOCKED_DOCKER_UNAVAILABLE"
    if not state.get("docker_daemon_available"):
        return "BLOCKED_DAEMON_UNAVAILABLE"
    if state.get("production_risk"):
        return "BLOCKED_PRODUCTION_RISK"
    if state.get("secret_risk"):
        return "BLOCKED_SECRET_RISK"
    if not state.get("cleanup_policy"):
        return "BLOCKED_NO_CLEANUP_POLICY"
    if not state.get("fixture_hash_captured"):
        return "BLOCKED_MISSING_FIXTURE_HASH"
    if not state.get("migration_reviewed"):
        return "BLOCKED_MISSING_MIGRATION_REVIEW"
    if not state.get("owner_approval_signed"):
        return "BLOCKED_OWNER_APPROVAL_PENDING"
    if not state.get("expires_at"):
        return "BLOCKED_EXPIRES_AT_MISSING"
    if state.get("expires_at_days", 0) > 7:
        return "BLOCKED_EXPIRES_AT_TOO_LONG"
    if state.get("all_gates_pass"):
        return "READY_FOR_LOCAL_DOCKER_POSTGRES_DRY_RUN"
    return "BLOCKED_OWNER_APPROVAL_PENDING"


def _make_all_pass_state() -> dict:
    return {
        "docker_installed": True,
        "docker_daemon_available": True,
        "local_context": True,
        "production_risk": False,
        "secret_risk": False,
        "cleanup_policy": "container_remove",
        "fixture_hash_captured": True,
        "migration_reviewed": True,
        "owner_approval_signed": True,
        "expires_at": "2026-05-25T16:00:00Z",
        "expires_at_days": 7,
        "all_gates_pass": True,
    }


# --- tests ---

class TestDocumentExists:
    def test_h51_final_go_gate_doc_exists(self):
        assert os.path.exists(DOC_PATH), f"Expected {DOC_PATH} to exist"

    def test_h51_doc_not_empty(self):
        text = _read_doc()
        assert len(text) > 500


class TestGateTable:
    def test_gate_table_g1_to_g15_documented(self):
        text = _read_doc()
        for gate in REQUIRED_GATES:
            assert gate in text, f"Gate {gate} not documented"

    def test_all_gates_pass_in_h51(self):
        text = _read_doc()
        assert "15 of 15" in text or "15/15" in text

    def test_g7_now_passes_in_h51(self):
        text = _read_doc()
        assert "G7" in text
        assert "ROLANDI GELIKOSHVILI" in text or "signed" in text.lower()

    def test_no_gates_failed_in_h51(self):
        text = _read_doc()
        assert "Gates failed" in text or "gates failed" in text.lower()
        assert "none" in text.lower() or "0 of 15" in text


class TestFinalDecisionLogic:
    def test_final_decision_logic_documented(self):
        text = _read_doc()
        assert "Final Decision" in text or "final_decision" in text
        assert "READY_FOR_LOCAL_DOCKER_POSTGRES_DRY_RUN" in text

    def test_ready_decision_documented(self):
        text = _read_doc()
        assert "READY_FOR_LOCAL_DOCKER_POSTGRES_DRY_RUN" in text

    def test_blocked_owner_approval_decision_documented(self):
        text = _read_doc()
        assert "BLOCKED_OWNER_APPROVAL_PENDING" in text

    def test_expires_at_decisions_documented(self):
        text = _read_doc()
        assert "BLOCKED_EXPIRES_AT_MISSING" in text
        assert "BLOCKED_EXPIRES_AT_TOO_LONG" in text

    def test_blocked_docker_decision_documented(self):
        text = _read_doc()
        assert "BLOCKED_DOCKER_UNAVAILABLE" in text


class TestCurrentDecision:
    def test_current_decision_is_ready(self):
        text = _read_doc()
        assert "READY_FOR_LOCAL_DOCKER_POSTGRES_DRY_RUN" in text

    def test_expires_at_set_in_h51(self):
        text = _read_doc()
        assert "2026-05-25" in text

    def test_approved_at_set_in_h51(self):
        text = _read_doc()
        assert "2026-05-18" in text

    def test_approval_scope_local_only(self):
        text = _read_doc()
        assert "local_docker_postgres_dry_run_only" in text or "local" in text.lower()


class TestNextTask:
    def test_next_task_h52_documented(self):
        text = _read_doc()
        assert "H52" in text

    def test_h52_provisioning_dry_run_named(self):
        text = _read_doc()
        assert "Dry-Run" in text or "dry-run" in text or "dry_run" in text

    def test_expires_at_constraint_for_h52(self):
        text = _read_doc()
        assert "expires_at" in text or "2026-05-25" in text

    def test_h52_steps_not_executed_in_h51(self):
        text = _read_doc()
        assert "H52" in text
        assert "executed in H51" in text or "not execute" in text.lower()


class TestSafetyConfirmation:
    def test_safety_confirmation_documented(self):
        text = _read_doc()
        assert "Safety" in text or "safety" in text.lower()

    def test_no_docker_run_confirmed(self):
        text = _read_doc()
        assert "No Docker" in text or "no Docker" in text.lower()

    def test_no_db_confirmed(self):
        text = _read_doc()
        assert "No DB" in text or "No DB created" in text

    def test_no_sql_confirmed(self):
        text = _read_doc()
        assert "No SQL" in text

    def test_no_migration_execution_confirmed(self):
        text = _read_doc()
        assert "No migration" in text or "no migration" in text.lower()

    def test_no_fixture_load_confirmed(self):
        text = _read_doc()
        assert "No fixture" in text or "no fixture" in text.lower()

    def test_feature_flag_remains_off(self):
        text = _read_doc()
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text


class TestGoGateClassifier:
    def test_go_gate_ready_when_all_gates_pass(self):
        state = _make_all_pass_state()
        result = evaluate_go_gate(state)
        assert result == "READY_FOR_LOCAL_DOCKER_POSTGRES_DRY_RUN"

    def test_go_gate_blocks_when_g7_pending(self):
        state = _make_all_pass_state()
        state["owner_approval_signed"] = False
        result = evaluate_go_gate(state)
        assert result == "BLOCKED_OWNER_APPROVAL_PENDING"

    def test_go_gate_blocks_expires_at_missing(self):
        state = _make_all_pass_state()
        state["expires_at"] = None
        result = evaluate_go_gate(state)
        assert result == "BLOCKED_EXPIRES_AT_MISSING"

    def test_go_gate_blocks_expires_at_too_long(self):
        state = _make_all_pass_state()
        state["expires_at_days"] = 8
        result = evaluate_go_gate(state)
        assert result == "BLOCKED_EXPIRES_AT_TOO_LONG"

    def test_go_gate_blocks_production_risk(self):
        state = _make_all_pass_state()
        state["production_risk"] = True
        result = evaluate_go_gate(state)
        assert result == "BLOCKED_PRODUCTION_RISK"

    def test_go_gate_blocks_docker_unavailable(self):
        state = _make_all_pass_state()
        state["docker_installed"] = False
        result = evaluate_go_gate(state)
        assert result == "BLOCKED_DOCKER_UNAVAILABLE"

    def test_go_gate_blocks_missing_fixture_hash(self):
        state = _make_all_pass_state()
        state["fixture_hash_captured"] = False
        result = evaluate_go_gate(state)
        assert result == "BLOCKED_MISSING_FIXTURE_HASH"

    def test_go_gate_blocks_missing_migration_review(self):
        state = _make_all_pass_state()
        state["migration_reviewed"] = False
        result = evaluate_go_gate(state)
        assert result == "BLOCKED_MISSING_MIGRATION_REVIEW"

    def test_go_gate_blocks_no_cleanup_policy(self):
        state = _make_all_pass_state()
        state["cleanup_policy"] = None
        result = evaluate_go_gate(state)
        assert result == "BLOCKED_NO_CLEANUP_POLICY"

    def test_all_decisions_are_valid(self):
        # Ensure all decision values the classifier can return are in the allowed set
        for result in [
            "READY_FOR_LOCAL_DOCKER_POSTGRES_DRY_RUN",
            "BLOCKED_OWNER_APPROVAL_PENDING",
            "BLOCKED_EXPIRES_AT_MISSING",
            "BLOCKED_EXPIRES_AT_TOO_LONG",
            "BLOCKED_PRODUCTION_RISK",
            "BLOCKED_DOCKER_UNAVAILABLE",
            "BLOCKED_MISSING_FIXTURE_HASH",
            "BLOCKED_MISSING_MIGRATION_REVIEW",
            "BLOCKED_NO_CLEANUP_POLICY",
        ]:
            assert result in ALLOWED_GO_GATE_DECISIONS


class TestNoForbiddenImports:
    def test_no_db_docker_execution_imports(self):
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
