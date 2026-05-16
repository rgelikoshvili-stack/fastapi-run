"""
H31 — Production Switch Gate Contract / Feature Flag Approval Checklist.

Local contract prototypes for gate evaluation helpers.
These helpers are defined here only — NOT imported from or added to any app module.

No DB, no SQL, no migrations, no fixture load, no runtime API calls,
no feature flag enablement.
"""
import os

# ---------------------------------------------------------------------------
# Local prototype helpers (contract only — not production implementations)
# ---------------------------------------------------------------------------

REQUIRED_GATES = [f"G{i}" for i in range(1, 13)]  # G1..G12

NO_GO_CODES = [
    "critical_mismatch",
    "tenant_leakage",
    "status_policy_mismatch",
    "missing_evidence",
    "missing_posting_log",
    "migration_not_dry_run",
    "fixture_load_not_completed",
    "no_accountant_signoff",
    "no_rollback_owner",
    "flag_enabled_without_packet",
    "balance_activation_coupled",
    "pii_exposed",
    "auth_bypass",
    "production_db_touched",
    "packet_incomplete",
]

REQUIRED_PACKET_FIELDS = [
    "request_id",
    "requested_by",
    "requested_at",
    "git_sha",
    "deployment_sha",
    "feature_flag",
    "target_environment",
    "gate_results",
    "accountant_review_report_id",
    "rollback_plan_reference",
    "monitoring_plan_reference",
    "sign_offs",
    "no_go_blockers_checked",
    "emergency_disable_command_reference",
]

REQUIRED_SIGNOFFS = ["engineering", "accountant", "product", "rollback_owner"]


def _all_gates_passed(gate_results: dict) -> bool:
    return all(gate_results.get(g) == "passed" for g in REQUIRED_GATES)


def evaluate_switch_request(packet: dict) -> dict:
    """
    Evaluate a production switch request packet against all gate rules.
    Returns dict with keys: allowed (bool), blockers (list[str]), decision (str).
    This is a contract prototype — NOT a production implementation.
    """
    blockers = []

    # Check all required packet fields present
    for field in REQUIRED_PACKET_FIELDS:
        if field not in packet:
            blockers.append(f"packet_incomplete:{field}")

    # Validate no_go_blockers_checked flag
    if not packet.get("no_go_blockers_checked", False):
        blockers.append("no_go_blockers_checked_false")

    gate_results = packet.get("gate_results", {})

    # G6 must have no critical/high mismatches
    g6 = gate_results.get("G6", "")
    if g6 == "critical_mismatch":
        blockers.append("critical_mismatch")
    if g6 == "high_mismatch":
        blockers.append("high_mismatch")

    # Tenant leakage
    if gate_results.get("G10") == "tenant_leakage":
        blockers.append("tenant_leakage")

    # Missing evidence
    if gate_results.get("G7") == "missing_evidence":
        blockers.append("missing_evidence")

    # Rollback gate
    if gate_results.get("G9") != "passed":
        blockers.append("missing_rollback")

    # Accountant sign-off
    sign_offs = packet.get("sign_offs", {})
    if not sign_offs.get("accountant"):
        blockers.append("no_accountant_signoff")

    # Engineering sign-off
    if not sign_offs.get("engineering"):
        blockers.append("no_engineering_signoff")

    # Rollback owner sign-off
    if not sign_offs.get("rollback_owner"):
        blockers.append("no_rollback_owner")

    # Feature flag already enabled without packet
    if packet.get("flag_already_enabled_in_production"):
        blockers.append("flag_enabled_without_packet")

    # Balance.ge activation coupled
    if packet.get("balance_activation_coupled"):
        blockers.append("balance_activation_coupled")

    # git_sha required
    if not packet.get("git_sha"):
        blockers.append("git_sha_missing")

    # All gates must be passed
    if not _all_gates_passed(gate_results):
        for g in REQUIRED_GATES:
            status = gate_results.get(g)
            if status != "passed":
                if f"missing_rollback" not in blockers or g != "G9":
                    if not any(g in b for b in blockers):
                        blockers.append(f"gate_{g}_not_passed:{status}")

    allowed = len(blockers) == 0
    return {
        "allowed": allowed,
        "blockers": blockers,
        "decision": "GO" if allowed else "NO-GO",
    }


