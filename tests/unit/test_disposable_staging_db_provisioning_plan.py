"""
H36 — Disposable/Staging DB Provisioning Plan.
Pure local contract tests. No DB. No network. No SQL. No subprocess. No Docker.
"""

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DOCS_DIR = Path(__file__).parent.parent.parent / "docs"
_H36_DOC = _DOCS_DIR / "disposable-staging-db-provisioning-plan.md"
_H35_DOC = _DOCS_DIR / "runtime-comparison-dry-run-blocker-resolution-plan.md"


def _h36_text() -> str:
    return _H36_DOC.read_text(encoding="utf-8")


def _h35_text() -> str:
    return _H35_DOC.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Local contract helpers — pure functions, no DB, no network
# ---------------------------------------------------------------------------

PRODUCTION_URL_MARKERS = [
    "production",
    "prod-",
    "-prod",
    "cloudsql",
    "rgelikoshvili",
    "europe-west1.run.app",
    "sql.goog",
]

ALLOWED_DB_OPTIONS = {
    "docker_disposable",
    "local_disposable",
    "staging",
    "sandbox_tenant",
}

FORBIDDEN_DB_OPTIONS = {
    "production",
    "cloud_run_production",
    "unknown",
    "customer",
}

REQUIRED_PACKET_FIELDS = [
    "provisioning_id",
    "environment",
    "db_option",
    "db_classification",
    "db_name",
    "host_classification",
    "owner_approval_id",
    "cleanup_policy",
    "retention_policy",
    "redacted_connection_proof",
    "allowed_operations",
    "forbidden_operations",
    "ready_for_h37",
    "created_at",
    "created_by",
]

VALID_CLEANUP_POLICIES = {"drop_after", "preserve_staging", "container_remove"}

DECISION_OUTPUTS = {
    "READY_FOR_H37_DRY_RUN",
    "BLOCKED_NO_PROVISIONING_OPTION",
    "BLOCKED_NO_OWNER_APPROVAL",
    "BLOCKED_PRODUCTION_RISK",
    "BLOCKED_NO_CLEANUP_POLICY",
    "BLOCKED_RAW_SECRET_RISK",
    "BLOCKED_NO_REDACTED_CONNECTION_PROOF",
}

OPTION_RANK = {
    "docker_disposable": 1,
    "local_disposable": 2,
    "staging": 3,
    "sandbox_tenant": 4,
}

REQUIRED_DB_MARKERS = {"bridgehub_disposable", "bridgehub_staging", "disposable", "staging", "nonprod"}


def classify_provisioning_option(db_url: str, option: str) -> dict:
    """Classify a provisioning option as allowed or forbidden."""
    if option in FORBIDDEN_DB_OPTIONS:
        return {"allowed": False, "option": option, "reason": "forbidden_option"}
    if not db_url or db_url.strip() == "":
        return {"allowed": False, "option": option, "reason": "empty_url"}
    url_lower = db_url.lower()
    for marker in PRODUCTION_URL_MARKERS:
        if marker in url_lower:
            return {
                "allowed": False,
                "option": option,
                "reason": f"production_marker:{marker}",
                "class": "production",
            }
    if option not in ALLOWED_DB_OPTIONS:
        return {"allowed": False, "option": option, "reason": "unknown_option"}
    return {"allowed": True, "option": option, "class": option}


def evaluate_provisioning_readiness(plan: dict) -> dict:
    """Evaluate a provisioning plan and return decision output."""
    blockers = []

    db_url = plan.get("db_url", "")
    option = plan.get("db_option", "")
    result = classify_provisioning_option(db_url, option)
    if not result["allowed"]:
        reason = result.get("reason", "forbidden")
        if "production" in reason:
            blockers.append("BLOCKED_PRODUCTION_RISK")
        elif "empty" in reason or not option:
            blockers.append("BLOCKED_NO_PROVISIONING_OPTION")
        else:
            blockers.append("BLOCKED_NO_PROVISIONING_OPTION")

    if not plan.get("owner_approval_id"):
        blockers.append("BLOCKED_NO_OWNER_APPROVAL")

    if plan.get("cleanup_policy") not in VALID_CLEANUP_POLICIES:
        blockers.append("BLOCKED_NO_CLEANUP_POLICY")

    # Redacted connection proof check
    conn_proof = plan.get("redacted_connection_proof", "")
    if not conn_proof or "***" not in conn_proof:
        blockers.append("BLOCKED_NO_REDACTED_CONNECTION_PROOF")

    # Raw secret check
    if plan.get("raw_secret_detected", False):
        blockers.append("BLOCKED_RAW_SECRET_RISK")

    if not blockers:
        return {"decision": "READY_FOR_H37_DRY_RUN", "blockers": [], "ready_for_h37": True}

    primary = blockers[0]
    return {"decision": primary, "blockers": blockers, "ready_for_h37": False}


