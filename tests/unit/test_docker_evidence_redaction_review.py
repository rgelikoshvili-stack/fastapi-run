"""
Tests for docs/docker-evidence-redaction-review.md (H42).

H42 reviews H41 Docker evidence for secrets, production indicators,
and customer data. H41 decision was BLOCKED_DOCKER_UNAVAILABLE (Docker not installed).
H42 decision: EVIDENCE_SANITIZED — CommandNotFoundException output is clean.
No container, DB, SQL, migration, fixture, runtime API, Cloud Run mutation, or feature flag.
"""

import re
import os
import pytest

DOC_PATH = "docs/docker-evidence-redaction-review.md"

REQUIRED_REDACTION_RULES = [
    "R1", "R2", "R3", "R4", "R5", "R6",
    "R7", "R8", "R9", "R10", "R11", "R12",
]

DECISION_OUTPUTS = {
    "EVIDENCE_SANITIZED",
    "BLOCKED_SECRET_RISK",
    "BLOCKED_PRODUCTION_RISK",
    "BLOCKED_CUSTOMER_DATA_RISK",
    "BLOCKED_MISSING_H41_EVIDENCE",
}

REQUIRED_SANITIZED_PACKET_FIELDS = [
    "sanitization_id",
    "docker_evidence_id",
    "redaction_status",
    "secret_risk",
    "production_risk",
    "customer_data_risk",
    "safe_to_commit",
    "ready_for_h43",
]

REDACTION_STATUSES = {"clean", "clean_with_notes", "blocked_secret_risk",
                      "blocked_production_risk", "blocked_customer_data_risk",
                      "clean_with_notes", "blocked"}

# --- helpers ---

def _read_doc():
    with open(DOC_PATH, "r", encoding="utf-8") as f:
        return f.read()

def check_evidence_for_secrets(evidence_text: str) -> dict:
    """Scan evidence text for secret patterns. Returns findings."""
    findings = {
        "password_found": bool(re.search(r"(?i)password\s*[:=]\s*\S{4,}", evidence_text)),
        "api_key_found": bool(re.search(r"(?i)(api[_-]?key|apikey)\s*[:=]\s*\S{8,}", evidence_text)),
        "production_hostname": any(
            m in evidence_text for m in
            ["production", "cloudsql", "sql.goog", "run.app"]
        ),
        "raw_database_url": bool(re.search(r"postgresql://[^:]+:[^*\s]{4,}@", evidence_text)),
    }
    findings["secret_risk"] = any([
        findings["password_found"],
        findings["api_key_found"],
        findings["raw_database_url"],
    ])
    findings["production_risk"] = findings["production_hostname"]
    return findings

def evaluate_sanitization(packet: dict) -> str:
    """Evaluate an H42 sanitization packet and return decision."""
    if not packet.get("h41_evidence_available"):
        return "BLOCKED_MISSING_H41_EVIDENCE"
    if packet.get("secret_risk"):
        return "BLOCKED_SECRET_RISK"
    if packet.get("production_risk"):
        return "BLOCKED_PRODUCTION_RISK"
    if packet.get("customer_data_risk"):
        return "BLOCKED_CUSTOMER_DATA_RISK"
    return "EVIDENCE_SANITIZED"

def validate_sanitized_packet(packet: dict) -> list:
    """Validate an H42 sanitized evidence packet. Returns errors."""
    errors = []
    for field in REQUIRED_SANITIZED_PACKET_FIELDS:
        if field not in packet:
            errors.append(f"missing field: {field}")
    status = packet.get("redaction_status", "")
    if status not in REDACTION_STATUSES:
        errors.append(f"invalid redaction_status: {status!r}")
    return errors

# --- tests ---

class TestDocumentExists:
    def test_h42_doc_exists(self):
        assert os.path.exists(DOC_PATH), f"Expected {DOC_PATH} to exist"


class TestH42Purpose:
    def test_h42_purpose_documented(self):
        text = _read_doc()
        assert "Sanitization" in text or "Redaction" in text or "sanitization" in text.lower()

    def test_h42_no_docker_execution(self):
        text = _read_doc()
        assert "does not execute Docker" in text.lower() or "H42 does not execute Docker" in text or "not execute Docker" in text.lower()


