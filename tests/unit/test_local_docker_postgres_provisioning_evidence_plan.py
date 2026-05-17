"""
Tests for docs/local-docker-postgres-provisioning-evidence-plan.md (H37).

H37 is docs/tests only. No Docker is executed. No DB is created.
No SQL is run. No migration is run. No fixture is loaded into any DB.
No runtime API calls are made. No Cloud Run env vars are mutated.
No feature flags are enabled. No Balance.ge connector is activated.
DATABASE_URL stays empty during all local test runs.
"""

import re
import os
import pytest

DOC_PATH = "docs/local-docker-postgres-provisioning-evidence-plan.md"

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
    "DE1", "DE2", "DE3", "DE4", "DE5",
    "DE6", "DE7", "DE8", "DE9", "DE10",
    "DE11", "DE12", "DE13", "DE14", "DE15",
]

REQUIRED_NAMING_RULES = ["DNR1", "DNR2", "DNR3", "DNR4", "DNR5", "DNR6", "DNR7"]

REQUIRED_CONNECTION_RULES = ["RCP1", "RCP2", "RCP3", "RCP4", "RCP5", "RCP6", "RCP7"]

REQUIRED_NO_GO_BLOCKERS = ["HB1", "HB2", "HB3", "HB4", "HB5", "HB6", "HB7", "HB8", "HB9"]

DECISION_OUTPUTS = {
    "READY_FOR_H38_READINESS_GATE",
    "BLOCKED_DOCKER_NOT_EXECUTED",
    "BLOCKED_DOCKER_UNAVAILABLE",
    "BLOCKED_NO_OWNER_APPROVAL",
    "BLOCKED_RAW_SECRET_RISK",
    "BLOCKED_NO_CLEANUP_POLICY",
    "BLOCKED_PRODUCTION_RISK",
}

REQUIRED_EVIDENCE_PACKET_FIELDS = [
    "evidence_id",
    "db_option",
    "container_name",
    "db_name",
    "host",
    "port",
    "redacted_connection_proof",
    "owner_approval_id",
    "cleanup_policy",
    "retention_policy",
    "fixture_version",
    "migration_version",
    "no_production_data_proof",
    "ready_for_h38",
]

FORBIDDEN_EXECUTABLE_COMMANDS = [
    r"^\s*docker\s+run\b",
    r"^\s*docker\s+exec\b",
    r"^\s*docker\s+start\b",
    r"^\s*createdb\b",
    r"^\s*dropdb\b",
    r"^\s*psql\b",
    r"^\s*pg_isready\b",
]

# --- helpers ---

def _read_doc():
    with open(DOC_PATH, "r", encoding="utf-8") as f:
        return f.read()

def classify_connection_url(url: str) -> dict:
    """Classify a PostgreSQL connection URL for local-only safety."""
    is_local = any(h in url for h in ["localhost", "127.0.0.1"])
    has_production_marker = any(m in url for m in PRODUCTION_URL_MARKERS)
    has_raw_password = bool(re.search(r"://[^:]+:[^*@][^@]*@", url))
    has_disposable_marker = "disposable" in url or "nonprod" in url
    return {
        "is_local": is_local,
        "has_production_marker": has_production_marker,
        "has_raw_password": has_raw_password,
        "has_disposable_marker": has_disposable_marker,
        "safe": is_local and not has_production_marker and not has_raw_password,
    }

def validate_evidence_packet(packet: dict) -> list:
    """Validate an H37 evidence packet. Returns list of missing/invalid fields."""
    errors = []
    for field in REQUIRED_EVIDENCE_PACKET_FIELDS:
        if field not in packet:
            errors.append(f"missing field: {field}")
    if packet.get("host") not in ("localhost", "127.0.0.1"):
        errors.append("host must be localhost or 127.0.0.1")
    if packet.get("ready_for_h38") is not False:
        errors.append("ready_for_h38 must be false until all evidence confirmed")
    conn = packet.get("redacted_connection_proof", "")
    if "***" not in conn:
        errors.append("redacted_connection_proof must use *** for password")
    if not any(m in conn for m in ["disposable", "nonprod"]):
        errors.append("redacted_connection_proof must include disposable/nonprod marker")
    return errors