def validate_redacted_connection(conn_str: str) -> dict:
    """Validate that a connection string is properly redacted."""
    if not conn_str:
        return {"valid": False, "reason": "empty"}
    if "***" not in conn_str:
        return {"valid": False, "reason": "password_not_redacted"}
    lower = conn_str.lower()
    for marker in PRODUCTION_URL_MARKERS:
        if marker in lower:
            return {"valid": False, "reason": f"production_marker:{marker}"}
    return {"valid": True}


def validate_provisioning_packet(packet: dict) -> list[str]:
    """Validate a provisioning evidence packet and return list of errors."""
    errors = []
    for field in REQUIRED_PACKET_FIELDS:
        if field not in packet:
            errors.append(f"missing_field:{field}")
        elif packet[field] is None or packet[field] == "":
            errors.append(f"empty_field:{field}")
    if "cleanup_policy" in packet and packet.get("cleanup_policy") not in VALID_CLEANUP_POLICIES:
        errors.append(f"invalid_cleanup_policy:{packet.get('cleanup_policy')!r}")
    conn = packet.get("redacted_connection_proof", "")
    if conn and "***" not in conn:
        errors.append("redacted_connection_proof_not_masked")
    return errors


# ---------------------------------------------------------------------------
# Doc-coverage tests
# ---------------------------------------------------------------------------


def test_h36_doc_exists():
    assert _H36_DOC.exists(), f"H36 doc not found: {_H36_DOC}"


def test_h36_non_action_statement_present():
    text = _h36_text()
    for phrase in (
        "H36 does NOT create a DB",
        "H36 does NOT connect to a DB",
        "H36 does NOT execute SQL",
        "H36 does NOT run migrations",
        "H36 does NOT load fixtures into a DB",
        "H36 does NOT call runtime report APIs",
        "H36 does NOT enable `POSTED_LEDGER_REPORTS_ENABLED`",
        "H36 does NOT activate Balance.ge",
        "H36 does NOT start dry-run execution",
    ):
        assert phrase in text, f"Non-action statement missing: {phrase!r}"


def test_h35_context_documented():
    text = _h36_text()
    for term in ("H35", "BLOCKED_NO_DB", "live verified", "no suitable disposable",
                 "POSTED_LEDGER_REPORTS_ENABLED", "remains OFF"):
        assert term.lower() in text.lower(), f"H35 context missing: {term!r}"


def test_provisioning_non_action_statement_documented():
    text = _h36_text()
    for stmt in ("H36 does NOT run Docker", "H36 does NOT run `createdb`",
                 "H36 does NOT run `psql`", "H36 does NOT connect to PostgreSQL",
                 "H36 does NOT set `DATABASE_URL`", "H36 does NOT start H37"):
        assert stmt in text, f"Provisioning non-action statement missing: {stmt!r}"


def test_recommended_provisioning_path_documented():
    text = _h36_text()
    for term in ("Docker PostgreSQL disposable container", "Local installed PostgreSQL",
                 "Dedicated staging PostgreSQL", "Sandbox tenant",
                 "Recommended", "Option A", "safest"):
        assert term.lower() in text.lower(), f"Recommended path missing: {term!r}"
    # Docker must be ranked first (rank 1)
    docker_pos = text.lower().find("docker postgresql disposable")
    local_pos = text.lower().find("local installed postgresql")
    assert docker_pos < local_pos, "Docker must appear before local installed PostgreSQL in ranking"


def test_acceptable_provisioning_options_documented():
    text = _h36_text()
    for opt in ("Option A", "Option B", "Option C", "Option D"):
        assert opt in text, f"Acceptable option missing: {opt!r}"
    for prop in ("cleanup policy", "owner approval", "required evidence",
                 "allowed scope", "limitations", "when to use"):
        assert prop.lower() in text.lower(), f"Option property missing: {prop!r}"


