"""
H35 — Runtime Comparison Dry-Run Blocker Resolution Plan.
Pure local contract tests. No DB. No network. No SQL. No subprocess.
"""

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DOCS_DIR = Path(__file__).parent.parent.parent / "docs"
_H35_DOC = _DOCS_DIR / "runtime-comparison-dry-run-blocker-resolution-plan.md"
_H34_DOC = _DOCS_DIR / "disposable-staging-runtime-comparison-execution-plan.md"


def _h35_text() -> str:
    return _H35_DOC.read_text(encoding="utf-8")


def _h34_text() -> str:
    return _H34_DOC.read_text(encoding="utf-8")


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

ALLOWED_DB_CLASSES = {
    "disposable_local_db",
    "docker_db",
    "staging_db",
    "sandbox_db",
}

FORBIDDEN_DB_CLASSES = {
    "production_db",
    "cloud_run_production_db",
    "unknown_db",
}

ALLOWED_ENVIRONMENTS = {
    "disposable_local",
    "docker_container",
    "staging",
    "sandbox_tenant",
}

FORBIDDEN_ENVIRONMENTS = {
    "production",
    "cloud_run_production",
    "unknown",
}

DECISION_OUTPUTS = {
    "READY_FOR_DRY_RUN_EXECUTION",
    "BLOCKED_NO_DB",
    "BLOCKED_UNKNOWN_DB",
    "BLOCKED_PRODUCTION_RISK",
    "BLOCKED_NO_OWNER_APPROVAL",
    "BLOCKED_NO_CLEANUP_PLAN",
    "BLOCKED_NO_FIXTURE_HASH",
    "BLOCKED_NO_MIGRATION_REVIEW",
}

REQUIRED_PACKET_FIELDS = [
    "execution_request_id",
    "requested_by",
    "environment",
    "db_classification",
    "db_proof_reference",
    "fixture_version",
    "migration_version",
    "owner_approval",
    "cleanup_plan",
    "feature_flag_plan",
    "rollback_reference",
    "no_go_blockers_checked",
    "go_decision",
    "created_at",
]

VALID_CLEANUP_PLANS = {"drop_after", "preserve_staging", "container_remove"}
VALID_GO_DECISIONS = {"go", "no_go"}


def classify_db_url(db_url: str) -> dict:
    """Classify a DB URL as allowed or forbidden."""
    if not db_url or db_url.strip() == "":
        return {"allowed": False, "class": "unknown_db", "reason": "empty_url"}
    url_lower = db_url.lower()
    for marker in PRODUCTION_URL_MARKERS:
        if marker in url_lower:
            return {
                "allowed": False,
                "class": "production_db",
                "reason": f"production_marker:{marker}",
            }
    if any(h in url_lower for h in ("localhost", "127.0.0.1", "0.0.0.0")):
        if "docker" in url_lower or "container" in url_lower:
            return {"allowed": True, "class": "docker_db"}
        return {"allowed": True, "class": "disposable_local_db"}
    if "staging" in url_lower or "sandbox" in url_lower:
        return {"allowed": True, "class": "staging_db"}
    if "dev" in url_lower or "test" in url_lower or "disposable" in url_lower:
        return {"allowed": True, "class": "disposable_local_db"}
    return {"allowed": False, "class": "unknown_db", "reason": "cannot_classify"}


def evaluate_readiness(plan: dict) -> dict:
    """Evaluate a readiness plan dict and return blockers + decision output."""
    blockers = []

    # DB classification
    db_url = plan.get("db_url", "")
    db_result = classify_db_url(db_url)
    if not db_result["allowed"]:
        reason = db_result.get("reason", "forbidden")
        if "production" in reason:
            blockers.append("BLOCKED_PRODUCTION_RISK")
        elif "empty" in reason or "cannot" in reason:
            blockers.append("BLOCKED_NO_DB")
        else:
            blockers.append("BLOCKED_UNKNOWN_DB")

    # Owner approval
    if not plan.get("owner_approval"):
        blockers.append("BLOCKED_NO_OWNER_APPROVAL")

    # Cleanup plan
    if plan.get("cleanup_plan") not in VALID_CLEANUP_PLANS:
        blockers.append("BLOCKED_NO_CLEANUP_PLAN")

    # Fixture hash
    if not plan.get("fixture_hash"):
        blockers.append("BLOCKED_NO_FIXTURE_HASH")

    # Migration review
    if not plan.get("migration_reviewed"):
        blockers.append("BLOCKED_NO_MIGRATION_REVIEW")

    # Balance.ge
    balance_state = plan.get("balance_connector_state")
    if balance_state not in (None, "demo_mode", "unconfigured"):
        blockers.append("balance_live_connector")

    # Production flag
    if plan.get("production_flag_on", False):
        blockers.append("production_flag_on_forbidden")

    # Production data
    if plan.get("production_data_detected", False):
        blockers.append("production_data_detected")

    if not blockers:
        return {
            "decision": "READY_FOR_DRY_RUN_EXECUTION",
            "blockers": [],
            "go_decision": "go",
        }

    primary = blockers[0] if blockers else "BLOCKED_UNKNOWN_DB"
    if "BLOCKED_" in primary:
        decision = primary
    else:
        decision = "BLOCKED_UNKNOWN_DB"

    return {
        "decision": decision,
        "blockers": blockers,
        "go_decision": "no_go",
    }