class TestH41Dependency:
    def test_h41_dependency_documented(self):
        text = _read_doc()
        assert "H41" in text
        assert "DOCKER-EV-2026-H41-001" in text or "docker_evidence_id" in text


class TestRedactionChecklist:
    def test_redaction_checklist_r1_to_r12_documented(self):
        text = _read_doc()
        for rule in REQUIRED_REDACTION_RULES:
            assert rule in text, f"Redaction rule {rule} not found in doc"

    def test_r1_no_passwords(self):
        text = _read_doc()
        assert "R1" in text
        assert "password" in text.lower()

    def test_r3_no_api_keys(self):
        text = _read_doc()
        assert "R3" in text
        assert "API key" in text or "api key" in text.lower()

    def test_r5_no_production_hostnames(self):
        text = _read_doc()
        assert "R5" in text
        assert "production" in text.lower()


class TestSanitizationResult:
    def test_sanitization_result_documented(self):
        text = _read_doc()
        assert "Sanitization Result" in text or "redaction_status" in text

    def test_clean_result_documented(self):
        text = _read_doc()
        assert "clean" in text.lower()

    def test_redaction_blocks_password(self):
        findings = check_evidence_for_secrets("password=mysecretpassword123")
        assert findings["password_found"] is True
        assert findings["secret_risk"] is True

    def test_redaction_blocks_api_key(self):
        findings = check_evidence_for_secrets("api_key=sk-abcdefghijklmnop")
        assert findings["api_key_found"] is True
        assert findings["secret_risk"] is True

    def test_redaction_blocks_production_hostname(self):
        findings = check_evidence_for_secrets("host=production.cloudsql.example.com")
        assert findings["production_risk"] is True

    def test_redaction_accepts_clean_local_evidence(self):
        findings = check_evidence_for_secrets(
            "docker: The term 'docker' is not recognized as the name of a cmdlet"
        )
        assert findings["secret_risk"] is False
        assert findings["production_risk"] is False
        assert findings["raw_database_url"] is False


class TestSanitizedEvidencePacket:
    def test_sanitized_evidence_packet_documented(self):
        text = _read_doc()
        assert "sanitization_id" in text
        assert "ready_for_h43" in text

    def _make_packet(self):
        return {
            "sanitization_id": "SANITIZATION-2026-H42-001",
            "docker_evidence_id": "DOCKER-EV-2026-H41-001",
            "redaction_status": "clean",
            "secret_risk": False,
            "production_risk": False,
            "customer_data_risk": False,
            "safe_to_commit": True,
            "ready_for_h43": True,
        }

    def test_valid_packet_passes(self):
        errors = validate_sanitized_packet(self._make_packet())
        assert errors == []

    def test_missing_field_detected(self):
        packet = self._make_packet()
        del packet["safe_to_commit"]
        errors = validate_sanitized_packet(packet)
        assert any("safe_to_commit" in e for e in errors)


class TestH42DecisionOutputs:
    def test_h42_decision_outputs_documented(self):
        text = _read_doc()
        for output in DECISION_OUTPUTS:
            assert output in text, f"Decision output {output} not found in doc"

    def test_evaluator_missing_h41(self):
        result = evaluate_sanitization({"h41_evidence_available": False})
        assert result == "BLOCKED_MISSING_H41_EVIDENCE"

    def test_evaluator_secret_risk(self):
        result = evaluate_sanitization({
            "h41_evidence_available": True,
            "secret_risk": True,
        })
        assert result == "BLOCKED_SECRET_RISK"

    def test_evaluator_production_risk(self):
        result = evaluate_sanitization({
            "h41_evidence_available": True,
            "secret_risk": False,
            "production_risk": True,
        })
        assert result == "BLOCKED_PRODUCTION_RISK"

    def test_evaluator_clean(self):
        result = evaluate_sanitization({
            "h41_evidence_available": True,
            "secret_risk": False,
            "production_risk": False,
            "customer_data_risk": False,
        })
        assert result == "EVIDENCE_SANITIZED"


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
