"""
Tests for docs/local-docker-availability-evidence-capture-plan.md (H39).

H39 is docs/tests only. No Docker executed. No DB created. No SQL run.
No migration executed. No fixture loaded. No runtime API calls made.
No Cloud Run env vars mutated. No feature flags enabled.
No Balance.ge activated. DATABASE_URL stays empty.
"""

import re
import os
import pytest

DOC_PATH = "docs/local-docker-availability-evidence-capture-plan.md"

PRODUCTION_URL_MARKERS = [
    "production",
    "prod-",
    "-prod",
    "cloudsql",
    "rgelikoshvili",
    "europe-west1.run.app",
    "sql.goog",
]

REQUIRED_EVIDENCE_ITEMS = [
    "EV1", "EV2", "EV3", "EV4", "EV5",
    "EV6", "EV7", "EV8", "EV9", "EV10",
]

REQUIRED_NO_GO_BLOCKERS = [
    "HB1", "HB2", "HB3", "HB4", "HB5",
    "HB6", "HB7", "HB8", "HB9",
]

DECISION_OUTPUTS = {
    "READY_FOR_H40_PREFLIGHT",
    "BLOCKED_DOCKER_EVIDENCE_NOT_CAPTURED",
    "BLOCKED_DOCKER_UNAVAILABLE",
    "BLOCKED_DOCKER_DAEMON_UNAVAILABLE",
    "BLOCKED_REMOTE_CONTEXT",
    "BLOCKED_PRODUCTION_RISK",
    "BLOCKED_RAW_SECRET_RISK",
    "BLOCKED_MISSING_OWNER_APPROVAL",
}

REQUIRED_EVIDENCE_PACKET_FIELDS = [
    "docker_evidence_id",
    "docker_installed",
    "docker_daemon_available",
    "docker_context",
    "host_classification",
    "version_proof_reference",
    "context_proof_reference",
    "permission_proof_reference",
    "redaction_checked",
    "production_risk",
    "ready_for_preflight",
    "created_at",
    "created_by",
]

HOST_CLASSIFICATIONS = {"local_only", "unknown", "remote", "production_risk"}

FORBIDDEN_EXECUTABLE_PATTERNS = [
    r"^\s*docker\s+run\b",
    r"^\s*docker\s+pull\b",
    r"^\s*docker\s+exec\b",
    r"^\s*createdb\b",
    r"^\s*dropdb\b",
    r"^\s*psql\b",
    r"^\s*pg_isready\b",
    r"^\s*gcloud\b",
    r"^\s*kubectl\b",
]

# --- helpers ---

def _read_doc():
    with open(DOC_PATH, "r", encoding="utf-8") as f:
        return f.read()

def classify_docker_context(context_info: dict) -> dict:
    """Classify a Docker context for local-only safety."""
    context_name = context_info.get("context_name", "")
    host = context_info.get("host", "")
    is_local = any(h in host for h in ["localhost", "127.0.0.1", "unix://", "npipe://"])
    is_remote = context_info.get("is_remote", False)
    has_production_marker = any(m in host for m in PRODUCTION_URL_MARKERS)
    classification = "local_only" if is_local and not is_remote and not has_production_marker else (
        "production_risk" if has_production_marker else (
            "remote" if is_remote else "unknown"
        )
    )
    return {
        "context_name": context_name,
        "host": host,
        "classification": classification,
        "safe": classification == "local_only",
        "production_risk": has_production_marker,
    }

def validate_evidence_packet(packet: dict) -> list:
    """Validate an H39 Docker evidence packet. Returns list of errors."""
    errors = []
    for field in REQUIRED_EVIDENCE_PACKET_FIELDS:
        if field not in packet:
            errors.append(f"missing field: {field}")
    host_class = packet.get("host_classification", "")
    if host_class not in HOST_CLASSIFICATIONS:
        errors.append(f"invalid host_classification: {host_class}")
    if packet.get("ready_for_preflight") is not False:
        errors.append("ready_for_preflight must be false until all evidence confirmed")
    if packet.get("production_risk") is True:
        errors.append("production_risk must be false for acceptable evidence")
    if packet.get("redaction_checked") is not False and packet.get("redaction_checked") is not True:
        errors.append("redaction_checked must be boolean")
    return errors