def test_forbidden_provisioning_options_documented():
    text = _h36_text()
    for fp in ("FP1", "FP2", "FP3", "FP4", "FP5", "FP6", "FP7", "FP8", "FP9", "FP10", "FP11"):
        assert fp in text, f"Forbidden option missing: {fp!r}"
    for term in ("production db", "unknown db", "customer db", "balance.ge live db",
                 "unclear retention", "owner approval"):
        assert term.lower() in text.lower(), f"Forbidden option term missing: {term!r}"


def test_db_naming_and_marker_rules_documented():
    text = _h36_text()
    for rule in ("NR1", "NR2", "NR3", "NR4", "NR5", "NR6", "NR7"):
        assert rule in text, f"Naming rule missing: {rule!r}"
    for term in ("bridgehub_disposable", "bridgehub_staging",
                 "no production hostnames", "no production secrets"):
        assert term.lower() in text.lower(), f"Naming rule term missing: {term!r}"


def test_redacted_connection_string_proof_documented():
    text = _h36_text()
    for rule in ("RP1", "RP2", "RP3", "RP4", "RP5", "RP6", "RP7", "RP8"):
        assert rule in text, f"Redaction rule missing: {rule!r}"
    assert "***" in text, "Redacted connection example must show ***"
    for term in ("password is always redacted", "raw credentials must never be committed",
                 "production-like hostnames are forbidden"):
        assert term.lower() in text.lower(), f"Redaction rule term missing: {term!r}"


def test_owner_approval_contract_documented():
    text = _h36_text()
    for approver in ("Engineering owner", "DB/provisioning owner",
                     "Accounting/product owner", "Rollback/cleanup owner"):
        assert approver.lower() in text.lower(), f"Approver missing: {approver!r}"
    for field in ("owner_id", "owner_role", "scope", "allowed_operations",
                  "cleanup_policy", "approval_timestamp", "approval_expires"):
        assert field in text, f"Approval field missing: {field!r}"
    assert "7 days" in text, "Approval expiry (7 days) must be documented"


def test_cleanup_retention_policy_documented():
    text = _h36_text()
    for term in ("drop_after", "container_remove", "preserve_staging",
                 "no secrets", "synthetic only", "production cleanup",
                 "not applicable"):
        assert term.lower() in text.lower(), f"Cleanup/retention term missing: {term!r}"


def test_future_provisioning_command_templates_documented():
    text = _h36_text()
    for term in ("NOT EXECUTED IN H36", "docker run", "docker stop",
                 "createdb", "dropdb", "pg_isready", "psql", "export DATABASE_URL"):
        assert term.lower() in text.lower(), f"Future command template missing: {term!r}"
    assert "[FUTURE" in text, "Future commands must be marked [FUTURE...]"


def test_provisioning_evidence_packet_documented():
    text = _h36_text()
    for field in REQUIRED_PACKET_FIELDS:
        assert field in text, f"Evidence packet field missing: {field!r}"
    for term in ("15 fields", "ready_for_h37", "NOT produced in H36"):
        assert term.lower() in text.lower(), f"Evidence packet section missing: {term!r}"


def test_h37_readiness_gate_documented():
    text = _h36_text()
    for gate in ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11"):
        assert gate in text, f"H37 gate missing: {gate!r}"
    for term in ("provisioning evidence packet", "db classification", "owner approval",
                 "cleanup policy", "fixture hash", "migration 011",
                 "no production data", "balance.ge", "feature flag plan",
                 "rollback reference", "dry-run execution packet"):
        assert term.lower() in text.lower(), f"H37 gate term missing: {term!r}"


def test_no_go_blockers_documented():
    text = _h36_text()
    for pnb in ("PNB1", "PNB2", "PNB3", "PNB4", "PNB5", "PNB6", "PNB7",
                "PNB8", "PNB9", "PNB10", "PNB11", "PNB12", "PNB13"):
        assert pnb in text, f"No-go blocker missing: {pnb!r}"
    for term in ("owner approval", "unknown db", "production db", "raw credentials",
                 "balance.ge", "cleanup policy", "redacted"):
        assert term.lower() in text.lower(), f"No-go blocker term missing: {term!r}"


def test_decision_outputs_documented():
    text = _h36_text()
    for decision in DECISION_OUTPUTS:
        assert decision in text, f"Decision output missing: {decision!r}"
    assert "Current H36 decision" in text
    assert "BLOCKED_NO_PROVISIONING_OPTION" in text


