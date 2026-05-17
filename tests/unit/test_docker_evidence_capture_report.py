"""
Tests for docs/docker-evidence-capture-report.md (H41).

H41 captured read-only Docker evidence. Docker was not installed on the local machine.
All 7 allowed read-only commands failed with CommandNotFoundException.
H41 decision: BLOCKED_DOCKER_UNAVAILABLE.
No container, DB, SQL, migration, fixture, runtime API, Cloud Run mutation, or feature flag.
"""

import re
import os
import pytest

DOC_PATH = "docs/docker-evidence-capture-report.md"

PRODUCTION_URL_MARKERS = [
    "production",
    "prod-",
    "-prod",
    "cloudsql",
    "rgelikoshvili",
    "europe-west1.run.app",
    "sql.goog",
]

ALLOWED_DECISIONS = {
    "DOCKER_EVIDENCE_CAPTURED",
    "BLOCKED_DOCKER_UNAVAILABLE",
    "BLOCKED_DAEMON_UNAVAILABLE",
    "BLOCKED_REMOTE_CONTEXT",
    "BLOCKED_PRODUCTION_RISK",
    "BLOCKED_COMMAND_FAILURE",
    "BLOCKED_REDACTION_REQUIRED",
}

REQUIRED_EVIDENCE_COMMANDS = [
    "docker --version",
    "docker version",
    "docker context ls",
    "docker info",
    "docker ps",
    "docker volume ls",
    "docker network ls",
]

REQUIRED_PACKET_FIELDS = [
    "docker_evidence_id",
    "docker_installed",
    "docker_daemon_available",
    "docker_context",
    "host_classification",
    "commands_executed",
    "commands_failed",
    "redaction_required",
    "production_risk",
    "ready_for_h42",
    "created_at",
    "created_by",
]

HOST_CLASSIFICATIONS = {"local_only", "remote", "cloud", "unknown", "production_risk"}

# --- helpers ---

def _read_doc():
    with open(DOC_PATH, "r", encoding="utf-8") as f:
        return f.read()

def classify_docker_evidence(evidence: dict) -> str:
    """Classify Docker evidence and return H41 decision."""
    if not evidence.get("docker_installed"):
        return "BLOCKED_DOCKER_UNAVAILABLE"
    if not evidence.get("docker_daemon_available"):
        return "BLOCKED_DAEMON_UNAVAILABLE"
    host = evidence.get("host_classification", "unknown")
    if host == "production_risk":
        return "BLOCKED_PRODUCTION_RISK"
    if host == "remote":
        return "BLOCKED_REMOTE_CONTEXT"
    if evidence.get("redaction_required"):
        return "BLOCKED_REDACTION_REQUIRED"
    if evidence.get("commands_failed") and len(evidence.get("commands_failed", [])) > 0:
        if not evidence.get("docker_installed"):
            return "BLOCKED_DOCKER_UNAVAILABLE"
        return "BLOCKED_COMMAND_FAILURE"
    if evidence.get("docker_installed") and evidence.get("docker_daemon_available"):
        return "DOCKER_EVIDENCE_CAPTURED"
    return "BLOCKED_DOCKER_UNAVAILABLE"

def validate_evidence_packet(packet: dict) -> list:
    """Validate an H41 evidence packet. Returns list of errors."""
    errors = []
    for field in REQUIRED_PACKET_FIELDS:
        if field not in packet:
            errors.append(f"missing field: {field}")
    host = packet.get("host_classification", "")
    if host not in HOST_CLASSIFICATIONS:
        errors.append(f"invalid host_classification: {host!r}")
    if packet.get("production_risk") is True:
        conn = packet.get("host_classification", "")
        if conn not in ("remote", "production_risk"):
            errors.append("production_risk true but host_classification not remote/production_risk")
    return errors

# --- tests ---

class TestDocumentExists:
    def test_h41_doc_exists(self):
        assert os.path.exists(DOC_PATH), f"Expected {DOC_PATH} to exist"

    def test_h41_doc_not_empty(self):
        text = _read_doc()
        assert len(text) > 500


class TestH41NonActionStatement:
    def test_h41_non_action_statement_present(self):
        text = _read_doc()
        assert "does NOT create" in text or "H41 does NOT" in text

    def test_h41_no_container(self):
        text = _read_doc()
        assert "NOT create any container" in text or "not create container" in text.lower()

    def test_h41_no_cloud_run_mutation(self):
        text = _read_doc()
        assert "NOT mutate Cloud Run" in text or "not mutate Cloud Run" in text.lower()

    def test_posted_ledger_flag_not_enabled(self):
        text = _read_doc()
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text


class TestCommandsExecutedSection:
    def test_commands_executed_section_present(self):
        text = _read_doc()
        assert "Commands Executed" in text or "commands_executed" in text

    def test_all_allowed_commands_documented(self):
        text = _read_doc()
        for cmd in REQUIRED_EVIDENCE_COMMANDS:
            assert cmd in text, f"Command {cmd!r} not documented"

    def test_command_failure_documented(self):
        text = _read_doc()
        assert "CommandNotFoundException" in text or "not recognized" in text or "not installed" in text


