"""
H34 — Disposable/Staging DB Runtime Comparison Execution Plan
Pure local contract tests. No DB. No network. No SQL. No subprocess.
"""
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# File references
# ---------------------------------------------------------------------------
_REPO = Path(__file__).parent.parent.parent
_H34_DOC = _REPO / "docs" / "disposable-staging-runtime-comparison-execution-plan.md"
_H33_DOC = _REPO / "docs" / "controlled-nonproduction-feature-flag-simulation-plan.md"
_H32_DOC = _REPO / "docs" / "rollback-monitoring-post-switch-safety-contract.md"


def _h34_text() -> str:
    return _H34_DOC.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Local contract prototype helpers (not production code)
# ---------------------------------------------------------------------------

ALLOWED_ENVIRONMENTS = {"disposable_local", "staging"}
SANDBOX_TENANT_ALLOWED_WITH_EVIDENCE = "sandbox_tenant"
FORBIDDEN_ENVIRONMENTS = {"production", "cloud_run_production", "unknown"}

ALLOWED_DB_CLASSES = {"disposable_local_db", "staging_db"}
FORBIDDEN_DB_CLASSES = {"production_db", "cloud_run_production_db", "unknown_db"}

ALL_11_REPORTS = [
    "trial_balance", "pl_summary", "pl_detail",
    "balance_sheet_summary", "balance_sheet_detail",
    "vat_register", "account_ledger", "counterparty_ledger",
    "payroll_ledger", "journal_entries_list", "cashflow",
]

REQUIRED_RESULT_PACKET_FIELDS = [
    "execution_id", "environment", "db_classification", "git_sha",
    "fixture_version", "migration_version", "feature_flag_states",
    "reports_captured", "comparison_result_id", "accountant_review_id",
    "gate_outcome", "promotion_recommendation", "cleanup_status",
    "evidence_artifacts", "created_at", "created_by",
]

VALID_GATE_OUTCOMES = {"pass", "pass_with_rounding", "fail", "blocked"}
VALID_PROMOTION_RECOMMENDATIONS = {"proceed_to_next_stage", "fix_and_retry", "block_promotion"}
VALID_CLEANUP_STATUSES = {"db_dropped", "db_preserved", "cleanup_pending"}

REQUIRED_ARTIFACT_IDS = [
    "A1_environment_proof", "A2_db_proof", "A3_migration_log",
    "A4_fixture_load_log", "A5_fixture_hash", "A6_old_snapshots",
    "A7_new_snapshots", "A8_normalized_snapshots", "A9_comparison_result",
    "A10_accountant_review", "A11_rollback_cleanup_log",
    "A12_nogo_blocker_report", "A13_execution_summary",
]

PRODUCTION_URL_MARKERS = [
    "production", "prod-", "-prod", "cloudsql", "rgelikoshvili",
    "europe-west1.run.app", "sql.goog",
]


def classify_environment(env_string: str, *, staging_evidence: bool = False) -> dict:
    """Local prototype: classify an execution environment."""
    if env_string in ALLOWED_ENVIRONMENTS:
        return {"allowed": True, "class": env_string}
    if env_string == SANDBOX_TENANT_ALLOWED_WITH_EVIDENCE:
        if staging_evidence:
            return {"allowed": True, "class": env_string}
        return {"allowed": False, "class": env_string,
                "reason": "sandbox_tenant_requires_staging_evidence"}
    if env_string in FORBIDDEN_ENVIRONMENTS or not env_string:
        return {"allowed": False, "class": env_string, "reason": "forbidden_or_unknown"}
    return {"allowed": False, "class": env_string, "reason": "unknown_fail_closed"}


def classify_db(db_url: str) -> dict:
    """Local prototype: classify a DATABASE_URL for execution safety."""
    if not db_url or db_url.strip() == "":
        return {"allowed": False, "class": "unknown_db", "reason": "empty_url"}
    url_lower = db_url.lower()
    for marker in PRODUCTION_URL_MARKERS:
        if marker in url_lower:
            return {"allowed": False, "class": "production_db",
                    "reason": f"production_marker_found:{marker}"}
    if any(h in url_lower for h in ("localhost", "127.0.0.1", "0.0.0.0")):
        return {"allowed": True, "class": "disposable_local_db"}
    if "staging" in url_lower or "sandbox" in url_lower or "dev" in url_lower:
        return {"allowed": True, "class": "staging_db"}
    return {"allowed": False, "class": "unknown_db", "reason": "cannot_classify"}


