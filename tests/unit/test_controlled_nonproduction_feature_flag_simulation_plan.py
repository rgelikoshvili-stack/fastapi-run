"""
H33 — Controlled Non-Production Feature Flag Simulation Plan
Pure local contract tests. No DB. No network. No SQL. No subprocess.
"""
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# File references
# ---------------------------------------------------------------------------
_REPO = Path(__file__).parent.parent.parent
_H33_DOC = _REPO / "docs" / "controlled-nonproduction-feature-flag-simulation-plan.md"
_H31_DOC = _REPO / "docs" / "production-switch-gate-contract.md"
_H32_DOC = _REPO / "docs" / "rollback-monitoring-post-switch-safety-contract.md"


def _h33_text() -> str:
    return _H33_DOC.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Local contract prototype helpers (not production code)
# ---------------------------------------------------------------------------

ALLOWED_ENVIRONMENTS = {"disposable_local", "staging", "sandbox_tenant", "ci_monkeypatch"}
FORBIDDEN_ENVIRONMENTS = {"production", "cloud_run_production", "production_db", "unknown"}

ALLOWED_TRUE_FLAG_VALUES = {"1", "true", "yes"}

REQUIRED_SIMULATION_PACKET_FIELDS = [
    "simulation_id", "environment", "tenant_id", "feature_flag", "flag_state",
    "db_classification", "fixture_version", "migration_version", "old_snapshot_id",
    "new_snapshot_id", "comparison_result_id", "accountant_review_id",
    "gate_outcome", "promotion_recommendation", "rollback_reference",
    "created_at", "created_by",
]

VALID_GATE_OUTCOMES = {"pass", "pass_with_rounding", "fail", "blocked"}
VALID_PROMOTION_RECOMMENDATIONS = {"proceed_to_next_stage", "fix_and_retry", "block_promotion"}

PROMOTION_BLOCKERS = [
    "critical_mismatch", "high_mismatch", "tenant_leakage",
    "missing_evidence", "status_policy_mismatch", "fixture_load_failure",
    "db_classification_uncertain", "environment_classification_uncertain",
    "balance_live_connector", "production_data_detected",
    "no_accountant_review", "no_rollback_plan", "no_owner_approval",
    "feature_flag_state_mismatch",
]


def classify_environment(env_string: str) -> dict:
    """Local prototype: classify an environment string for simulation."""
    if env_string in ALLOWED_ENVIRONMENTS:
        return {"allowed": True, "environment": env_string, "simulation_permitted": True}
    if env_string in FORBIDDEN_ENVIRONMENTS or not env_string:
        return {"allowed": False, "environment": env_string, "simulation_permitted": False,
                "reason": "forbidden_or_unknown"}
    # Unknown: fail closed
    return {"allowed": False, "environment": env_string, "simulation_permitted": False,
            "reason": "unknown_environment_fail_closed"}


def parse_feature_flag(raw_value: str | None, environment: str) -> dict:
    """Local prototype: parse feature flag value with environment guard."""
    env_class = classify_environment(environment)
    if not env_class["allowed"]:
        return {"enabled": False, "reason": "forbidden_environment", "raw": raw_value}
    if raw_value is None or str(raw_value).strip() == "":
        return {"enabled": False, "reason": "absent_treated_as_off", "raw": raw_value}
    if str(raw_value).strip().lower() in ALLOWED_TRUE_FLAG_VALUES:
        return {"enabled": True, "reason": "explicit_true", "raw": raw_value}
    return {"enabled": False, "reason": "unknown_value_treated_as_off", "raw": raw_value}


def evaluate_simulation_gate(plan: dict) -> dict:
    """Local prototype: evaluate a simulation plan and return gate result."""
    blockers = []

    env = plan.get("environment", "")
    env_class = classify_environment(env)
    if not env_class["allowed"]:
        blockers.append("environment_classification_uncertain")

    if plan.get("flag_state") == "on" and env in FORBIDDEN_ENVIRONMENTS | {"production"}:
        blockers.append("production_flag_on_forbidden")

    if plan.get("balance_connector_state") not in ("demo_mode", "unconfigured", None):
        blockers.append("balance_live_connector")

    if plan.get("production_data_detected", False):
        blockers.append("production_data_detected")

    if not plan.get("rollback_reference"):
        blockers.append("no_rollback_plan")

    if not plan.get("accountant_review_id") and plan.get("gate_outcome") not in (None, "blocked"):
        blockers.append("no_accountant_review")

    db_class = plan.get("db_classification", "")
    if db_class == "production" or "prod" in db_class.lower():
        blockers.append("db_classification_uncertain")

    mismatch = plan.get("critical_mismatch_count", 0)
    if isinstance(mismatch, int) and mismatch > 0:
        blockers.append("critical_mismatch")

    high = plan.get("high_mismatch_count", 0)
    if isinstance(high, int) and high > 0:
        blockers.append("high_mismatch")

    if blockers:
        return {"gate_outcome": "blocked", "blockers": blockers,
                "promotion_recommendation": "block_promotion"}
    return {"gate_outcome": "pass", "blockers": [],
            "promotion_recommendation": "proceed_to_next_stage"}


