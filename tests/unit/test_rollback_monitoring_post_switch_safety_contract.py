"""
H32 — Rollback / Monitoring / Post-Switch Safety Contract
Pure local contract tests. No DB. No network. No SQL. No subprocess.
"""
import re
import os
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# File references
# ---------------------------------------------------------------------------
_REPO = Path(__file__).parent.parent.parent
_H32_DOC = _REPO / "docs" / "rollback-monitoring-post-switch-safety-contract.md"
_H31_DOC = _REPO / "docs" / "production-switch-gate-contract.md"


def _h32_text() -> str:
    return _H32_DOC.read_text(encoding="utf-8")


def _h31_text() -> str:
    return _H31_DOC.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Local contract prototype helpers (not production code)
# ---------------------------------------------------------------------------

REQUIRED_ROLLBACK_PLAN_FIELDS = [
    "rollback_id", "trigger", "initiated_by", "initiated_at",
    "feature_flag", "previous_state", "target_state", "affected_tenants",
    "rollback_owner", "verification_steps", "audit_reference",
    "communication_reference", "status",
]

REQUIRED_INCIDENT_FIELDS = [
    "incident_id", "detected_at", "detected_by", "trigger_condition",
    "severity", "affected_reports", "affected_tenants", "affected_accounts",
    "evidence_links", "action_taken", "rollback_id", "resolved_at",
    "root_cause", "follow_up_tasks", "sign_offs",
]

VALID_ROLLBACK_STATUSES = {"planned", "in_progress", "completed", "failed"}

CRITICAL_TRIGGERS = {
    "tenant_leakage", "auth_bypass", "balance_activation_side_effect",
    "feature_flag_unexpected_state", "unexpected_config_mutation",
    "critical_mismatch", "security_privacy_incident", "data_corruption",
}

HIGH_TRIGGERS = {
    "high_5xx_rate", "high_latency_p95", "missing_evidence",
    "high_mismatch", "status_policy_error", "staged_rollout_halt",
    "rollback_owner_request", "accountant_no_go",
}

REQUIRED_RENABLE_FIELDS = [
    "root_cause_documented", "fix_merged", "tests_updated",
    "accountant_review_rerun", "gates_reevaluated", "monitoring_green",
    "rollback_owner_approved", "new_packet_issued", "sign_offs_refreshed",
    "staged_rollout_restarted",
]

ROLLBACK_VERIFICATION_ITEMS = [
    "version_sha_recorded", "health_checked", "feature_flag_off",
    "report_path_safe", "auth_endpoints_protected", "balance_demo_mode",
    "no_migration_executed", "no_config_mutation", "owners_notified",
    "incident_record_created", "post_rollback_report_sampled",
]


def evaluate_trigger(event: dict) -> dict:
    """Local prototype: evaluate a monitoring event and return severity + action."""
    condition = event.get("condition", "")
    value = event.get("value")

    if condition in CRITICAL_TRIGGERS:
        return {"severity": "CRITICAL", "action": "immediate_rollback", "condition": condition}

    if condition == "report_5xx_rate" and isinstance(value, (int, float)) and value > 1.0:
        return {"severity": "HIGH", "action": "rollback_evaluation", "condition": condition}

    if condition == "report_latency_p95_ms" and isinstance(value, (int, float)) and value > 3000:
        return {"severity": "HIGH", "action": "rollback_evaluation", "condition": condition}

    if condition in HIGH_TRIGGERS:
        return {"severity": "HIGH", "action": "rollback_evaluation", "condition": condition}

    return {"severity": "OK", "action": "monitor", "condition": condition}


def validate_rollback_plan(plan: dict) -> list[str]:
    """Local prototype: return list of missing fields in rollback plan."""
    missing = [f for f in REQUIRED_ROLLBACK_PLAN_FIELDS if f not in plan]
    if plan.get("status") not in VALID_ROLLBACK_STATUSES:
        missing.append("status_invalid")
    if not isinstance(plan.get("affected_tenants"), list):
        missing.append("affected_tenants_not_list")
    if not isinstance(plan.get("verification_steps"), list) or not plan.get("verification_steps"):
        missing.append("verification_steps_empty")
    if not plan.get("rollback_owner"):
        missing.append("rollback_owner_empty")
    return missing


def validate_post_rollback_checklist(checklist: dict) -> list[str]:
    """Local prototype: return items not confirmed in rollback verification checklist."""
    return [item for item in ROLLBACK_VERIFICATION_ITEMS if not checklist.get(item)]


def validate_reenable_request(req: dict) -> list[str]:
    """Local prototype: return missing requirements for safe re-enable."""
    missing = []
    for field in REQUIRED_RENABLE_FIELDS:
        if not req.get(field):
            missing.append(field)
    if not req.get("new_packet_id"):
        missing.append("new_packet_id")
    sign_offs = req.get("sign_offs", {})
    for role in ("engineering", "accounting", "rollback_owner"):
        if not sign_offs.get(role):
            missing.append(f"signoff_missing:{role}")
    return missing