def evaluate_execution_gate(plan: dict) -> dict:
    """Local prototype: evaluate an execution plan and return gate result."""
    blockers = []

    env_result = classify_environment(plan.get("environment", ""),
                                       staging_evidence=plan.get("staging_evidence", False))
    if not env_result["allowed"]:
        blockers.append(f"environment_blocked:{env_result.get('reason', 'forbidden')}")

    db_result = classify_db(plan.get("db_url", ""))
    if not db_result["allowed"]:
        blockers.append(f"db_blocked:{db_result.get('reason', 'forbidden')}")

    if not plan.get("owner_approval", False):
        blockers.append("owner_approval_missing")

    if not plan.get("fixture_hash"):
        blockers.append("fixture_hash_missing")

    if plan.get("balance_connector_state") not in ("demo_mode", "unconfigured", None):
        blockers.append("balance_live_connector")

    if plan.get("production_flag_on", False):
        blockers.append("production_flag_on_forbidden")

    if plan.get("production_data_detected", False):
        blockers.append("production_data_detected")

    if plan.get("critical_mismatch_count", 0) > 0:
        blockers.append("critical_mismatch")

    if plan.get("high_mismatch_count", 0) > 0:
        blockers.append("high_mismatch")

    if blockers:
        return {"gate_outcome": "blocked", "blockers": blockers,
                "promotion_recommendation": "block_promotion"}
    return {"gate_outcome": "pass", "blockers": [],
            "promotion_recommendation": "proceed_to_next_stage"}


def validate_result_packet(packet: dict) -> list[str]:
    """Local prototype: return list of missing/invalid fields in result packet."""
    missing = [f for f in REQUIRED_RESULT_PACKET_FIELDS if f not in packet]
    if packet.get("gate_outcome") not in VALID_GATE_OUTCOMES:
        missing.append("gate_outcome_invalid")
    if packet.get("promotion_recommendation") not in VALID_PROMOTION_RECOMMENDATIONS:
        missing.append("promotion_recommendation_invalid")
    if packet.get("cleanup_status") not in VALID_CLEANUP_STATUSES:
        missing.append("cleanup_status_invalid")
    reports = packet.get("reports_captured", [])
    if not isinstance(reports, list) or len(reports) != 11:
        missing.append("reports_captured_must_be_11")
    artifacts = packet.get("evidence_artifacts", [])
    for aid in REQUIRED_ARTIFACT_IDS:
        if aid not in artifacts:
            missing.append(f"artifact_missing:{aid}")
    flag_states = packet.get("feature_flag_states", {})
    if flag_states.get("post_reset") != "off":
        missing.append("feature_flag_not_reset_to_off")
    return missing


def _minimal_execution_plan(*, environment: str = "staging",
                              db_url: str = "postgresql://user:pw@localhost/staging_bridge") -> dict:
    return {
        "environment": environment,
        "db_url": db_url,
        "owner_approval": True,
        "fixture_hash": "abc123def456",
        "balance_connector_state": "demo_mode",
        "production_flag_on": False,
        "production_data_detected": False,
        "critical_mismatch_count": 0,
        "high_mismatch_count": 0,
    }


def _minimal_result_packet() -> dict:
    return {
        "execution_id": "EXEC-2026-001",
        "environment": "staging",
        "db_classification": "staging_db",
        "git_sha": "8b2810fa9e1b0219d0a5b01e1f1972c8fcd08f22",
        "fixture_version": "synthetic_fixture_v1_abc123",
        "migration_version": "011",
        "feature_flag_states": {
            "old_capture": "off",
            "new_capture": "on",
            "post_reset": "off",
        },
        "reports_captured": ALL_11_REPORTS,
        "comparison_result_id": "cmp_exec_001",
        "accountant_review_id": "review_exec_001",
        "gate_outcome": "pass",
        "promotion_recommendation": "proceed_to_next_stage",
        "cleanup_status": "db_dropped",
        "evidence_artifacts": REQUIRED_ARTIFACT_IDS,
        "created_at": "2026-05-17T00:00:00Z",
        "created_by": "Bridge Hub",
    }