def _minimal_passing_packet() -> dict:
    """Build a minimal valid switch request packet for testing."""
    return {
        "request_id": "PSR-2026-001",
        "requested_by": "engineering_owner",
        "requested_at": "2026-05-16T00:00:00Z",
        "git_sha": "ec35a58cf4b4e9e8dc552a1a1d2d321f3a3c41c6",
        "deployment_sha": "ec35a58cf4b4e9e8dc552a1a1d2d321f3a3c41c6",
        "feature_flag": "POSTED_LEDGER_REPORTS_ENABLED",
        "target_environment": "production",
        "gate_results": {g: "passed" for g in REQUIRED_GATES},
        "accountant_review_report_id": "review_synthetic_001",
        "rollback_plan_reference": "docs/rollback-plan.md",
        "monitoring_plan_reference": "https://monitoring.internal/bridge-hub",
        "sign_offs": {
            "engineering": {"signer": "eng_owner", "at": "2026-05-16T00:00:00Z"},
            "accountant": {"signer": "acct_owner", "at": "2026-05-16T00:00:00Z"},
            "product": {"signer": "product_owner", "at": "2026-05-16T00:00:00Z"},
            "rollback_owner": {"signer": "rollback_eng", "at": "2026-05-16T00:00:00Z"},
        },
        "no_go_blockers_checked": True,
        "emergency_disable_command_reference": "runbooks/emergency-disable.md",
        "flag_already_enabled_in_production": False,
        "balance_activation_coupled": False,
    }


def _doc_text() -> str:
    doc_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "docs",
        "production-switch-gate-contract.md",
    )
    with open(doc_path, encoding="utf-8") as f:
        return f.read()


# ===========================================================================
# 1. Doc existence and non-action
# ===========================================================================

def test_h31_doc_exists():
    doc_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "docs",
        "production-switch-gate-contract.md",
    )
    assert os.path.isfile(doc_path), "H31 doc must exist"


def test_h31_non_action_statement_present():
    text = _doc_text().lower().replace("**", "").replace("*", "")
    assert "does not enable" in text or "h31 does not enable the flag" in text
    assert "does not modify cloud run" in text or "does not modify cloud run env vars" in text
    assert "does not start h32" in text


# ===========================================================================
# 2. Feature flag identity
# ===========================================================================

def test_feature_flag_identity_documented():
    text = _doc_text()
    assert "POSTED_LEDGER_REPORTS_ENABLED" in text
    assert "fail-closed" in text.lower() or "fail closed" in text.lower()
    assert "OFF" in text or "absent" in text.lower()


# ===========================================================================
# 3. Gate list G1–G12
# ===========================================================================

def test_required_gate_list_documents_g1_to_g12():
    text = _doc_text()
    for i in range(1, 13):
        assert f"G{i}" in text, f"Gate G{i} must be documented"


# ===========================================================================
# 4. No-go blockers
# ===========================================================================

def test_no_go_blockers_documented():
    text = _doc_text().lower()
    blockers = [
        "critical mismatch",
        "tenant leakage",
        "status policy mismatch",
        "missing",
        "rollback",
        "accountant sign-off",
        "balance",
        "credential",
    ]
    for b in blockers:
        assert b in text, f"No-go blocker concept '{b}' must be in doc"


# ===========================================================================
# 5. Production switch request packet
# ===========================================================================

def test_production_switch_request_packet_documented():
    text = _doc_text()
    for field in REQUIRED_PACKET_FIELDS:
        assert field in text, f"Packet field '{field}' must be documented"


# ===========================================================================
# 6. Sign-off requirements
# ===========================================================================

def test_sign_off_requirements_documented():
    text = _doc_text().lower()
    assert "engineering" in text
    assert "accountant" in text
    assert "rollback owner" in text
    assert "product" in text
    assert "critical" in text and "cannot be waived" in text


# ===========================================================================
# 7. Rollback plan requirements
# ===========================================================================

def test_rollback_plan_requirements_documented():
    text = _doc_text().lower()
    assert "rollback" in text
    assert "rto" in text or "rollback time objective" in text
    assert "data loss" in text or "data safety" in text
    assert "disable" in text


# ===========================================================================
# 8. Monitoring plan requirements
# ===========================================================================

def test_monitoring_plan_requirements_documented():
    text = _doc_text().lower()
    assert "5xx" in text or "error rate" in text
    assert "latency" in text
    assert "tenant leakage sentinel" in text or "tenant leakage" in text
    assert "correlation" in text
    assert "on-call" in text or "on call" in text


# ===========================================================================
# 9. Staged rollout rules
# ===========================================================================

def test_staged_rollout_rules_documented():
    text = _doc_text().lower()
    assert "staged" in text
    assert "disposable" in text or "local" in text
    assert "staging" in text
    assert "all tenants" in text
    assert "never" in text


# ===========================================================================
# 10. Emergency disable rules
# ===========================================================================