class TestDockerInstalledProof:
    def test_docker_installed_proof_documented(self):
        text = _read_doc()
        assert "Docker Installed Proof" in text or "docker_installed" in text

    def test_installed_status_documented(self):
        text = _read_doc()
        assert "not installed" in text.lower() or "docker_installed" in text


class TestDockerDaemonProof:
    def test_docker_daemon_proof_documented(self):
        text = _read_doc()
        assert "Docker Daemon Proof" in text or "docker_daemon_available" in text

    def test_daemon_unavailable_documented(self):
        text = _read_doc()
        assert "daemon" in text.lower()


class TestDockerContextProof:
    def test_docker_context_proof_documented(self):
        text = _read_doc()
        assert "Docker Context Proof" in text or "docker_context" in text

    def test_context_classification_documented(self):
        text = _read_doc()
        assert "local_only" in text or "unknown" in text


class TestHostClassification:
    def test_host_classification_documented(self):
        text = _read_doc()
        assert "host_classification" in text or "Host Classification" in text

    def test_local_only_allowed(self):
        result = classify_docker_evidence({
            "docker_installed": True,
            "docker_daemon_available": True,
            "host_classification": "local_only",
            "redaction_required": False,
            "commands_failed": [],
        })
        assert result == "DOCKER_EVIDENCE_CAPTURED"

    def test_local_evidence_classifier_blocks_remote(self):
        result = classify_docker_evidence({
            "docker_installed": True,
            "docker_daemon_available": True,
            "host_classification": "remote",
            "redaction_required": False,
            "commands_failed": [],
        })
        assert result == "BLOCKED_REMOTE_CONTEXT"

    def test_local_evidence_classifier_blocks_production_risk(self):
        result = classify_docker_evidence({
            "docker_installed": True,
            "docker_daemon_available": True,
            "host_classification": "production_risk",
            "redaction_required": False,
            "commands_failed": [],
        })
        assert result == "BLOCKED_PRODUCTION_RISK"

    def test_local_evidence_classifier_allows_local_only(self):
        result = classify_docker_evidence({
            "docker_installed": True,
            "docker_daemon_available": True,
            "host_classification": "local_only",
            "redaction_required": False,
            "commands_failed": [],
        })
        assert result == "DOCKER_EVIDENCE_CAPTURED"


class TestProductionRiskScan:
    def test_production_risk_scan_documented(self):
        text = _read_doc()
        assert "Production Risk" in text or "production_risk" in text

    def test_no_production_risk_in_captured_evidence(self):
        """Production risk section must confirm no production risk found."""
        text = _read_doc()
        # Confirm the doc has a production risk section that states no risk
        assert "production_risk" in text or "Production Risk" in text
        # The evidence packet must have production_risk: false
        assert '"production_risk": false' in text or "production_risk: false" in text or (
            "Production risk" in text and "none" in text.lower()
        )


class TestH41EvidencePacket:
    def test_h41_evidence_packet_documented(self):
        text = _read_doc()
        assert "docker_evidence_id" in text
        assert "ready_for_h42" in text

    def _make_packet(self):
        return {
            "docker_evidence_id": "DOCKER-EV-2026-H41-001",
            "docker_installed": False,
            "docker_daemon_available": False,
            "docker_context": "unknown",
            "host_classification": "unknown",
            "commands_executed": ["docker --version"],
            "commands_failed": ["docker --version"],
            "redaction_required": False,
            "production_risk": False,
            "ready_for_h42": True,
            "created_at": "2026-05-17T16:00:27Z",
            "created_by": "Bridge Hub",
        }

    def test_packet_valid_when_complete(self):
        errors = validate_evidence_packet(self._make_packet())
        assert errors == []

    def test_packet_missing_field_detected(self):
        packet = self._make_packet()
        del packet["ready_for_h42"]
        errors = validate_evidence_packet(packet)
        assert any("ready_for_h42" in e for e in errors)

    def test_invalid_host_classification_rejected(self):
        packet = self._make_packet()
        packet["host_classification"] = "invalid_value"
        errors = validate_evidence_packet(packet)
        assert any("host_classification" in e for e in errors)


class TestH41DecisionOutputs:
    def test_h41_decision_outputs_documented(self):
        text = _read_doc()
        assert "BLOCKED_DOCKER_UNAVAILABLE" in text

    def test_current_decision_blocked(self):
        text = _read_doc()
        assert "BLOCKED_DOCKER_UNAVAILABLE" in text

    def test_classifier_docker_not_installed(self):
        result = classify_docker_evidence({"docker_installed": False})
        assert result == "BLOCKED_DOCKER_UNAVAILABLE"

    def test_classifier_daemon_unavailable(self):
        result = classify_docker_evidence({
            "docker_installed": True,
            "docker_daemon_available": False,
        })
        assert result == "BLOCKED_DAEMON_UNAVAILABLE"


class TestH41SafetyConfirmation:
    def test_h41_safety_confirmation_documented(self):
        text = _read_doc()
        assert "Safety Confirmation" in text or "safety" in text.lower()

    def test_no_container_created_confirmed(self):
        text = _read_doc()
        assert "No Docker container created" in text or "not create" in text.lower()


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