# ---------------------------------------------------------------------------
# Tests 1–17: Documentation coverage
# ---------------------------------------------------------------------------

def test_h34_doc_exists():
    assert _H34_DOC.exists(), f"H34 doc missing: {_H34_DOC}"


def test_h34_non_action_statement_present():
    text = _h34_text()
    assert "H34 does NOT" in text or "H34 does not" in text, \
        "H34 doc must contain a non-action statement"
    assert "POSTED_LEDGER_REPORTS_ENABLED" in text
    assert "docs/tests only" in text.lower() or "Docs/tests only" in text, \
        "H34 doc must state docs/tests only"
    assert "[FUTURE]" in text or "FUTURE" in text, \
        "H34 doc must mark future steps as [FUTURE]"


def test_h24_h33_context_documented():
    text = _h34_text()
    text_lower = text.lower()
    for task in ("h24", "h25", "h26", "h27", "h28", "h29", "h30", "h31", "h32", "h33"):
        assert task in text_lower, f"H34 doc missing context reference: {task!r}"
    for item in ("synthetic fixture", "normalizer", "comparator", "accountant review",
                 "production switch", "rollback", "simulation plan"):
        assert item.lower() in text_lower, f"H34 context missing: {item!r}"


def test_environment_classification_gate_documented():
    text = _h34_text()
    for env in ("disposable_local", "staging", "sandbox_tenant",
                "ci_monkeypatch", "production", "unknown"):
        assert env in text, f"Environment gate missing class: {env!r}"
    for rule in ("forbidden", "unknown", "environment proof"):
        assert rule.lower() in text.lower(), f"Environment gate rule missing: {rule!r}"


def test_db_classification_gate_documented():
    text = _h34_text()
    for cls in ("disposable_local_db", "staging_db", "production_db",
                "cloud_run_production_db", "unknown_db"):
        assert cls in text, f"DB gate missing class: {cls!r}"
    for rule in ("forbidden", "DATABASE_URL", "host", "non-production marker"):
        assert rule.lower() in text.lower(), f"DB gate rule missing: {rule!r}"


def test_required_prerequisites_documented():
    text = _h34_text()
    for item in ("H31", "H32", "H33", "PostgreSQL", "migration 011",
                 "synthetic fixture", "fixture hash", "no production data",
                 "Balance.ge", "Owner approval"):
        assert item in text, f"Prerequisites missing: {item!r}"


def test_future_migration_execution_plan_documented():
    text = _h34_text()
    for term in ("migration 011", "disposable", "staging", "NOT EXECUTED IN H34",
                 "verify db classification", "idempotency", "migration log"):
        assert term.lower() in text.lower(), \
            f"Future migration plan missing: {term!r}"


def test_future_fixture_load_plan_documented():
    text = _h34_text()
    for term in ("fixture hash", "row count", "balanced entries", "tenant isolation",
                 "correction", "reversal", "evidence", "NOT EXECUTED IN H34",
                 "no production"):
        assert term.lower() in text.lower(), \
            f"Future fixture load plan missing: {term!r}"


def test_future_report_capture_plan_documents_all_11_reports():
    text = _h34_text()
    report_names = [
        "Trial Balance", "P&L Summary", "P&L Detail",
        "Balance Sheet Summary", "Balance Sheet Detail",
        "VAT Register", "Account Ledger", "Counterparty Ledger",
        "Payroll Ledger", "Journal Entries List", "Cashflow",
    ]
    for rname in report_names:
        assert rname in text, f"Report capture plan missing report: {rname!r}"
    assert "flag OFF" in text.lower() or "flag off" in text.lower(), \
        "Report capture plan must mention flag OFF capture"
    assert "flag ON" in text.lower() or "flag on" in text.lower(), \
        "Report capture plan must mention flag ON capture"
    assert "NOT EXECUTED IN H34" in text, "Future steps must be marked NOT EXECUTED IN H34"