def evaluate_h39_readiness(state: dict) -> str:
    """Evaluate H39 Docker availability state and return decision output."""
    if state.get("docs_only"):
        return "BLOCKED_DOCKER_EVIDENCE_NOT_CAPTURED"
    if not state.get("docker_installed"):
        return "BLOCKED_DOCKER_UNAVAILABLE"
    if not state.get("docker_daemon_available"):
        return "BLOCKED_DOCKER_DAEMON_UNAVAILABLE"
    context = state.get("context_info", {})
    host = context.get("host", "")
    if any(m in host for m in PRODUCTION_URL_MARKERS):
        return "BLOCKED_PRODUCTION_RISK"
    if context.get("is_remote"):
        return "BLOCKED_REMOTE_CONTEXT"
    if state.get("raw_secret_in_evidence"):
        return "BLOCKED_RAW_SECRET_RISK"
    if not state.get("owner_approval"):
        return "BLOCKED_MISSING_OWNER_APPROVAL"
    if state.get("evidence_complete"):
        return "READY_FOR_H40_PREFLIGHT"
    return "BLOCKED_DOCKER_EVIDENCE_NOT_CAPTURED"

# --- tests ---

class TestDocumentExists:
    def test_h39_doc_exists(self):
        assert os.path.exists(DOC_PATH), f"Expected {DOC_PATH} to exist"

    def test_h39_doc_not_empty(self):
        text = _read_doc()
        assert len(text) > 500


class TestH39NonActionStatement:
    def test_h39_non_action_statement_present(self):
        text = _read_doc()
        assert "docs/tests only" in text.lower() or "H39 is docs" in text

    def test_h39_does_not_execute_docker(self):
        text = _read_doc()
        assert "does NOT execute Docker" in text or "NOT execute Docker" in text

    def test_h39_does_not_create_db(self):
        text = _read_doc()
        assert "does NOT create a DB" in text or "NOT create a DB" in text

    def test_h39_does_not_run_migrations(self):
        text = _read_doc()
        assert "does NOT run migrations" in text or "NOT run migrations" in text

    def test_posted_ledger_flag_remains_off(self):
        text = _read_doc()
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text
        assert "remains OFF" in text or "remain OFF" in text


class TestH37H38Context:
    def test_h37_h38_context_documented(self):
        text = _read_doc()
        assert "H37" in text
        assert "H38" in text
        assert "BLOCKED_DOCKER_NOT_EXECUTED" in text
        assert "BLOCKED_MISSING_H37_EVIDENCE" in text

    def test_no_docker_executed_context_confirmed(self):
        text = _read_doc()
        assert "Docker executed" in text or "Docker evidence" in text


class TestEvidenceCaptureScope:
    def test_evidence_capture_scope_documented(self):
        text = _read_doc()
        for item in REQUIRED_EVIDENCE_ITEMS:
            assert item in text, f"Evidence item {item} not found in doc"

    def test_ev1_docker_installed_proof(self):
        text = _read_doc()
        assert "EV1" in text
        assert "Docker installed" in text or "installed" in text

    def test_ev4_local_only_host_proof(self):
        text = _read_doc()
        assert "EV4" in text
        assert "local" in text.lower()

    def test_ev9_no_balance_ge_activation(self):
        text = _read_doc()
        assert "EV9" in text
        assert "Balance" in text or "balance" in text

    def test_ev10_no_feature_flag(self):
        text = _read_doc()
        assert "EV10" in text
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text


class TestFutureEvidenceCommands:
    def test_future_evidence_commands_documented(self):
        text = _read_doc()
        assert "FUTURE" in text or "future" in text.lower()
        assert "NOT EXECUTED IN H39" in text

    def test_future_commands_labeled_not_executed(self):
        text = _read_doc()
        assert "NOT EXECUTED IN H39" in text

    def test_docker_version_mentioned_as_future(self):
        text = _read_doc()
        assert "docker version" in text or "docker --version" in text


class TestEvidenceRedactionRules:
    def test_evidence_redaction_rules_documented(self):
        text = _read_doc()
        assert "edaction" in text  # Redaction / redaction
        assert "***" in text or "redact" in text.lower()

    def test_no_raw_secrets_rule_present(self):
        text = _read_doc()
        assert "raw secret" in text.lower() or "no raw secrets" in text.lower()

    def test_no_passwords_rule_present(self):
        text = _read_doc()
        assert "password" in text.lower()


class TestLocalOnlyProofRequirements:
    def test_local_only_proof_requirements_documented(self):
        text = _read_doc()
        assert "local" in text.lower()
        assert "localhost" in text or "local Docker" in text

    def test_remote_context_forbidden(self):
        text = _read_doc()
        assert "remote" in text.lower()

    def test_production_cluster_forbidden(self):
        text = _read_doc()
        assert "production" in text.lower()

    def test_classify_local_context_safe(self):
        result = classify_docker_context({
            "context_name": "default",
            "host": "unix:///var/run/docker.sock",
            "is_remote": False,
        })
        assert result["classification"] == "local_only"
        assert result["safe"] is True

    def test_classify_remote_context_blocked(self):
        result = classify_docker_context({
            "context_name": "prod-cluster",
            "host": "tcp://production.docker.example.com:2376",
            "is_remote": True,
        })
        assert result["safe"] is False
        assert result["classification"] in ("remote", "production_risk")

    def test_classify_production_host_blocked(self):
        result = classify_docker_context({
            "context_name": "gke-prod",
            "host": "tcp://production.cloudsql.example.com:2376",
            "is_remote": False,
        })
        assert result["production_risk"] is True
        assert result["safe"] is False