def validate_execution_packet(packet: dict) -> list[str]:
    """Validate a dry-run execution packet and return list of errors."""
    errors = []
    for field in REQUIRED_PACKET_FIELDS:
        if field not in packet:
            errors.append(f"missing_field:{field}")
        elif packet[field] is None or packet[field] == "":
            errors.append(f"empty_field:{field}")
    if "cleanup_plan" in packet and packet.get("cleanup_plan") not in VALID_CLEANUP_PLANS:
        errors.append(f"invalid_cleanup_plan:{packet.get('cleanup_plan')!r}")
    if "go_decision" in packet and packet.get("go_decision") not in VALID_GO_DECISIONS:
        errors.append(f"invalid_go_decision:{packet.get('go_decision')!r}")
    if packet.get("no_go_blockers_checked") is not True:
        errors.append("no_go_blockers_checked_must_be_true")
    return errors


# ---------------------------------------------------------------------------
# Doc-coverage tests
# ---------------------------------------------------------------------------


def test_h35_doc_exists():
    assert _H35_DOC.exists(), f"H35 doc not found: {_H35_DOC}"


def test_h35_non_action_statement_present():
    text = _h35_text()
    for phrase in (
        "H35 does NOT create a DB",
        "H35 does NOT connect to a DB",
        "H35 does NOT execute SQL",
        "H35 does NOT run migrations",
        "H35 does NOT load fixtures into a DB",
        "H35 does NOT call runtime report APIs",
        "H35 does NOT enable `POSTED_LEDGER_REPORTS_ENABLED`",
        "H35 does NOT activate Balance.ge",
    ):
        assert phrase in text, f"Non-action statement missing: {phrase!r}"


def test_h34_context_documented():
    text = _h35_text()
    for term in ("H34", "execution plan", "did not execute", "suitable disposable/staging DB",
                 "POSTED_LEDGER_REPORTS_ENABLED", "remains OFF"):
        assert term.lower() in text.lower(), f"H34 context missing: {term!r}"


def test_current_blocker_statement_documented():
    text = _h35_text()
    for blocker_id in ("CB1", "CB2", "CB3", "CB4", "CB5", "CB6", "CB7", "CB8", "CB9", "CB10"):
        assert blocker_id in text, f"Blocker ID missing: {blocker_id!r}"
    for term in ("no confirmed", "no dry-run", "no explicit go"):
        assert term.lower() in text.lower(), f"Blocker statement missing: {term!r}"


def test_acceptable_db_options_documented():
    text = _h35_text()
    for opt in ("Disposable Local PostgreSQL", "Docker PostgreSQL", "Staging PostgreSQL",
                "Sandbox Tenant"):
        assert opt.lower() in text.lower(), f"Acceptable DB option missing: {opt!r}"
    for prop in ("cleanup policy", "owner approval", "allowed migration scope",
                 "allowed fixture scope", "non-production marker"):
        assert prop.lower() in text.lower(), f"DB option property missing: {prop!r}"


def test_forbidden_db_options_documented():
    text = _h35_text()
    for fdb in ("FDB1", "FDB2", "FDB3", "FDB4", "FDB5", "FDB6", "FDB7", "FDB8", "FDB9"):
        assert fdb in text, f"Forbidden DB option missing: {fdb!r}"
    for term in ("production db", "unknown db", "customer db", "cleanup policy is unclear"):
        assert term.lower() in text.lower(), f"Forbidden DB term missing: {term!r}"


def test_required_evidence_to_unblock_documented():
    text = _h35_text()
    for ev in ("EV1", "EV2", "EV3", "EV4", "EV5", "EV6", "EV7", "EV8",
               "EV9", "EV10", "EV11", "EV12", "EV13"):
        assert ev in text, f"Evidence item missing: {ev!r}"
    for term in ("environment classification proof", "db classification proof",
                 "owner approval", "cleanup plan", "fixture hash", "migration file",
                 "rollback", "no production data proof", "feature flag state proof",
                 "execution command"):
        assert term.lower() in text.lower(), f"Evidence term missing: {term!r}"