def _minimal_rollback_plan() -> dict:
    return {
        "rollback_id": "RB-2026-001",
        "trigger": "tenant_leakage",
        "initiated_by": "on_call_engineer",
        "initiated_at": "2026-05-16T22:00:00Z",
        "feature_flag": "POSTED_LEDGER_REPORTS_ENABLED",
        "previous_state": "on",
        "target_state": "off",
        "affected_tenants": ["tenant_alpha"],
        "rollback_owner": "rollback_eng",
        "verification_steps": [
            "verify /health shows flag OFF",
            "verify auth endpoints 401",
        ],
        "audit_reference": "INC-2026-001",
        "communication_reference": "notify-2026-001",
        "status": "completed",
    }


def _full_post_rollback_checklist() -> dict:
    return {item: True for item in ROLLBACK_VERIFICATION_ITEMS}


def _minimal_reenable_request() -> dict:
    return {
        "root_cause_documented": True,
        "fix_merged": True,
        "tests_updated": True,
        "accountant_review_rerun": True,
        "gates_reevaluated": True,
        "monitoring_green": True,
        "rollback_owner_approved": True,
        "new_packet_issued": True,
        "new_packet_id": "PSR-2026-002",
        "sign_offs_refreshed": True,
        "staged_rollout_restarted": True,
        "sign_offs": {
            "engineering": {"signer": "eng_owner", "at": "2026-05-17T00:00:00Z"},
            "accounting": {"signer": "acct_owner", "at": "2026-05-17T00:00:00Z"},
            "rollback_owner": {"signer": "rollback_eng", "at": "2026-05-17T00:00:00Z"},
        },
    }


# ---------------------------------------------------------------------------
# Tests 1–18: Documentation coverage
# ---------------------------------------------------------------------------

def test_h32_doc_exists():
    assert _H32_DOC.exists(), f"H32 doc missing: {_H32_DOC}"


def test_h32_non_action_statement_present():
    text = _h32_text()
    assert "H32 does NOT" in text or "H32 does not" in text, \
        "H32 doc must contain a non-action statement"
    assert "POSTED_LEDGER_REPORTS_ENABLED" in text, \
        "H32 doc must reference POSTED_LEDGER_REPORTS_ENABLED"
    assert "docs/tests only" in text.lower() or "docs only" in text.lower() \
        or "Docs/tests only" in text, \
        "H32 doc must state docs/tests only"


def test_h31_context_documented():
    text = _h32_text()
    text_lower = text.lower()
    for keyword in ("G1", "G12", "no-go", "switch request packet", "staged rollout"):
        assert keyword.lower() in text_lower, \
            f"H32 doc missing H31 context keyword: {keyword!r}"


def test_rollback_philosophy_documented():
    text = _h32_text()
    for phrase in ("safe", "fast", "auditable", "reversible", "first rollback",
                   "no corruption", "no silent", "preserve evidence",
                   "no accounting", "no Balance.ge"):
        assert phrase.lower() in text.lower(), \
            f"Rollback philosophy missing phrase: {phrase!r}"


def test_rollback_trigger_conditions_documented():
    text = _h32_text()
    for trigger in ("critical mismatch", "tenant", "leakage", "status policy",
                    "missing", "evidence", "5xx", "latency", "feature flag",
                    "config mutation", "discrepancy", "security", "privacy",
                    "Balance.ge", "auth bypass", "corruption"):
        assert trigger.lower() in text.lower(), \
            f"Rollback trigger conditions missing: {trigger!r}"


def test_emergency_disable_contract_documented():
    text = _h32_text()
    for term in ("who can disable", "when to disable", "communication",
                 "emergency disable", "post-disable", "evidence preservation",
                 "owner notification", "incident ticket", "audit entry"):
        assert term.lower() in text.lower(), \
            f"Emergency disable contract missing: {term!r}"


def test_rollback_plan_contract_documented():
    text = _h32_text()
    for field in REQUIRED_ROLLBACK_PLAN_FIELDS:
        assert field in text, f"Rollback plan contract missing field: {field!r}"
    for status in ("planned", "in_progress", "completed", "failed"):
        assert status in text, f"Rollback plan contract missing status: {status!r}"


def test_rollback_verification_checklist_documented():
    text = _h32_text()
    for item in ("version", "SHA", "health", "feature flag", "401", "Balance.ge",
                 "migration", "config mutation", "notified", "incident",
                 "post-rollback"):
        assert item.lower() in text.lower(), \
            f"Rollback verification checklist missing: {item!r}"