def validate_simulation_packet(packet: dict) -> list[str]:
    """Local prototype: return list of missing fields in simulation result packet."""
    missing = [f for f in REQUIRED_SIMULATION_PACKET_FIELDS if f not in packet]
    if packet.get("gate_outcome") not in VALID_GATE_OUTCOMES:
        missing.append("gate_outcome_invalid")
    if packet.get("promotion_recommendation") not in VALID_PROMOTION_RECOMMENDATIONS:
        missing.append("promotion_recommendation_invalid")
    if packet.get("feature_flag") != "POSTED_LEDGER_REPORTS_ENABLED":
        missing.append("feature_flag_incorrect")
    return missing


def _minimal_simulation_plan(*, environment: str = "staging",
                              flag_state: str = "on") -> dict:
    return {
        "environment": environment,
        "flag_state": flag_state,
        "balance_connector_state": "demo_mode",
        "production_data_detected": False,
        "rollback_reference": "docs/rollback-monitoring-post-switch-safety-contract.md",
        "accountant_review_id": "review_sim_001",
        "db_classification": "staging",
        "critical_mismatch_count": 0,
        "high_mismatch_count": 0,
    }


def _minimal_simulation_packet() -> dict:
    return {
        "simulation_id": "SIM-2026-001",
        "environment": "staging",
        "tenant_id": "tenant_alpha",
        "feature_flag": "POSTED_LEDGER_REPORTS_ENABLED",
        "flag_state": "on",
        "db_classification": "staging",
        "fixture_version": "synthetic_fixture_v1",
        "migration_version": "011",
        "old_snapshot_id": "snap_old_001",
        "new_snapshot_id": "snap_new_001",
        "comparison_result_id": "cmp_001",
        "accountant_review_id": "review_sim_001",
        "gate_outcome": "pass",
        "promotion_recommendation": "proceed_to_next_stage",
        "rollback_reference": "docs/rollback-monitoring-post-switch-safety-contract.md",
        "created_at": "2026-05-17T00:00:00Z",
        "created_by": "Bridge Hub",
    }


# ---------------------------------------------------------------------------
# Tests 1–14: Documentation coverage
# ---------------------------------------------------------------------------

def test_h33_doc_exists():
    assert _H33_DOC.exists(), f"H33 doc missing: {_H33_DOC}"


def test_h33_non_action_statement_present():
    text = _h33_text()
    assert "H33 does NOT" in text or "H33 does not" in text, \
        "H33 doc must contain a non-action statement"
    assert "POSTED_LEDGER_REPORTS_ENABLED" in text, \
        "H33 doc must reference POSTED_LEDGER_REPORTS_ENABLED"
    assert "docs/tests only" in text.lower() or "Docs/tests only" in text, \
        "H33 doc must state docs/tests only"


def test_feature_flag_identity_documented():
    text = _h33_text()
    for term in ("POSTED_LEDGER_REPORTS_ENABLED", "fail-closed", "OFF",
                 "true", "absent", "production", "silent fallback", "forbidden"):
        assert term.lower() in text.lower(), \
            f"Feature flag identity missing: {term!r}"


def test_nonproduction_environment_classification_documented():
    text = _h33_text()
    for env in ("disposable local", "staging", "sandbox tenant",
                "ci", "monkeypatch", "production"):
        assert env.lower() in text.lower(), \
            f"Environment classification missing: {env!r}"
    for rule in ("forbidden", "fail closed", "unknown"):
        assert rule.lower() in text.lower(), \
            f"Environment rule missing: {rule!r}"


def test_simulation_preconditions_documented():
    text = _h33_text()
    for item in ("non-production", "synthetic fixture", "migration version",
                 "fixture hash", "Balance.ge", "demo", "owner approval",
                 "rollback", "normalizer", "comparator", "accountant review"):
        assert item.lower() in text.lower(), \
            f"Simulation preconditions missing: {item!r}"