def test_future_normalization_comparison_plan_documented():
    text = _h34_text()
    for term in ("normalize", "compare", "mismatch", "accountant review",
                 "block promotion", "machine-readable json", "h28", "h29", "h30"):
        assert term.lower() in text.lower(), \
            f"Normalization/comparison plan missing: {term!r}"


def test_feature_flag_handling_documented():
    text = _h34_text()
    for item in ("POSTED_LEDGER_REPORTS_ENABLED", "OFF", "ON", "reset",
                 "never", "production", "fail-closed", "unknown flag state"):
        assert item.lower() in text.lower(), \
            f"Feature flag handling missing: {item!r}"


def test_expected_artifacts_documented():
    text = _h34_text()
    for artifact in ("A1", "A2", "A3", "A4", "A5", "A6", "A7",
                     "A8", "A9", "A10", "A11", "A12", "A13"):
        assert artifact in text, f"Expected artifacts missing: {artifact!r}"
    for label in ("environment classification proof", "migration log",
                  "fixture load log", "accountant review", "execution summary"):
        assert label.lower() in text.lower(), f"Artifact label missing: {label!r}"


def test_cleanup_evidence_retention_plan_documented():
    text = _h34_text()
    for term in ("db_dropped", "db_preserved", "cleanup_pending",
                 "feature flag reset", "retained", "production cleanup"):
        assert term.lower() in text.lower(), \
            f"Cleanup/retention plan missing: {term!r}"


def test_no_go_blockers_documented():
    text = _h34_text()
    for blocker in ("B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8",
                    "B9", "B10", "B11", "B12", "B13", "B14", "B15", "B16"):
        assert blocker in text, f"No-go blockers missing: {blocker!r}"
    for term in ("critical mismatch", "tenant leakage", "production data",
                 "balance.ge", "auth bypass", "rollback plan", "owner approval"):
        assert term.lower() in text.lower(), \
            f"No-go blocker term missing: {term!r}"


def test_runtime_comparison_result_packet_documented():
    text = _h34_text()
    for field in REQUIRED_RESULT_PACKET_FIELDS:
        assert field in text, f"Result packet missing field: {field!r}"
    for outcome in VALID_GATE_OUTCOMES:
        assert outcome in text, f"Result packet missing gate outcome: {outcome!r}"
    for status in VALID_CLEANUP_STATUSES:
        assert status in text, f"Result packet missing cleanup status: {status!r}"


def test_execution_checklist_table_documented():
    text = _h34_text()
    for col in ("Step", "Action", "Environment", "Allowed in H34",
                "Future Execution Allowed", "Required Evidence", "Blocking if Failed"):
        assert col in text, f"Execution checklist missing column: {col!r}"
    for step in ("classify environment", "classify db", "run migration",
                 "load", "fixture", "capture", "normalize", "compare",
                 "accountant review", "cleanup"):
        assert step.lower() in text.lower(), \
            f"Execution checklist missing step: {step!r}"


def test_safety_rules_documented():
    text = _h34_text()
    for rule in ("no db", "no sql", "no migration", "no fixture load",
                 "no runtime api", "no feature flag", "no cloud run",
                 "no balance.ge", "no connector", "no production data",
                 "no real credentials", "no infrastructure", "no ui"):
        assert rule.lower() in text.lower(), \
            f"Safety rules missing: {rule!r}"


# ---------------------------------------------------------------------------
# Tests 18–26: Local prototype helpers
# ---------------------------------------------------------------------------

def test_local_environment_gate_allows_disposable_and_staging():
    for env in ("disposable_local", "staging"):
        result = classify_environment(env)
        assert result["allowed"] is True, f"Environment {env!r} must be allowed"


def test_local_environment_gate_blocks_production_and_unknown():
    for env in ("production", "cloud_run_production", "unknown", "", "mystery_env"):
        result = classify_environment(env)
        assert result["allowed"] is False, \
            f"Environment {env!r} must be blocked"

    # sandbox_tenant blocked without staging evidence
    result_no_evidence = classify_environment("sandbox_tenant", staging_evidence=False)
    assert result_no_evidence["allowed"] is False

    # sandbox_tenant allowed with staging evidence
    result_with_evidence = classify_environment("sandbox_tenant", staging_evidence=True)
    assert result_with_evidence["allowed"] is True