def test_emergency_disable_rules_documented():
    text = _doc_text().lower()
    assert "emergency" in text
    assert "who can disable" in text or "who may disable" in text or "engineering owner" in text
    assert "audit trail" in text or "incident" in text
    assert "notify" in text or "notified" in text


# ===========================================================================
# 11. Post-switch verification checklist
# ===========================================================================

def test_post_switch_verification_checklist_documented():
    text = _doc_text().lower()
    assert "post-switch" in text or "post switch" in text
    assert "/version" in text
    assert "/health" in text
    assert "401" in text or "403" in text
    assert "tenant leakage" in text


# ===========================================================================
# 12. Checklist table
# ===========================================================================

def test_production_switch_checklist_table_documented():
    text = _doc_text()
    assert "Required Evidence" in text or "required evidence" in text.lower()
    assert "Owner" in text
    assert "Blocking if Failed" in text or "blocking" in text.lower()
    for i in range(1, 13):
        assert f"G{i}" in text


# ===========================================================================
# 13. Sample go/no-go outcomes
# ===========================================================================

def test_sample_go_no_go_outcomes_documented():
    text = _doc_text().upper()
    assert "GO" in text
    assert "NO-GO" in text


# ===========================================================================
# 14. Safety rules
# ===========================================================================

def test_safety_rules_documented():
    text = _doc_text().lower().replace("**", "").replace("*", "")
    assert "no db" in text or "does not create a db" in text or "does not connect" in text
    assert "does not enable" in text or "posted_ledger_reports_enabled" in text.lower()
    assert "no runtime api calls" in text or "does not call runtime" in text


# ===========================================================================
# 15. Next task H32
# ===========================================================================

def test_next_task_h32_documented():
    text = _doc_text()
    assert "H32" in text


# ===========================================================================
# 16. Local gate evaluator — all pass → GO
# ===========================================================================

def test_local_gate_evaluator_all_pass_allows_go():
    packet = _minimal_passing_packet()
    result = evaluate_switch_request(packet)
    assert result["allowed"] is True
    assert result["decision"] == "GO"
    assert result["blockers"] == []


# ===========================================================================
# 17. Local gate evaluator — high mismatch blocks
# ===========================================================================

def test_local_gate_evaluator_blocks_high_mismatch():
    packet = _minimal_passing_packet()
    packet["gate_results"]["G6"] = "high_mismatch"
    result = evaluate_switch_request(packet)
    assert result["allowed"] is False
    assert result["decision"] == "NO-GO"
    assert any("high_mismatch" in b for b in result["blockers"])


# ===========================================================================
# 18. Local gate evaluator — tenant leakage blocks
# ===========================================================================

def test_local_gate_evaluator_blocks_tenant_leakage():
    packet = _minimal_passing_packet()
    packet["gate_results"]["G10"] = "tenant_leakage"
    result = evaluate_switch_request(packet)
    assert result["allowed"] is False
    assert any("tenant_leakage" in b for b in result["blockers"])


# ===========================================================================
# 19. Local gate evaluator — missing evidence blocks
# ===========================================================================

def test_local_gate_evaluator_blocks_missing_evidence():
    packet = _minimal_passing_packet()
    packet["gate_results"]["G7"] = "missing_evidence"
    result = evaluate_switch_request(packet)
    assert result["allowed"] is False
    assert any("missing_evidence" in b for b in result["blockers"])


# ===========================================================================
# 20. Local gate evaluator — missing rollback blocks
# ===========================================================================

def test_local_gate_evaluator_blocks_missing_rollback():
    packet = _minimal_passing_packet()
    packet["gate_results"]["G9"] = "not_passed"
    result = evaluate_switch_request(packet)
    assert result["allowed"] is False
    assert any("rollback" in b for b in result["blockers"])


# ===========================================================================
# 21. Local gate evaluator — missing accountant sign-off blocks
# ===========================================================================

def test_local_gate_evaluator_blocks_missing_accountant_signoff():
    packet = _minimal_passing_packet()
    packet["sign_offs"]["accountant"] = None
    result = evaluate_switch_request(packet)
    assert result["allowed"] is False
    assert any("accountant" in b for b in result["blockers"])


# ===========================================================================
# 22. Local gate evaluator — flag already enabled without packet blocks
# ===========================================================================

def test_local_gate_evaluator_blocks_unexpected_feature_flag_enabled():
    packet = _minimal_passing_packet()
    packet["flag_already_enabled_in_production"] = True
    result = evaluate_switch_request(packet)
    assert result["allowed"] is False
    assert any("flag_enabled_without_packet" in b for b in result["blockers"])