def test_db_classification_checklist_documented():
    text = _h35_text()
    for dc in ("DC1", "DC2", "DC3", "DC4", "DC5", "DC6", "DC7", "DC8", "DC9"):
        assert dc in text, f"DB checklist item missing: {dc!r}"
    for term in ("host is local or staging", "no production hostname",
                 "no customer data", "cleanup strategy", "owner approval"):
        assert term.lower() in text.lower(), f"DB checklist term missing: {term!r}"


def test_future_execution_decision_tree_documented():
    text = _h35_text()
    for term in ("disposable local", "docker", "staging", "production", "blocked",
                 "READY_FOR_DRY_RUN_EXECUTION", "NOT EXECUTED IN H35"):
        assert term.lower() in text.lower(), f"Decision tree missing: {term!r}"


def test_future_dry_run_execution_packet_documented():
    text = _h35_text()
    for field in REQUIRED_PACKET_FIELDS:
        assert field in text, f"Packet field missing: {field!r}"
    for term in ("go | no_go", "NOT assembled in H35", "14 fields"):
        assert term.lower() in text.lower(), f"Packet section missing: {term!r}"


def test_future_only_commands_documented():
    text = _h35_text()
    for category in ("Create disposable DB", "Run migration 011", "Inspect schema",
                     "Load fixture", "Run report capture", "Run comparison",
                     "Generate accountant review", "Cleanup"):
        assert category.lower() in text.lower(), f"Future command category missing: {category!r}"
    assert "NOT EXECUTED IN H35" in text, "Future commands must be marked NOT EXECUTED IN H35"


def test_no_go_blockers_documented():
    text = _h35_text()
    for ngb in ("NGB1", "NGB2", "NGB3", "NGB4", "NGB5", "NGB6", "NGB7",
                "NGB8", "NGB9", "NGB10", "NGB11", "NGB12", "NGB13", "NGB14"):
        assert ngb in text, f"No-go blocker missing: {ngb!r}"
    for term in ("production db indicator", "unknown db", "owner approval",
                 "cleanup plan", "fixture hash", "migration", "rollback",
                 "balance.ge", "production data", "feature flag", "auth bypass",
                 "accountant review", "evidence retention"):
        assert term.lower() in text.lower(), f"No-go term missing: {term!r}"


def test_readiness_checklist_table_documented():
    text = _h35_text()
    for col in ("Requirement", "Evidence Required", "Owner", "Status",
                "Blocking if Missing", "Notes"):
        assert col in text, f"Readiness checklist column missing: {col!r}"
    for row in ("environment proof", "DB proof", "Owner approval", "Cleanup policy",
                "Migration review", "Fixture hash", "No production data proof",
                "Feature flag plan", "Rollback reference", "Dry-run packet",
                "No-go blockers checked"):
        assert row.lower() in text.lower(), f"Readiness checklist row missing: {row!r}"


def test_h35_decision_output_documented():
    text = _h35_text()
    for decision in DECISION_OUTPUTS:
        assert decision in text, f"Decision output missing: {decision!r}"
    assert "BLOCKED_NO_DB" in text
    assert "Current H35 decision" in text


def test_recommended_next_step_logic_documented():
    text = _h35_text()
    for term in ("READY_FOR_DRY_RUN_EXECUTION", "BLOCKED_NO_DB", "BLOCKED_PRODUCTION_RISK",
                 "BLOCKED_NO_OWNER_APPROVAL", "Provisioning Plan", "Current recommendation"):
        assert term in text, f"Next-step logic missing: {term!r}"


def test_safety_rules_documented():
    text = _h35_text()
    for rule in ("creates no DB", "runs no SQL", "runs no migration",
                 "loads no fixture", "runs no runtime API calls",
                 "enables no feature flags", "mutates no Cloud Run",
                 "activates no Balance.ge", "no infrastructure changes",
                 "no UI/static file changes"):
        assert rule.lower() in text.lower(), f"Safety rule missing: {rule!r}"


# ---------------------------------------------------------------------------
# Local logic tests
# ---------------------------------------------------------------------------


def test_local_db_option_accepts_disposable_local():
    result = classify_db_url("postgresql://user:pw@localhost:5432/disposable_dev_db")
    assert result["allowed"] is True
    assert result["class"] == "disposable_local_db"


def test_local_db_option_accepts_docker_postgres():
    result = classify_db_url("postgresql://user:pw@localhost:5432/docker_test_db")
    assert result["allowed"] is True
    assert result["class"] in ("disposable_local_db", "docker_db")


def test_local_db_option_accepts_staging_with_marker():
    result = classify_db_url("postgresql://user:pw@staging-db.internal:5432/staging_bridge")
    assert result["allowed"] is True
    assert result["class"] == "staging_db"