def test_simulation_matrix_documented():
    text = _h33_text()
    for col in ("Environment", "DB Source", "Data Source", "Flag State",
                "Allowed", "Required Approval", "Expected Output", "Promotion Allowed"):
        assert col in text, f"Simulation matrix missing column: {col!r}"
    # Forbidden rows must be documented
    for forbidden in ("FORBIDDEN", "forbidden", "Never"):
        assert forbidden in text, f"Simulation matrix missing forbidden marker: {forbidden!r}"
    # Both ON and OFF rows
    assert "ON" in text and "OFF" in text, "Matrix must show both ON and OFF flag states"


def test_production_guard_rules_documented():
    text = _h33_text()
    for rule in ("forbidden", "production db", "production cloud run",
                 "production customer data", "balance.ge", "demo_mode",
                 "absent", "production flag on"):
        assert rule.lower() in text.lower(), \
            f"Production guard rules missing: {rule!r}"


def test_required_evidence_before_simulation_documented():
    text = _h33_text()
    for item in ("environment classification proof", "db classification proof",
                 "fixture hash", "migration version", "feature flag state proof",
                 "balance.ge", "no production data", "test command output",
                 "rollback reference", "owner approval"):
        assert item.lower() in text.lower(), \
            f"Required evidence missing: {item!r}"


def test_expected_simulation_outputs_documented():
    text = _h33_text()
    for output in ("old path snapshot", "posted-ledger path snapshot",
                   "normalizer", "comparator result", "accountant review",
                   "mismatch summary", "gate outcome", "promotion recommendation",
                   "proceed_to_next_stage", "fix_and_retry", "block_promotion"):
        assert output.lower() in text.lower(), \
            f"Expected simulation outputs missing: {output!r}"


def test_nonproduction_rollback_disable_rules_documented():
    text = _h33_text()
    for rule in ("disable", "flag", "off", "verify", "no production rollback",
                 "preserve", "artifact", "simulation result"):
        assert rule.lower() in text.lower(), \
            f"Non-production rollback/disable rules missing: {rule!r}"


def test_promotion_blockers_documented():
    text = _h33_text()
    for blocker in ("critical mismatch", "high mismatch", "tenant leakage",
                    "evidence/drilldown", "status policy", "fixture load failure",
                    "db classification", "environment classification",
                    "balance", "production data", "accountant review",
                    "rollback plan", "owner approval"):
        assert blocker.lower() in text.lower(), \
            f"Promotion blockers missing: {blocker!r}"


def test_simulation_result_packet_documented():
    text = _h33_text()
    for field in REQUIRED_SIMULATION_PACKET_FIELDS:
        assert field in text, f"Simulation result packet missing field: {field!r}"
    for outcome in VALID_GATE_OUTCOMES:
        assert outcome in text, f"Simulation result packet missing gate outcome: {outcome!r}"


def test_ci_monkeypatch_rules_documented():
    text = _h33_text()
    for rule in ("monkeypatch", "TEST_MODE", "no real DB", "no Cloud Run",
                 "no production data", "production guard", "fail closed",
                 "test-local", "ci simulation", "staging simulation"):
        assert rule.lower() in text.lower(), \
            f"CI/monkeypatch rules missing: {rule!r}"


def test_safety_rules_documented():
    text = _h33_text()
    for rule in ("no db", "no runtime api", "no feature flag", "no cloud run",
                 "no balance.ge", "no connector", "no production data",
                 "no real credentials", "no infrastructure", "no ui"):
        assert rule.lower() in text.lower(), \
            f"Safety rules missing: {rule!r}"


# ---------------------------------------------------------------------------
# Tests 15–25: Local prototype helpers
# ---------------------------------------------------------------------------

def test_local_environment_classifier_allows_disposable_local():
    result = classify_environment("disposable_local")
    assert result["allowed"] is True
    assert result["simulation_permitted"] is True


def test_local_environment_classifier_allows_staging():
    result = classify_environment("staging")
    assert result["allowed"] is True
    assert result["simulation_permitted"] is True


def test_local_environment_classifier_blocks_production():
    for env in ("production", "cloud_run_production", "production_db"):
        result = classify_environment(env)
        assert result["allowed"] is False, \
            f"Production environment {env!r} must be blocked"
        assert result["simulation_permitted"] is False


def test_local_environment_classifier_blocks_unknown():
    result = classify_environment("some_unknown_env_XYZ")
    assert result["allowed"] is False
    assert result["simulation_permitted"] is False
    assert "unknown" in result.get("reason", "").lower() or \
           "unknown" in result.get("environment", "").lower() or \
           "fail_closed" in result.get("reason", "").lower()

    # Empty string also fails closed
    result_empty = classify_environment("")
    assert result_empty["allowed"] is False


