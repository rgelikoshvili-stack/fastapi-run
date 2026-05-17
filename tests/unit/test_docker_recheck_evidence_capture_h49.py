"""
Tests for docs/docker-recheck-evidence-capture-h49.md (H49).

H49 recaptured Docker evidence after Docker Desktop 4.73.0 was installed.
All 7 read-only commands succeeded. Context is local-only (desktop-linux).
H49 decision: DOCKER_EVIDENCE_CAPTURED.
No container, DB, SQL, migration, fixture, runtime API, Cloud Run mutation, or feature flag.
"""

import os
import pytest

DOC_PATH = "docs/docker-recheck-evidence-capture-h49.md"

REQUIRED_EVIDENCE_COMMANDS = [
    "docker --version",
    "docker version",
    "docker context ls",
    "docker info",
    "docker ps",
    "docker volume ls",
    "docker network ls",
]

ALLOWED_DECISIONS = {
    "DOCKER_EVIDENCE_CAPTURED",
    "BLOCKED_DOCKER_UNAVAILABLE",
    "BLOCKED_DAEMON_UNAVAILABLE",
    "BLOCKED_REMOTE_CONTEXT",
    "BLOCKED_PRODUCTION_RISK",
}

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
    "ready_for_h50",
    "created_at",
    "created_by",
]


def _read_doc():
    with open(DOC_PATH, "r", encoding="utf-8") as f:
        return f.read()


def validate_h49_packet(packet: dict) -> list:
    """Validate an H49 evidence packet. Returns list of errors."""
    errors = []
    for field in REQUIRED_PACKET_FIELDS:
        if field not in packet:
            errors.append(f"missing field: {field}")
    if packet.get("docker_installed") is not True:
        errors.append("docker_installed must be true in H49")
    if packet.get("docker_daemon_available") is not True:
        errors.append("docker_daemon_available must be true in H49")
    if packet.get("host_classification") != "local_only":
        errors.append(f"host_classification must be local_only, got {packet.get('host_classification')!r}")
    if packet.get("production_risk") is not False:
        errors.append("production_risk must be false")
    return errors


def classify_h49_evidence(evidence: dict) -> str:
    """Classify H49 Docker evidence and return decision."""
    if not evidence.get("docker_installed"):
        return "BLOCKED_DOCKER_UNAVAILABLE"
    if not evidence.get("docker_daemon_available"):
        return "BLOCKED_DAEMON_UNAVAILABLE"
    host = evidence.get("host_classification", "unknown")
    if host == "production_risk":
        return "BLOCKED_PRODUCTION_RISK"
    if host == "remote":
        return "BLOCKED_REMOTE_CONTEXT"
    if evidence.get("production_risk"):
        return "BLOCKED_PRODUCTION_RISK"
    if evidence.get("docker_installed") and evidence.get("docker_daemon_available"):
        return "DOCKER_EVIDENCE_CAPTURED"
    return "BLOCKED_DOCKER_UNAVAILABLE"


# --- tests ---

class TestDocumentExists:
    def test_h49_doc_exists(self):
        assert os.path.exists(DOC_PATH), f"Expected {DOC_PATH} to exist"

    def test_h49_doc_not_empty(self):
        text = _read_doc()
        assert len(text) > 500


class TestH49Purpose:
    def test_h49_purpose_documented(self):
        text = _read_doc()
        assert "H49" in text
        assert "Recheck" in text or "recheck" in text

    def test_h49_non_action_statement_present(self):
        text = _read_doc()
        assert "does NOT" in text or "NOT create" in text

    def test_h49_no_container(self):
        text = _read_doc()
        assert "NOT create any Docker container" in text or "not create" in text.lower()

    def test_h49_no_cloud_run_mutation(self):
        text = _read_doc()
        assert "NOT mutate Cloud Run" in text or "not mutate Cloud Run" in text.lower()

    def test_posted_ledger_flag_not_enabled(self):
        text = _read_doc()
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text


class TestH49Context:
    def test_h41_context_documented(self):
        text = _read_doc()
        assert "H41" in text
        assert "BLOCKED_DOCKER_UNAVAILABLE" in text

    def test_installation_steps_documented(self):
        text = _read_doc()
        assert "Docker Desktop" in text
        assert "WSL" in text or "wsl" in text.lower()


class TestCommandsExecutedSection:
    def test_commands_executed_section_present(self):
        text = _read_doc()
        assert "Commands Executed" in text or "commands_executed" in text

    def test_all_allowed_commands_documented(self):
        text = _read_doc()
        for cmd in REQUIRED_EVIDENCE_COMMANDS:
            assert cmd in text, f"Command {cmd!r} not documented"

    def test_all_commands_succeeded(self):
        text = _read_doc()
        assert "commands_failed" in text
        assert '"commands_failed": []' in text or "commands_failed: []" in text