def test_provisioning_checklist_table_documented():
    text = _h36_text()
    for col in ("Requirement", "Evidence Required", "Owner", "Status",
                "Blocking if Missing", "Notes"):
        assert col in text, f"Checklist column missing: {col!r}"
    for row in ("Provisioning option selected", "DB classification",
                "Redacted connection proof", "Owner approval", "Cleanup policy",
                "Retention policy", "Fixture hash", "Migration review",
                "No production data proof", "Balance.ge demo proof",
                "Feature flag plan", "Rollback reference", "H37 packet"):
        assert row.lower() in text.lower(), f"Checklist row missing: {row!r}"


def test_safety_rules_documented():
    text = _h36_text()
    for rule in ("creates no DB", "runs no SQL", "runs no migration",
                 "loads no fixture", "runs no runtime API calls",
                 "enables no feature flags", "mutates no Cloud Run",
                 "activates no Balance.ge", "no infrastructure changes",
                 "no UI/static file changes", "does not run Docker"):
        assert rule.lower() in text.lower(), f"Safety rule missing: {rule!r}"


# ---------------------------------------------------------------------------
# Local logic tests
# ---------------------------------------------------------------------------


def test_local_option_rank_prefers_docker_disposable():
    assert OPTION_RANK["docker_disposable"] == 1, "Docker disposable must be rank 1"
    assert OPTION_RANK["docker_disposable"] < OPTION_RANK["local_disposable"]
    assert OPTION_RANK["local_disposable"] < OPTION_RANK["staging"]
    assert OPTION_RANK["staging"] < OPTION_RANK["sandbox_tenant"]


def test_local_option_accepts_local_disposable():
    result = classify_provisioning_option(
        "postgresql://bridgehub_nonprod_user:***@localhost:5432/bridgehub_disposable_h37",
        "local_disposable",
    )
    assert result["allowed"] is True
    assert result["class"] == "local_disposable"


def test_local_option_accepts_staging_with_marker():
    result = classify_provisioning_option(
        "postgresql://nonprod_role:***@staging-db.internal:5432/bridgehub_staging_h37",
        "staging",
    )
    assert result["allowed"] is True
    assert result["class"] == "staging"


def test_local_option_blocks_production():
    prod_urls = [
        ("postgresql://user:pw@production.db.example.com:5432/bridge", "docker_disposable"),
        ("postgresql://user:pw@prod-db:5432/bridge", "local_disposable"),
        ("postgresql://user:pw@sql.goog:5432/bridge", "staging"),
        ("postgresql://user:pw@rgelikoshvili-db:5432/bridge", "docker_disposable"),
        ("postgresql://user:pw@europe-west1.run.app:5432/bridge", "local_disposable"),
    ]
    for url, option in prod_urls:
        result = classify_provisioning_option(url, option)
        assert result["allowed"] is False, f"Production URL must be blocked: {url}"
        assert "production" in result.get("reason", "").lower() or \
               result.get("class") == "production"


def test_local_option_blocks_unknown():
    result = classify_provisioning_option(
        "postgresql://user:pw@mystery-host:5432/somedb",
        "unknown",
    )
    assert result["allowed"] is False


def test_local_readiness_blocks_without_redacted_connection_proof():
    plan = {
        "db_url": "postgresql://user:***@localhost:5432/bridgehub_disposable",
        "db_option": "local_disposable",
        "owner_approval_id": "eng-owner-001",
        "cleanup_policy": "drop_after",
        "redacted_connection_proof": "",  # missing
    }
    result = evaluate_provisioning_readiness(plan)
    assert result["ready_for_h37"] is False
    assert "BLOCKED_NO_REDACTED_CONNECTION_PROOF" in result["blockers"]


def test_local_readiness_blocks_without_cleanup_policy():
    plan = {
        "db_url": "postgresql://user:***@localhost:5432/bridgehub_disposable",
        "db_option": "local_disposable",
        "owner_approval_id": "eng-owner-001",
        "cleanup_policy": "undefined",
        "redacted_connection_proof": "postgresql://user:***@localhost:5432/bridgehub_disposable",
    }
    result = evaluate_provisioning_readiness(plan)
    assert result["ready_for_h37"] is False
    assert "BLOCKED_NO_CLEANUP_POLICY" in result["blockers"]


def test_local_readiness_blocks_without_owner_approval():
    plan = {
        "db_url": "postgresql://user:***@localhost:5432/bridgehub_disposable",
        "db_option": "local_disposable",
        "owner_approval_id": None,
        "cleanup_policy": "drop_after",
        "redacted_connection_proof": "postgresql://user:***@localhost:5432/bridgehub_disposable",
    }
    result = evaluate_provisioning_readiness(plan)
    assert result["ready_for_h37"] is False
    assert "BLOCKED_NO_OWNER_APPROVAL" in result["blockers"]