def evaluate_h37_readiness(evidence: dict) -> str:
    """Evaluate H37 provisioning evidence and return decision output."""
    if evidence.get("docker_executed"):
        return "BLOCKED_DOCKER_NOT_EXECUTED"
    if not evidence.get("docker_available"):
        return "BLOCKED_DOCKER_UNAVAILABLE"
    if not evidence.get("owner_approval"):
        return "BLOCKED_NO_OWNER_APPROVAL"
    url = evidence.get("database_url", "")
    if any(m in url for m in PRODUCTION_URL_MARKERS):
        return "BLOCKED_PRODUCTION_RISK"
    if re.search(r"://[^:]+:[^*@][^@]*@", url):
        return "BLOCKED_RAW_SECRET_RISK"
    if not evidence.get("cleanup_policy"):
        return "BLOCKED_NO_CLEANUP_POLICY"
    if evidence.get("all_evidence_confirmed"):
        return "READY_FOR_H38_READINESS_GATE"
    return "BLOCKED_DOCKER_NOT_EXECUTED"

# --- tests ---

class TestDocumentExists:
    def test_doc_file_exists(self):
        assert os.path.exists(DOC_PATH), f"Expected {DOC_PATH} to exist"

    def test_doc_is_not_empty(self):
        text = _read_doc()
        assert len(text) > 500

    def test_doc_title_present(self):
        text = _read_doc()
        assert "H37" in text
        assert "Provisioning Evidence" in text or "provisioning-evidence" in DOC_PATH


class TestH37NonActionStatement:
    def test_h37_is_docs_tests_only(self):
        text = _read_doc()
        assert "docs/tests only" in text.lower() or "H37 is docs" in text

    def test_h37_does_not_execute_docker(self):
        text = _read_doc()
        assert "does NOT execute Docker" in text or "NOT execute Docker" in text

    def test_h37_does_not_create_db(self):
        text = _read_doc()
        assert "does NOT create a DB" in text or "NOT create a DB" in text

    def test_h37_does_not_run_migrations(self):
        text = _read_doc()
        assert "does NOT run migrations" in text or "NOT run migrations" in text

    def test_posted_ledger_flag_remains_off(self):
        text = _read_doc()
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text
        assert "remains OFF" in text or "remain OFF" in text


class TestEvidenceItems:
    def test_all_evidence_items_documented(self):
        text = _read_doc()
        for item in REQUIRED_EVIDENCE_ITEMS:
            assert item in text, f"Evidence item {item} not found in doc"

    def test_de1_docker_availability(self):
        text = _read_doc()
        assert "DE1" in text
        assert "docker version" in text.lower() or "Docker availability" in text

    def test_de8_redacted_connection_proof(self):
        text = _read_doc()
        assert "DE8" in text
        assert "***" in text

    def test_de9_owner_approval(self):
        text = _read_doc()
        assert "DE9" in text
        assert "owner" in text.lower() or "approval" in text.lower()

    def test_de14_rollback_reference_present(self):
        text = _read_doc()
        assert "DE14" in text
        assert "rollback" in text.lower()


class TestNamingRules:
    def test_all_naming_rules_documented(self):
        text = _read_doc()
        for rule in REQUIRED_NAMING_RULES:
            assert rule in text, f"Naming rule {rule} not found in doc"

    def test_container_name_requires_disposable_marker(self):
        text = _read_doc()
        assert "bridgehub_disposable" in text

    def test_username_requires_nonprod_marker(self):
        text = _read_doc()
        assert "nonprod" in text.lower()

    def test_password_never_committed(self):
        text = _read_doc()
        assert "never committed" in text.lower() or "not committed" in text.lower()


class TestRedactedConnectionProof:
    def test_redacted_connection_rules_documented(self):
        text = _read_doc()
        for rule in REQUIRED_CONNECTION_RULES:
            assert rule in text, f"Connection rule {rule} not found in doc"

    def test_example_uses_starred_password(self):
        text = _read_doc()
        assert "***" in text

    def test_example_uses_localhost(self):
        text = _read_doc()
        assert "localhost" in text

    def test_forbidden_raw_password_example_shown(self):
        text = _read_doc()
        assert "Forbidden" in text or "forbidden" in text

    def test_classify_safe_url(self):
        result = classify_connection_url(
            "postgresql://bridgehub_nonprod_user:***@localhost:5432/bridgehub_disposable_h37"
        )
        assert result["is_local"] is True
        assert result["has_production_marker"] is False
        assert result["has_raw_password"] is False
        assert result["safe"] is True

    def test_classify_raw_password_url_flagged(self):
        result = classify_connection_url(
            "postgresql://user:realpassword@localhost:5432/bridgehub_disposable_h37"
        )
        assert result["has_raw_password"] is True
        assert result["safe"] is False

    def test_classify_production_url_blocked(self):
        result = classify_connection_url(
            "postgresql://user:***@production.db.example.com:5432/bridge"
        )
        assert result["has_production_marker"] is True
        assert result["safe"] is False