def test_local_db_option_blocks_production():
    for prod_url in (
        "postgresql://user:pw@production.db.example.com:5432/bridge_prod",
        "postgresql://user:pw@prod-db:5432/maindb",
        "postgresql://user:pw@sql.goog:5432/bridge",
        "postgresql://user:pw@rgelikoshvili-db:5432/bridge",
        "postgresql://user:pw@europe-west1.run.app:5432/bridge",
    ):
        result = classify_db_url(prod_url)
        assert result["allowed"] is False, f"Production URL must be blocked: {prod_url}"
        assert result["class"] == "production_db"


def test_local_db_option_blocks_unknown():
    result = classify_db_url("postgresql://user:pw@mystery-host:5432/somedb")
    assert result["allowed"] is False
    assert result["class"] == "unknown_db"


def test_local_readiness_blocks_without_owner_approval():
    plan = {
        "db_url": "postgresql://user:pw@localhost:5432/disposable_dev",
        "owner_approval": None,
        "cleanup_plan": "drop_after",
        "fixture_hash": "abc123",
        "migration_reviewed": True,
    }
    result = evaluate_readiness(plan)
    assert result["go_decision"] == "no_go"
    assert "BLOCKED_NO_OWNER_APPROVAL" in result["blockers"]


def test_local_readiness_blocks_without_cleanup_plan():
    plan = {
        "db_url": "postgresql://user:pw@localhost:5432/disposable_dev",
        "owner_approval": "eng-owner-001",
        "cleanup_plan": "undefined",
        "fixture_hash": "abc123",
        "migration_reviewed": True,
    }
    result = evaluate_readiness(plan)
    assert result["go_decision"] == "no_go"
    assert "BLOCKED_NO_CLEANUP_PLAN" in result["blockers"]


def test_local_readiness_blocks_without_fixture_hash():
    plan = {
        "db_url": "postgresql://user:pw@localhost:5432/disposable_dev",
        "owner_approval": "eng-owner-001",
        "cleanup_plan": "drop_after",
        "fixture_hash": "",
        "migration_reviewed": True,
    }
    result = evaluate_readiness(plan)
    assert result["go_decision"] == "no_go"
    assert "BLOCKED_NO_FIXTURE_HASH" in result["blockers"]


def test_local_readiness_blocks_balance_live_connector():
    plan = {
        "db_url": "postgresql://user:pw@localhost:5432/disposable_dev",
        "owner_approval": "eng-owner-001",
        "cleanup_plan": "drop_after",
        "fixture_hash": "abc123",
        "migration_reviewed": True,
        "balance_connector_state": "live",
    }
    result = evaluate_readiness(plan)
    assert result["go_decision"] == "no_go"
    assert "balance_live_connector" in result["blockers"]


def test_local_decision_outputs_ready_only_when_all_evidence_present():
    # Missing DB → no_go
    result_no_db = evaluate_readiness({
        "db_url": "",
        "owner_approval": "eng-owner-001",
        "cleanup_plan": "drop_after",
        "fixture_hash": "abc123",
        "migration_reviewed": True,
    })
    assert result_no_db["go_decision"] == "no_go"
    assert result_no_db["decision"] in DECISION_OUTPUTS

    # All present → ready
    result_ready = evaluate_readiness({
        "db_url": "postgresql://user:pw@localhost:5432/disposable_dev",
        "owner_approval": "eng-owner-001",
        "cleanup_plan": "drop_after",
        "fixture_hash": "abc123sha256",
        "migration_reviewed": True,
        "balance_connector_state": "demo_mode",
        "production_flag_on": False,
        "production_data_detected": False,
    })
    assert result_ready["go_decision"] == "go"
    assert result_ready["decision"] == "READY_FOR_DRY_RUN_EXECUTION"


# ---------------------------------------------------------------------------
# Security / hygiene tests
# ---------------------------------------------------------------------------


def test_no_real_pii_or_tax_or_bank_patterns():
    _b_og = "Bank of Georgia"
    text_h35 = _h35_text()
    text_test = Path(__file__).read_text(encoding="utf-8")
    pii_patterns = [
        r"\b010\d{8}\b",
        r"\bGE\d{2}[A-Z0-9]{20,}\b",
        r"\b\d{16}\b",
    ]
    for pattern in pii_patterns:
        for name, text in (("H35 doc", text_h35), ("H35 test", text_test)):
            matches = re.findall(pattern, text)
            assert not matches, f"{name}: real PII pattern {pattern!r} found: {matches}"
    assert _b_og not in text_h35, "H35 doc must not contain 'Bank of Georgia' as a literal string"


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


def test_next_task_h36_documented():
    text = _h35_text()
    for term in ("H36", "Disposable/Staging DB Provisioning Plan",
                 "Runtime Comparison Dry-Run Execution",
                 "H35 is live verified"):
        assert term in text, f"Next-task H36 reference missing: {term!r}"