def test_local_redaction_rejects_raw_password():
    for raw in (
        "postgresql://user:realpassword@localhost:5432/bridgehub_disposable",
        "postgresql://user:abc123@127.0.0.1:5432/bridgehub_staging",
        "postgresql://admin:secret@staging-db:5432/bridge",
    ):
        result = validate_redacted_connection(raw)
        assert result["valid"] is False, f"Raw password must be rejected: {raw}"
        assert result["reason"] == "password_not_redacted"


def test_local_redaction_accepts_masked_password():
    for masked in (
        "postgresql://bridgehub_nonprod_user:***@localhost:5432/bridgehub_disposable_h37",
        "postgresql://nonprod_role:***@127.0.0.1:5432/bridgehub_staging_dryrun",
    ):
        result = validate_redacted_connection(masked)
        assert result["valid"] is True, f"Masked password must be accepted: {masked}"


# ---------------------------------------------------------------------------
# Security / hygiene tests
# ---------------------------------------------------------------------------


def test_no_real_pii_or_tax_or_bank_patterns():
    _b_og = "Bank of Georgia"
    text_h36 = _h36_text()
    text_test = Path(__file__).read_text(encoding="utf-8")
    pii_patterns = [
        r"\b010\d{8}\b",
        r"\bGE\d{2}[A-Z0-9]{20,}\b",
        r"\b\d{16}\b",
    ]
    for pattern in pii_patterns:
        for name, text in (("H36 doc", text_h36), ("H36 test", text_test)):
            matches = re.findall(pattern, text)
            assert not matches, f"{name}: real PII pattern {pattern!r} found: {matches}"
    assert _b_og not in text_h36, "H36 doc must not contain 'Bank of Georgia' as a literal string"


def test_no_db_or_network_imports_in_test_file():
    text = Path(__file__).read_text(encoding="utf-8")
    lines = text.splitlines()
    forbidden_import_patterns = [
        (r"^import asyncpg", "asyncpg import"),
        (r"^import sqlalchemy", "sqlalchemy import"),
        (r"^import requests\b", "requests import"),
        (r"^import httpx\b", "httpx import"),
        (r"^import socket\b", "socket import"),
        (r"^import psycopg", "psycopg import"),
        (r"^from psycopg", "from psycopg import"),
        (r"^from sqlalchemy", "from sqlalchemy import"),
        (r"^from requests", "from requests import"),
        (r"^from httpx", "from httpx import"),
    ]
    found = []
    for line in lines:
        for pattern, label in forbidden_import_patterns:
            if re.search(pattern, line):
                found.append(f"{label}: {line.strip()!r}")
    assert found == [], "Forbidden DB/network imports found:\n" + "\n".join(found)


def test_no_sql_or_subprocess_in_test_file():
    text = Path(__file__).read_text(encoding="utf-8")
    lines = text.splitlines()
    forbidden_patterns = [
        (r"^import subprocess\b", "subprocess import"),
        (r"^\s*subprocess\.run\b|^\s*subprocess\.call\b|^\s*subprocess\.Popen\b",
         "subprocess call"),
        (r"(?i)^\s*INSERT\s+INTO\b", "executable INSERT INTO"),
        (r"(?i)^\s*DELETE\s+FROM\b", "executable DELETE FROM"),
        (r"(?i)^\s*CREATE\s+TABLE\b", "executable CREATE TABLE"),
        (r"(?i)^\s*ALTER\s+TABLE\b", "executable ALTER TABLE"),
        (r"(?i)^\s*DROP\s+TABLE\b", "DROP TABLE"),
        (r"^\s*gcloud\s+run\s+services\s+update", "gcloud run update"),
        (r"^\s*kubectl\s+apply\b|^\s*kubectl\s+create\b", "kubectl apply/create"),
    ]
    found = []
    for line in lines:
        for pattern, label in forbidden_patterns:
            if re.search(pattern, line):
                found.append(f"{label}: {line.strip()!r}")
    assert found == [], "Forbidden SQL/subprocess patterns found:\n" + "\n".join(found)


def test_next_task_h37_documented():
    text = _h36_text()
    for term in ("H37", "Provisioning Evidence Completion",
                 "Local Docker PostgreSQL Setup Plan",
                 "Runtime Comparison Dry-Run Execution",
                 "H36 is live verified"):
        assert term in text, f"Next-task H37 reference missing: {term!r}"