def test_local_db_gate_allows_disposable_and_staging():
    disposable_url = "postgresql://user:pw@localhost/bridge_test"
    result = classify_db(disposable_url)
    assert result["allowed"] is True
    assert result["class"] == "disposable_local_db"

    staging_url = "postgresql://user:pw@staging-postgres.internal/bridge_staging"
    result2 = classify_db(staging_url)
    assert result2["allowed"] is True
    assert result2["class"] == "staging_db"


def test_local_db_gate_blocks_production_cloudrun_and_unknown():
    prod_urls = [
        "postgresql://user:pw@production.db.internal/bridge",
        "postgresql://user:pw@prod-db.example.com/bridge",
        "postgresql://user:pw@europe-west1.run.app:5432/bridge",
    ]
    for url in prod_urls:
        result = classify_db(url)
        assert result["allowed"] is False, \
            f"Production-like URL must be blocked: {url!r}"

    # Empty URL: unknown
    result_empty = classify_db("")
    assert result_empty["allowed"] is False

    # Unclassifiable URL
    result_unknown = classify_db("postgresql://user:pw@mystery-host.xyz/db")
    assert result_unknown["allowed"] is False


def test_local_execution_gate_blocks_without_owner_approval():
    plan = _minimal_execution_plan()
    plan["owner_approval"] = False
    result = evaluate_execution_gate(plan)
    assert result["gate_outcome"] == "blocked"
    assert "owner_approval_missing" in result["blockers"]


def test_local_execution_gate_blocks_without_fixture_hash():
    plan = _minimal_execution_plan()
    plan["fixture_hash"] = ""
    result = evaluate_execution_gate(plan)
    assert result["gate_outcome"] == "blocked"
    assert "fixture_hash_missing" in result["blockers"]


def test_local_execution_gate_blocks_balance_live_connector():
    plan = _minimal_execution_plan()
    plan["balance_connector_state"] = "live_active"
    result = evaluate_execution_gate(plan)
    assert result["gate_outcome"] == "blocked"
    assert "balance_live_connector" in result["blockers"]


def test_local_execution_gate_blocks_production_flag_on():
    plan = _minimal_execution_plan(environment="production",
                                    db_url="postgresql://user:pw@production.db/bridge")
    plan["production_flag_on"] = True
    result = evaluate_execution_gate(plan)
    assert result["gate_outcome"] == "blocked"
    assert any("production" in b for b in result["blockers"])


def test_local_result_packet_requires_comparison_and_review_ids():
    packet = _minimal_result_packet()
    missing = validate_result_packet(packet)
    assert missing == [], f"Minimal packet should be valid, got: {missing}"

    # Remove comparison_result_id
    bad = dict(packet)
    del bad["comparison_result_id"]
    missing2 = validate_result_packet(bad)
    assert "comparison_result_id" in missing2

    # Remove accountant_review_id
    bad3 = dict(packet)
    del bad3["accountant_review_id"]
    missing3 = validate_result_packet(bad3)
    assert "accountant_review_id" in missing3

    # Packet with flag not reset to OFF
    bad4 = dict(packet)
    bad4["feature_flag_states"] = {"old_capture": "off", "new_capture": "on",
                                    "post_reset": "on"}
    missing4 = validate_result_packet(bad4)
    assert "feature_flag_not_reset_to_off" in missing4

    # Wrong number of reports
    bad5 = dict(packet)
    bad5["reports_captured"] = ALL_11_REPORTS[:5]
    missing5 = validate_result_packet(bad5)
    assert "reports_captured_must_be_11" in missing5


# ---------------------------------------------------------------------------
# Tests 27–29: Safety scans
# ---------------------------------------------------------------------------