class TestDockerInstalledProof:
    def test_docker_installed_proof_documented(self):
        text = _read_doc()
        assert "Docker Installed Proof" in text or "docker_installed" in text

    def test_installed_true_documented(self):
        text = _read_doc()
        assert '"docker_installed": true' in text or "docker_installed: true" in text or "docker_installed | **true**" in text


class TestDockerDaemonProof:
    def test_docker_daemon_proof_documented(self):
        text = _read_doc()
        assert "Docker Daemon Proof" in text or "docker_daemon_available" in text

    def test_daemon_available_true_documented(self):
        text = _read_doc()
        assert '"docker_daemon_available": true' in text or "docker_daemon_available | **true**" in text


class TestDockerContextProof:
    def test_docker_context_proof_documented(self):
        text = _read_doc()
        assert "Docker Context Proof" in text or "docker_context" in text

    def test_desktop_linux_context_documented(self):
        text = _read_doc()
        assert "desktop-linux" in text

    def test_local_pipe_documented(self):
        text = _read_doc()
        assert "npipe" in text or "local" in text.lower()

    def test_local_only_classification(self):
        text = _read_doc()
        assert "local_only" in text


class TestProductionRiskScan:
    def test_production_risk_scan_documented(self):
        text = _read_doc()
        assert "Production Risk" in text or "production_risk" in text

    def test_no_production_risk_in_captured_evidence(self):
        text = _read_doc()
        assert '"production_risk": false' in text or "production_risk: false" in text or (
            "production_risk | **false**" in text
        )


class TestH49EvidencePacket:
    def test_h49_evidence_packet_documented(self):
        text = _read_doc()
        assert "docker_evidence_id" in text
        assert "ready_for_h50" in text

    def test_packet_id_documented(self):
        text = _read_doc()
        assert "DOCKER-EV-2026-H49-001" in text

    def _make_packet(self):
        return {
            "docker_evidence_id": "DOCKER-EV-2026-H49-001",
            "docker_installed": True,
            "docker_daemon_available": True,
            "docker_context": "desktop-linux",
            "host_classification": "local_only",
            "commands_executed": [
                "docker --version", "docker version", "docker context ls",
                "docker info", "docker ps", "docker volume ls", "docker network ls",
            ],
            "commands_failed": [],
            "redaction_required": False,
            "production_risk": False,
            "ready_for_h50": True,
            "created_at": "2026-05-18T00:00:00Z",
            "created_by": "Bridge Hub",
        }

    def test_packet_valid_when_complete(self):
        errors = validate_h49_packet(self._make_packet())
        assert errors == []

    def test_packet_missing_field_detected(self):
        packet = self._make_packet()
        del packet["ready_for_h50"]
        errors = validate_h49_packet(packet)
        assert any("ready_for_h50" in e for e in errors)

    def test_packet_requires_docker_installed_true(self):
        packet = self._make_packet()
        packet["docker_installed"] = False
        errors = validate_h49_packet(packet)
        assert any("docker_installed" in e for e in errors)

    def test_packet_requires_local_only_host(self):
        packet = self._make_packet()
        packet["host_classification"] = "remote"
        errors = validate_h49_packet(packet)
        assert any("host_classification" in e for e in errors)


class TestH49DecisionOutputs:
    def test_h49_decision_outputs_documented(self):
        text = _read_doc()
        assert "DOCKER_EVIDENCE_CAPTURED" in text

    def test_current_decision_captured(self):
        text = _read_doc()
        assert "DOCKER_EVIDENCE_CAPTURED" in text

    def test_classifier_docker_installed_local(self):
        result = classify_h49_evidence({
            "docker_installed": True,
            "docker_daemon_available": True,
            "host_classification": "local_only",
            "production_risk": False,
        })
        assert result == "DOCKER_EVIDENCE_CAPTURED"

    def test_classifier_docker_not_installed(self):
        result = classify_h49_evidence({"docker_installed": False})
        assert result == "BLOCKED_DOCKER_UNAVAILABLE"

    def test_classifier_daemon_unavailable(self):
        result = classify_h49_evidence({
            "docker_installed": True,
            "docker_daemon_available": False,
        })
        assert result == "BLOCKED_DAEMON_UNAVAILABLE"

    def test_classifier_remote_context_blocked(self):
        result = classify_h49_evidence({
            "docker_installed": True,
            "docker_daemon_available": True,
            "host_classification": "remote",
            "production_risk": False,
        })
        assert result == "BLOCKED_REMOTE_CONTEXT"

    def test_classifier_production_risk_blocked(self):
        result = classify_h49_evidence({
            "docker_installed": True,
            "docker_daemon_available": True,
            "host_classification": "production_risk",
            "production_risk": True,
        })
        assert result == "BLOCKED_PRODUCTION_RISK"


class TestH49SafetyConfirmation:
    def test_h49_safety_confirmation_documented(self):
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