def test_local_feature_flag_parser_defaults_false():
    # Absent flag → OFF
    for env in ("disposable_local", "staging", "ci_monkeypatch"):
        result = parse_feature_flag(None, env)
        assert result["enabled"] is False, \
            f"Absent flag must default to OFF for env={env!r}"

    # Empty string → OFF
    result_empty = parse_feature_flag("", "staging")
    assert result_empty["enabled"] is False

    # Unknown value → OFF
    result_unknown = parse_feature_flag("maybe", "staging")
    assert result_unknown["enabled"] is False


def test_local_feature_flag_parser_accepts_true_values_only_for_nonproduction():
    for val in ("1", "true", "yes"):
        # Allowed in non-production
        result = parse_feature_flag(val, "staging")
        assert result["enabled"] is True, \
            f"Value {val!r} must enable flag in staging"

        # Blocked in production
        result_prod = parse_feature_flag(val, "production")
        assert result_prod["enabled"] is False, \
            f"Value {val!r} must NOT enable flag in production"


def test_local_simulation_gate_blocks_production_flag_on():
    plan = _minimal_simulation_plan(environment="production", flag_state="on")
    result = evaluate_simulation_gate(plan)
    assert result["gate_outcome"] == "blocked"
    assert result["promotion_recommendation"] == "block_promotion"
    assert any("production" in b or "environment" in b or "forbidden" in b
               for b in result["blockers"]), \
        "Production flag ON must be listed as a blocker"


def test_local_simulation_gate_blocks_balance_live_connector():
    plan = _minimal_simulation_plan()
    plan["balance_connector_state"] = "live_active"
    result = evaluate_simulation_gate(plan)
    assert result["gate_outcome"] == "blocked"
    assert "balance_live_connector" in result["blockers"]


def test_local_simulation_gate_blocks_production_data():
    plan = _minimal_simulation_plan()
    plan["production_data_detected"] = True
    result = evaluate_simulation_gate(plan)
    assert result["gate_outcome"] == "blocked"
    assert "production_data_detected" in result["blockers"]


def test_local_simulation_gate_requires_rollback_reference():
    plan = _minimal_simulation_plan()
    plan["rollback_reference"] = ""
    result = evaluate_simulation_gate(plan)
    assert result["gate_outcome"] == "blocked"
    assert "no_rollback_plan" in result["blockers"]


def test_local_simulation_packet_requires_snapshot_and_review_ids():
    packet = _minimal_simulation_packet()
    missing = validate_simulation_packet(packet)
    assert missing == [], f"Minimal packet should be valid, got: {missing}"

    # Remove snapshot IDs
    bad = dict(packet)
    del bad["old_snapshot_id"]
    del bad["new_snapshot_id"]
    missing2 = validate_simulation_packet(bad)
    assert "old_snapshot_id" in missing2
    assert "new_snapshot_id" in missing2

    # Wrong feature flag name
    bad3 = dict(packet)
    bad3["feature_flag"] = "WRONG_FLAG"
    missing3 = validate_simulation_packet(bad3)
    assert "feature_flag_incorrect" in missing3


# ---------------------------------------------------------------------------
# Tests 26–28: Safety scans
# ---------------------------------------------------------------------------

def test_no_real_pii_or_tax_or_bank_patterns():
    text = _h33_text()
    # Card number pattern
    card_pattern = re.compile(r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b')
    assert not card_pattern.search(text), "H33 doc must not contain card number patterns"

    # IBAN-like patterns
    iban_pattern = re.compile(r'\bGE\d{2}[A-Z0-9]{4}\d{16}\b')
    assert not iban_pattern.search(text), "H33 doc must not contain IBAN patterns"

    # Split-fragment: no literal "Bank of Georgia"
    _bog_fragment = "Bank " + "of Georgia"
    assert _bog_fragment not in text, \
        "H33 doc must not contain 'Bank of Georgia' as a literal string"

    # No private key markers — split to avoid SEC-1 self-trigger
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
            f"H33 doc must not contain key marker matching: {pat!r}"

    # No 11-digit personal IDs
    pid_pattern = re.compile(r'\b[0-9]{11}\b')
    matches = pid_pattern.findall(text)
    assert len(matches) == 0, f"H33 doc must not contain 11-digit personal IDs: {matches}"


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
    # All patterns anchored to line-start to avoid matching string literals in this list
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
# Test 29: Next task
# ---------------------------------------------------------------------------

def test_next_task_h34_documented():
    text = _h33_text()
    assert "H34" in text, "H33 doc must reference next task H34"
    assert "Disposable" in text or "Staging" in text or "Dry-Run" in text or "Execution" in text, \
        "H33 doc must describe H34 as execution/staging plan"