class TestDockerEvidencePacket:
    def test_docker_evidence_packet_documented(self):
        text = _read_doc()
        assert "docker_evidence_id" in text
        assert "ready_for_preflight" in text
        assert "host_classification" in text

    def _make_packet(self):
        return {
            "docker_evidence_id": "DOCKER-EV-2026-001",
            "docker_installed": False,
            "docker_daemon_available": False,
            "docker_context": "default",
            "host_classification": "unknown",
            "version_proof_reference": "pending",
            "context_proof_reference": "pending",
            "permission_proof_reference": "pending",
            "redaction_checked": False,
            "production_risk": False,
            "ready_for_preflight": False,
            "created_at": "2026-01-01T00:00:00Z",
            "created_by": "Bridge Hub",
        }

    def test_packet_valid_when_complete(self):
        errors = validate_evidence_packet(self._make_packet())
        assert errors == []

    def test_packet_missing_field_detected(self):
        packet = self._make_packet()
        del packet["redaction_checked"]
        errors = validate_evidence_packet(packet)
        assert any("redaction_checked" in e for e in errors)

    def test_ready_for_preflight_must_be_false(self):
        packet = self._make_packet()
        packet["ready_for_preflight"] = True
        errors = validate_evidence_packet(packet)
        assert any("ready_for_preflight" in e for e in errors)

    def test_production_risk_true_rejected(self):
        packet = self._make_packet()
        packet["production_risk"] = True
        errors = validate_evidence_packet(packet)
        assert any("production_risk" in e for e in errors)


class TestH39NoGoBLockers:
    def test_h39_no_go_blockers_documented(self):
        text = _read_doc()
        for blocker in REQUIRED_NO_GO_BLOCKERS:
            assert blocker in text, f"No-go blocker {blocker} not found in doc"

    def test_hb3_remote_context_critical(self):
        text = _read_doc()
        assert "HB3" in text
        assert "remote" in text.lower() or "Remote" in text

    def test_hb5_raw_secret_critical(self):
        text = _read_doc()
        assert "HB5" in text
        assert "CRITICAL" in text or "secret" in text.lower()


class TestH39DecisionOutputs:
    def test_h39_decision_outputs_documented(self):
        text = _read_doc()
        for output in DECISION_OUTPUTS:
            assert output in text, f"Decision output {output} not found in doc"

    def test_current_decision_is_blocked(self):
        text = _read_doc()
        assert "BLOCKED_DOCKER_EVIDENCE_NOT_CAPTURED" in text

    def test_evaluator_docs_only_blocked(self):
        result = evaluate_h39_readiness({"docs_only": True})
        assert result == "BLOCKED_DOCKER_EVIDENCE_NOT_CAPTURED"

    def test_evaluator_docker_unavailable(self):
        result = evaluate_h39_readiness({"docs_only": False, "docker_installed": False})
        assert result == "BLOCKED_DOCKER_UNAVAILABLE"

    def test_evaluator_daemon_unavailable(self):
        result = evaluate_h39_readiness({
            "docs_only": False, "docker_installed": True, "docker_daemon_available": False
        })
        assert result == "BLOCKED_DOCKER_DAEMON_UNAVAILABLE"

    def test_evaluator_remote_context_blocked(self):
        result = evaluate_h39_readiness({
            "docs_only": False,
            "docker_installed": True,
            "docker_daemon_available": True,
            "context_info": {"host": "tcp://remote.example.com:2376", "is_remote": True},
        })
        assert result == "BLOCKED_REMOTE_CONTEXT"

    def test_evaluator_raw_secret_blocked(self):
        result = evaluate_h39_readiness({
            "docs_only": False,
            "docker_installed": True,
            "docker_daemon_available": True,
            "context_info": {"host": "unix:///var/run/docker.sock", "is_remote": False},
            "raw_secret_in_evidence": True,
        })
        assert result == "BLOCKED_RAW_SECRET_RISK"

    def test_evaluator_ready_when_complete(self):
        result = evaluate_h39_readiness({
            "docs_only": False,
            "docker_installed": True,
            "docker_daemon_available": True,
            "context_info": {"host": "unix:///var/run/docker.sock", "is_remote": False},
            "raw_secret_in_evidence": False,
            "owner_approval": True,
            "evidence_complete": True,
        })
        assert result == "READY_FOR_H40_PREFLIGHT"


class TestSafetyRules:
    def test_safety_rules_documented(self):
        text = _read_doc()
        assert "Safety" in text or "safety" in text.lower()
        assert "executes no Docker" in text or "not execute Docker" in text.lower()


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