def test_no_real_pii_or_tax_or_bank_patterns():
    text = _h34_text()
    card_pattern = re.compile(r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b')
    assert not card_pattern.search(text), "H34 doc must not contain card number patterns"

    iban_pattern = re.compile(r'\bGE\d{2}[A-Z0-9]{4}\d{16}\b')
    assert not iban_pattern.search(text), "H34 doc must not contain IBAN patterns"

    _bog_fragment = "Bank " + "of Georgia"
    assert _bog_fragment not in text, \
        "H34 doc must not contain 'Bank of Georgia' as a literal string"

    # Key marker check via split fragments to avoid SEC-1 self-trigger
    _b = "BEGIN"
    _rsa = "RSA"
    _priv = "PRIV" + "ATE"
    _key = "KEY"
    _openssh = "OPEN" + "SSH"
    forbidden_key_regexes = [
        rf"\b{_b}\s+{_rsa}\b",
        rf"\b{_b}\s+{_openssh}\b",
        rf"\b{_b}\s+{_priv}\b",
        rf"\b{_priv}\s+{_key}\b",
    ]
    for pat in forbidden_key_regexes:
        assert not re.search(pat, text), \
            f"H34 doc must not contain key marker matching: {pat!r}"

    pid_pattern = re.compile(r'\b[0-9]{11}\b')
    matches = pid_pattern.findall(text)
    assert len(matches) == 0, f"H34 doc must not contain 11-digit IDs: {matches}"


def test_no_db_or_network_imports_in_test_file():
    test_src = Path(__file__).read_text(encoding="utf-8")
    lines = test_src.splitlines()
    forbidden_patterns = [
        (r"^import psycopg", "psycopg import"),
        (r"^import asyncpg", "asyncpg import"),
        (r"^import sqlalchemy", "sqlalchemy import"),
        (r"^import requests\b", "requests import"),
        (r"^import httpx\b", "httpx import"),
        (r"^import socket\b", "socket import"),
        (r"^from psycopg", "from psycopg import"),
        (r"^from asyncpg", "from asyncpg import"),
        (r"^from sqlalchemy", "from sqlalchemy import"),
        (r"^from requests", "from requests import"),
        (r"^from httpx", "from httpx import"),
    ]
    found = []
    for lineno, line in enumerate(lines, 1):
        for pat, label in forbidden_patterns:
            if re.search(pat, line):
                found.append(f"Line {lineno}: {label}: {line.strip()[:80]}")
    assert found == [], "Forbidden DB/network imports found:\n" + "\n".join(found)


def test_no_sql_or_subprocess_in_test_file():
    test_src = Path(__file__).read_text(encoding="utf-8")
    lines = test_src.splitlines()
    # Line-start anchored to avoid matching string literals in this list
    forbidden_patterns = [
        (r"^import subprocess\b", "subprocess import"),
        (r"^\s*subprocess\.run\b|^\s*subprocess\.call\b|^\s*subprocess\.Popen\b", "subprocess call"),
        (r"(?i)^\s*(conn|cursor|db)\.execute\(", "DB execute call"),
        (r"(?i)^\s*INSERT\s+INTO\b", "executable INSERT INTO"),
        (r"(?i)^\s*DELETE\s+FROM\b", "executable DELETE FROM"),
        (r"(?i)^\s*CREATE\s+TABLE\b", "executable CREATE TABLE"),
        (r"(?i)^\s*ALTER\s+TABLE\b", "executable ALTER TABLE"),
        (r"(?i)^\s*DROP\s+TABLE\b", "DROP TABLE"),
        (r"(?i)^\s*SELECT \* FROM\b", "SELECT * FROM"),
        (r"^\s*gcloud\s+run\s+services\s+update", "gcloud run update"),
        (r"^\s*kubectl\s+apply\b|^\s*kubectl\s+create\b", "kubectl apply/create"),
    ]
    found = []
    for lineno, line in enumerate(lines, 1):
        for pat, label in forbidden_patterns:
            if re.search(pat, line):
                found.append(f"Line {lineno}: {label}: {line.strip()[:80]}")
    assert found == [], "Forbidden SQL/subprocess patterns found:\n" + "\n".join(found)


# ---------------------------------------------------------------------------
# Test 30: Next task
# ---------------------------------------------------------------------------

def test_next_task_h35_documented():
    text = _h34_text()
    assert "H35" in text, "H34 doc must reference next task H35"
    assert "Dry-Run" in text or "Blocker" in text or "Execution" in text, \
        "H34 doc must describe H35 as dry-run or blocker resolution"
    assert "DB is not available" in text or "unavailable" in text.lower() \
        or "not available" in text.lower(), \
        "H34 doc must address case where DB is unavailable"