def test_monitoring_metrics_documented():
    text = _h32_text()
    for metric in ("health_status", "version_sha", "feature_flag_state",
                   "report_5xx_rate", "report_latency_p95", "report_mismatch_count",
                   "critical_mismatch_count", "high_mismatch_count",
                   "tenant_leakage_sentinel", "auth_bypass_sentinel",
                   "balance_connector_state", "cloud_run_revision",
                   "correlation_id_coverage", "log_ingestion_freshness"):
        assert metric in text, f"Monitoring metrics missing: {metric!r}"


def test_alert_thresholds_documented():
    text = _h32_text()
    for threshold in ("tenant_leakage", "auth_bypass", "critical_mismatch",
                      "5xx", "latency", "missing_evidence", "high_mismatch",
                      "CRITICAL", "HIGH", "WARNING"):
        assert threshold in text, f"Alert thresholds missing: {threshold!r}"


def test_on_call_ownership_contract_documented():
    text = _h32_text()
    for role in ("engineering owner", "accounting owner", "product",
                 "rollback owner", "monitoring owner", "security"):
        assert role.lower() in text.lower(), \
            f"On-call ownership contract missing role: {role!r}"
    for attr in ("responsibility", "escalation", "notification"):
        assert attr.lower() in text.lower(), \
            f"On-call ownership contract missing attribute: {attr!r}"


def test_post_switch_watch_window_documented():
    text = _h32_text()
    for window in ("15 minutes", "1 hour", "business day", "close cycle"):
        assert window.lower() in text.lower(), \
            f"Post-switch watch window missing: {window!r}"
    for item in ("what to monitor", "who reviews", "rollback trigger", "evidence"):
        assert item.lower() in text.lower(), \
            f"Watch window missing column: {item!r}"


def test_staged_rollout_halt_rules_documented():
    text = _h32_text()
    for rule in ("critical alert", "high_mismatch", "missing_evidence",
                 "tenant_leakage", "auth", "feature flag", "accountant",
                 "Balance.ge", "previous stage"):
        assert rule.lower() in text.lower(), \
            f"Staged rollout halt rules missing: {rule!r}"


def test_safe_reenable_rules_documented():
    text = _h32_text()
    for rule in ("root cause", "fix pr", "tests updated", "accountant review",
                 "monitoring", "rollback owner", "new", "packet", "sign",
                 "staged rollout", "no automatic"):
        assert rule.lower() in text.lower(), \
            f"Safe re-enable rules missing: {rule!r}"


def test_incident_audit_report_contract_documented():
    text = _h32_text()
    for field in REQUIRED_INCIDENT_FIELDS:
        assert field in text, f"Incident/audit report contract missing field: {field!r}"


def test_post_switch_safety_dashboard_contract_documented():
    text = _h32_text()
    for panel in ("feature flag state", "health", "revision", "latency",
                  "mismatch", "tenant leakage", "evidence missing",
                  "rollback readiness", "owner", "on-call", "incidents",
                  "accountant sign-off"):
        assert panel.lower() in text.lower(), \
            f"Dashboard contract missing panel: {panel!r}"
    # Design only — must NOT contain implementation
    forbidden_impl = ("class Dashboard", "def render(", "React", "Vue")
    for f in forbidden_impl:
        assert f not in text, f"Dashboard contract must be design-only, found: {f!r}"


def test_production_config_mutation_rules_documented():
    text = _h32_text()
    for rule in ("cloud run", "env", "mutation", "mutated_by", "mutated_at",
                 "changed_field", "git_sha", "rollback_reference",
                 "approval_packet_reference", "critical alert", "unexpected"):
        assert rule.lower() in text.lower(), \
            f"Production config mutation rules missing: {rule!r}"


def test_safety_rules_documented():
    text = _h32_text()
    for rule in ("no db", "no runtime api", "no feature flag", "no cloud run",
                 "no balance.ge", "no connector", "no production data",
                 "no real credentials", "no infrastructure", "no ui"):
        assert rule.lower() in text.lower(), \
            f"Safety rules section missing: {rule!r}"


# ---------------------------------------------------------------------------
# Tests 19–26: Local prototype helpers
# ---------------------------------------------------------------------------

def test_local_trigger_evaluator_flags_tenant_leakage_as_critical():
    result = evaluate_trigger({"condition": "tenant_leakage"})
    assert result["severity"] == "CRITICAL"
    assert result["action"] == "immediate_rollback"


def test_local_trigger_evaluator_flags_auth_bypass_as_critical():
    result = evaluate_trigger({"condition": "auth_bypass"})
    assert result["severity"] == "CRITICAL"
    assert result["action"] == "immediate_rollback"


def test_local_trigger_evaluator_flags_balance_activation_side_effect_as_critical():
    result = evaluate_trigger({"condition": "balance_activation_side_effect"})
    assert result["severity"] == "CRITICAL"
    assert result["action"] == "immediate_rollback"