class TestEvidencePacketValidation:
    def _make_packet(self):
        return {
            "evidence_id": "DOCKER-PROV-2026-001",
            "db_option": "local_docker_postgres",
            "container_name": "bridgehub_disposable_h37",
            "db_name": "bridgehub_disposable_h37",
            "host": "localhost",
            "port": 5432,
            "redacted_connection_proof": "postgresql://bridgehub_nonprod_user:***@localhost:5432/bridgehub_disposable_h37",
            "owner_approval_id": "pending",
            "cleanup_policy": "container_remove",
            "retention_policy": "artifacts retained; no secrets; synthetic data only",
            "fixture_version": "sha256:abc123",
            "migration_version": "011_sha256:def456",
            "no_production_data_proof": "synthetic fixture only",
            "ready_for_h38": False,
        }

    def test_complete_packet_valid(self):
        errors = validate_evidence_packet(self._make_packet())
        assert errors == []

    def test_packet_missing_field_detected(self):
        packet = self._make_packet()
        del packet["cleanup_policy"]
        errors = validate_evidence_packet(packet)
        assert any("cleanup_policy" in e for e in errors)

    def test_ready_for_h38_must_be_false(self):
        packet = self._make_packet()
        packet["ready_for_h38"] = True
        errors = validate_evidence_packet(packet)
        assert any("ready_for_h38" in e for e in errors)

    def test_remote_host_rejected(self):
        packet = self._make_packet()
        packet["host"] = "production.cloudsql.example.com"
        errors = validate_evidence_packet(packet)
        assert any("host" in e for e in errors)

    def test_raw_password_in_conn_rejected(self):
        packet = self._make_packet()
        packet["redacted_connection_proof"] = (
            "postgresql://user:realpassword@localhost:5432/bridgehub_disposable_h37"
        )
        errors = validate_evidence_packet(packet)
        assert any("***" in e or "password" in e for e in errors)


class TestNoGoBlockers:
    def test_all_no_go_blockers_documented(self):
        text = _read_doc()
        for blocker in REQUIRED_NO_GO_BLOCKERS:
            assert blocker in text, f"No-go blocker {blocker} not found in doc"

    def test_hb1_docker_unavailable(self):
        text = _read_doc()
        assert "HB1" in text
        assert "Docker" in text

    def test_hb2_raw_secret_critical(self):
        text = _read_doc()
        assert "HB2" in text
        assert "secret" in text.lower() or "CRITICAL" in text


class TestDecisionOutputs:
    def test_all_decision_outputs_documented(self):
        text = _read_doc()
        for output in DECISION_OUTPUTS:
            assert output in text, f"Decision output {output} not found in doc"

    def test_current_decision_is_blocked(self):
        text = _read_doc()
        assert "BLOCKED_DOCKER_NOT_EXECUTED" in text
        assert "Current" in text or "current" in text

    def test_readiness_evaluator_blocked_no_docker(self):
        result = evaluate_h37_readiness({"docker_available": False, "docker_executed": False})
        assert result == "BLOCKED_DOCKER_UNAVAILABLE"

    def test_readiness_evaluator_blocked_no_approval(self):
        result = evaluate_h37_readiness({"docker_available": True, "owner_approval": False, "docker_executed": False})
        assert result == "BLOCKED_NO_OWNER_APPROVAL"

    def test_readiness_evaluator_production_risk_blocked(self):
        result = evaluate_h37_readiness({
            "docker_available": True,
            "owner_approval": True,
            "database_url": "postgresql://user:***@production.cloudsql.example.com:5432/bridge",
            "docker_executed": False,
        })
        assert result == "BLOCKED_PRODUCTION_RISK"


class TestNoForbiddenExecutionInDoc:
    def test_no_docker_run_outside_future_block(self):
        """docker run must only appear inside [FUTURE] labeled sections."""
        with open(DOC_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        in_future_block = False
        for line in lines:
            if "[FUTURE]" in line or "NOT EXECUTED" in line:
                in_future_block = True
            if in_future_block and line.strip() == "```":
                in_future_block = False
            if not in_future_block:
                assert not re.match(r"^\s*docker\s+run\b", line), (
                    f"docker run found outside [FUTURE] block: {line.rstrip()}"
                )

    def test_no_real_password_in_doc(self):
        """Prose text must not contain raw passwords; code blocks may have labeled forbidden examples."""
        with open(DOC_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        in_code_block = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                continue
            assert not re.search(r"postgresql://[^:]+:[^*\s]{4,}@", line), (
                f"Possible real password in prose: {line.rstrip()}"
            )