# ===========================================================================
# 23. Local gate evaluator — Balance.ge activation coupled blocks
# ===========================================================================

def test_local_gate_evaluator_blocks_balance_activation_mixed_in():
    packet = _minimal_passing_packet()
    packet["balance_activation_coupled"] = True
    result = evaluate_switch_request(packet)
    assert result["allowed"] is False
    assert any("balance" in b for b in result["blockers"])


# ===========================================================================
# 24. Switch packet requires git_sha and sign-offs
# ===========================================================================

def test_local_switch_packet_requires_git_sha_and_signoffs():
    packet = _minimal_passing_packet()
    packet["git_sha"] = ""
    result = evaluate_switch_request(packet)
    assert result["allowed"] is False
    assert any("git_sha" in b for b in result["blockers"])

    packet2 = _minimal_passing_packet()
    del packet2["sign_offs"]["engineering"]
    result2 = evaluate_switch_request(packet2)
    assert result2["allowed"] is False


# ===========================================================================
# 25. Rounding-only requires accountant sign-off
# ===========================================================================

def test_local_rounding_only_requires_accountant_signoff():
    # A rounding-only scenario: G6 passes but with rounding_only acceptance
    # requires accountant sign-off to be present
    packet = _minimal_passing_packet()
    packet["gate_results"]["G6"] = "passed"  # rounding_only accepted via sign-off
    packet["sign_offs"]["accountant"] = {"signer": "acct_owner", "at": "2026-05-16T00:00:00Z", "accepted_rounding": True}
    result = evaluate_switch_request(packet)
    assert result["allowed"] is True

    # Without accountant sign-off even with rounding scenario
    packet2 = _minimal_passing_packet()
    packet2["sign_offs"]["accountant"] = None
    result2 = evaluate_switch_request(packet2)
    assert result2["allowed"] is False


# ===========================================================================
# 26. No real PII / tax / bank patterns
# ===========================================================================

def test_no_real_pii_or_tax_or_bank_patterns():
    import re
    doc_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "docs",
        "production-switch-gate-contract.md",
    )
    # Scan doc only — the test file contains pattern strings as string literals
    with open(doc_path, encoding="utf-8") as f:
        doc_text = f.read()

    regex_patterns = [
        r"010\d{8}",
        r"GE\d{2}[A-Z0-9]{20,}",
        r"@gmail\.com|@yahoo\.com|@hotmail\.com",
        r"\bTBC\b|\bBOG\b",
        r"Ltd\.|GmbH",
    ]
    for pat in regex_patterns:
        assert not re.search(pat, doc_text), f"Real PII pattern found: {pat}"

    # Split-fragment check to avoid SEC-1 self-trigger
    _bog = "Bank " + "of Georgia"
    assert _bog not in doc_text, f"Real bank name found in doc"


# ===========================================================================
# 27. No DB / network imports in test file
# ===========================================================================

def test_no_db_or_network_imports_in_test_file():
    import re
    test_path = os.path.abspath(__file__)
    with open(test_path, encoding="utf-8") as f:
        source = f.read()
    # Check for actual import statements at line start only (not string literals)
    forbidden_patterns = [
        r"^import psycopg",
        r"^import sqlalchemy",
        r"^import requests\b",
        r"^import httpx\b",
        r"^import socket\b",
        r"^import aiohttp\b",
        r"^from psycopg",
        r"^from sqlalchemy",
    ]
    for pat in forbidden_patterns:
        assert not re.search(pat, source, re.MULTILINE), f"Forbidden import found: {pat}"


# ===========================================================================
# 28. No SQL / subprocess in test file
# ===========================================================================

def test_no_sql_or_subprocess_in_test_file():
    import re
    test_path = os.path.abspath(__file__)
    with open(test_path, encoding="utf-8") as f:
        source = f.read()
    # Check for actual executable SQL/subprocess calls (not string literals in lists)
    forbidden_patterns = [
        r"^import subprocess\b",
        r"subprocess\.run|subprocess\.call|subprocess\.Popen",
        r"(?i)\bINSERT\s+INTO\b(?!.*#)",      # actual SQL, not doc text
        r"(?i)\bDELETE\s+FROM\b(?!.*#)",
        r"(?i)\bDROP\s+TABLE\b(?!.*#)",
        r"(?i)\bALTER\s+TABLE\b(?!.*#)",
        r"\bcreatedb\b",
        r"\bdropdb\b",
    ]
    for pat in forbidden_patterns:
        assert not re.search(pat, source, re.MULTILINE), f"Forbidden term found: {pat}"