def test_local_trigger_evaluator_flags_feature_flag_unexpected_state_as_critical():
    result = evaluate_trigger({"condition": "feature_flag_unexpected_state"})
    assert result["severity"] == "CRITICAL"
    assert result["action"] == "immediate_rollback"


def test_local_trigger_evaluator_flags_high_5xx_rate():
    # Above threshold: 1.5% > 1.0%
    result = evaluate_trigger({"condition": "report_5xx_rate", "value": 1.5})
    assert result["severity"] == "HIGH"
    assert result["action"] == "rollback_evaluation"
    # Below threshold: OK
    result_ok = evaluate_trigger({"condition": "report_5xx_rate", "value": 0.5})
    assert result_ok["severity"] == "OK"


def test_local_rollback_plan_requires_owner_and_verification_steps():
    plan = _minimal_rollback_plan()
    errors = validate_rollback_plan(plan)
    assert errors == [], f"Minimal plan should be valid, got: {errors}"

    # Remove rollback_owner
    bad = dict(plan)
    del bad["rollback_owner"]
    errors = validate_rollback_plan(bad)
    assert "rollback_owner" in errors or "rollback_owner_empty" in errors, \
        "Missing rollback_owner should be flagged"

    # Remove verification_steps
    bad2 = dict(plan)
    bad2["verification_steps"] = []
    errors2 = validate_rollback_plan(bad2)
    assert "verification_steps_empty" in errors2, \
        "Empty verification_steps should be flagged"


def test_local_post_rollback_checklist_requires_feature_flag_off():
    checklist = _full_post_rollback_checklist()
    missing = validate_post_rollback_checklist(checklist)
    assert missing == [], f"Full checklist should have no missing items, got: {missing}"

    # Simulate feature_flag_off not confirmed
    incomplete = dict(checklist)
    incomplete["feature_flag_off"] = False
    missing2 = validate_post_rollback_checklist(incomplete)
    assert "feature_flag_off" in missing2, \
        "feature_flag_off=False must be reported as missing"


def test_local_safe_reenable_requires_new_packet_and_signoff():
    req = _minimal_reenable_request()
    missing = validate_reenable_request(req)
    assert missing == [], f"Minimal re-enable request should be valid, got: {missing}"

    # Missing new packet ID
    bad = dict(req)
    del bad["new_packet_id"]
    missing2 = validate_reenable_request(bad)
    assert "new_packet_id" in missing2

    # Missing rollback_owner sign-off
    bad3 = dict(req)
    bad3["sign_offs"] = {"engineering": {"signer": "e", "at": "2026-05-17T00:00:00Z"}}
    missing3 = validate_reenable_request(bad3)
    assert any("rollback_owner" in m for m in missing3), \
        "Missing rollback_owner sign-off must be flagged"


# ---------------------------------------------------------------------------
# Tests 27–29: Safety scans
# ---------------------------------------------------------------------------

def test_no_real_pii_or_tax_or_bank_patterns():
    text = _h32_text()
    # Check for real card numbers
    card_pattern = re.compile(r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b')
    assert not card_pattern.search(text), "H32 doc must not contain card number patterns"

    # Check for IBAN-like patterns
    iban_pattern = re.compile(r'\bGE\d{2}[A-Z0-9]{4}\d{16}\b')
    assert not iban_pattern.search(text), "H32 doc must not contain IBAN patterns"

    # Split-fragment check: no literal "Bank of Georgia" in doc
    _bog_fragment = "Bank " + "of Georgia"
    assert _bog_fragment not in text, \
        "H32 doc must not contain 'Bank of Georgia' as a literal string"

    # Check for private key markers via split-fragment regex — avoids SEC-1 self-trigger
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
            f"H32 doc must not contain key marker matching pattern: {pat!r}"

    # No 11-digit Georgian personal IDs
    pid_pattern = re.compile(r'\b[0-9]{11}\b')
    matches = pid_pattern.findall(text)
    assert len(matches) == 0, f"H32 doc must not contain 11-digit personal IDs: {matches}"


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
    assert found == [], f"Forbidden DB/network imports found:\n" + "\n".join(found)


def test_no_sql_or_subprocess_in_test_file():
    test_src = Path(__file__).read_text(encoding="utf-8")
    lines = test_src.splitlines()
    # All patterns anchored to line-start (^) to avoid matching string literals in this list
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
    assert found == [], f"Forbidden SQL/subprocess patterns found:\n" + "\n".join(found)


# ---------------------------------------------------------------------------
# Test 30: Next task
# ---------------------------------------------------------------------------

def test_next_task_h33_documented():
    text = _h32_text()
    assert "H33" in text, "H32 doc must reference next task H33"
    assert "Non-Production" in text or "Simulation" in text or "Staging" in text, \
        "H32 doc must describe H33 as non-production simulation or staging plan"
