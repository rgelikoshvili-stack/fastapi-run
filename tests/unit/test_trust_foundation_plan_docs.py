"""Read-only tests for Trust Foundation Implementation Plan documents.

These tests verify that planning documents exist and contain the required content.
They do not import runtime app code, connect to a database, execute SQL, or
change any runtime behavior.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

PLAN_DOC = ROOT / "docs" / "trust-foundation-implementation-plan.md"
SEQUENCE_DOC = ROOT / "docs" / "trust-foundation-implementation-sequence.md"
GATE_DOC = ROOT / "docs" / "balance-ge-activation-gate.md"


def _plan() -> str:
    assert PLAN_DOC.exists(), "trust-foundation-implementation-plan.md is missing"
    return PLAN_DOC.read_text(encoding="utf-8")


def _sequence() -> str:
    assert SEQUENCE_DOC.exists(), "trust-foundation-implementation-sequence.md is missing"
    return SEQUENCE_DOC.read_text(encoding="utf-8")


def _gate() -> str:
    assert GATE_DOC.exists(), "balance-ge-activation-gate.md is missing"
    return GATE_DOC.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Document existence
# ---------------------------------------------------------------------------

def test_all_three_trust_foundation_docs_exist():
    assert PLAN_DOC.exists(), "trust-foundation-implementation-plan.md missing"
    assert SEQUENCE_DOC.exists(), "trust-foundation-implementation-sequence.md missing"
    assert GATE_DOC.exists(), "balance-ge-activation-gate.md missing"


# ---------------------------------------------------------------------------
# Plan doc: required pillars and keywords
# ---------------------------------------------------------------------------

def test_plan_doc_covers_credential_vault_and_encryption():
    text = _plan().lower()
    required = [
        "credential vault",
        "encrypted-at-rest",
        "encryption",
        "plaintext",
        "key management",
        "rotation",
        "masked reads",
    ]
    for phrase in required:
        assert phrase in text, f"plan doc missing: {phrase}"


def test_plan_doc_covers_masked_secret_reads():
    text = _plan().lower()
    required = [
        "masked secret reads",
        "masked reads",
        "never return",
        "configured",
        "not_configured",
        "last_test_status",
    ]
    for phrase in required:
        assert phrase in text, f"plan doc missing: {phrase}"


def test_plan_doc_covers_subscription_trial_enforcement():
    text = _plan().lower()
    required = [
        "subscription",
        "trial",
        "trial_ends_at",
        "enforcement",
        "suspended",
        "expired",
        "read-only mode",
        "402",
    ]
    for phrase in required:
        assert phrase in text, f"plan doc missing: {phrase}"


def test_plan_doc_covers_redis_rate_limiting():
    text = _plan().lower()
    required = [
        "redis",
        "redis_url",
        "rate limit",
        "in-memory",
        "multi-instance",
        "429",
    ]
    for phrase in required:
        assert phrase in text, f"plan doc missing: {phrase}"


def test_plan_doc_covers_runtime_ddl_cutover():
    text = _plan().lower()
    required = [
        "runtime ddl",
        "ensure_table",
        "ensure_inventory_tables",
        "ensure_payroll_erp_tables",
        "shim",
        "cutover",
        "no-op",
        "additive migration",
    ]
    for phrase in required:
        assert phrase in text, f"plan doc missing: {phrase}"


def test_plan_doc_covers_backup_and_pitr():
    text = _plan().lower()
    required = [
        "backup",
        "point-in-time recovery",
        "pitr",
        "restore drill",
        "pre-migration backup",
        "environment separation",
    ]
    for phrase in required:
        assert phrase in text, f"plan doc missing: {phrase}"


def test_plan_doc_covers_static_files_gcs_cdn():
    text = _plan().lower()
    required = [
        "static files",
        "gcs",
        "cdn",
        "cloud storage",
        "cache",
        "deployment",
    ]
    for phrase in required:
        assert phrase in text, f"plan doc missing: {phrase}"


def test_plan_doc_covers_evidence_bundle():
    text = _plan().lower()
    required = [
        "evidence bundle",
        "source document",
        "ai reasoning",
        "connector payload",
        "posting result",
        "audit trace",
    ]
    for phrase in required:
        assert phrase in text, f"plan doc missing: {phrase}"


def test_plan_doc_covers_balance_ge_activation_gate():
    text = _plan().lower()
    required = [
        "balance.ge activation gate",
        "activation gate",
        "dry-run",
        "dry run",
        "payload preview",
        "idempotency",
        "posting_logs",
        "encrypted credentials",
        "rollback",
        "manual fallback",
        "test tenant",
    ]
    for phrase in required:
        assert phrase in text, f"plan doc missing: {phrase}"


def test_plan_doc_explicitly_forbids_balance_ge_activation_in_this_task():
    text = _plan().lower()
    forbidden_check_phrases = [
        "do not activate balance.ge",
        "no balance.ge activation",
    ]
    assert any(p in text for p in forbidden_check_phrases), (
        "plan doc must explicitly forbid Balance.ge activation in this task"
    )


def test_plan_doc_explicitly_forbids_production_db_mutation():
    text = _plan().lower()
    forbidden_check_phrases = [
        "do not touch production database",
        "no production database mutation",
        "production database is not touched",
        "production db must not be touched",
    ]
    assert any(p in text for p in forbidden_check_phrases), (
        "plan doc must explicitly forbid production DB mutation"
    )


def test_plan_doc_explicitly_forbids_runtime_behavior_change():
    text = _plan().lower()
    forbidden_check_phrases = [
        "do not implement encryption",
        "do not activate balance.ge",
        "no auth behavior change",
        "no connector behavior change",
    ]
    assert any(p in text for p in forbidden_check_phrases), (
        "plan doc must explicitly forbid runtime behavior changes in this task"
    )


# ---------------------------------------------------------------------------
# Sequence doc: must define multiple micro-tasks
# ---------------------------------------------------------------------------

def test_sequence_doc_contains_multiple_micro_tasks():
    text = _sequence()
    task_ids = ["10F-A", "10F-B", "10F-C", "10F-D", "10F-E", "10F-F", "10F-G", "10F-H"]
    for task_id in task_ids:
        assert task_id in text, f"sequence doc missing micro-task: {task_id}"


def test_sequence_doc_references_implementation_tasks():
    text = _sequence()
    impl_tasks = ["11C-A", "11C-B", "11C-C", "11C-D", "11C-E", "11C-F"]
    for task_id in impl_tasks:
        assert task_id in text, f"sequence doc missing implementation task: {task_id}"


def test_sequence_doc_distinguishes_docs_only_from_code_editing():
    text = _sequence().lower()
    assert "docs/tests only" in text or "docs only" in text, (
        "sequence doc must distinguish docs-only tasks from code-editing tasks"
    )
    assert "code editing" in text, (
        "sequence doc must identify which tasks involve code editing"
    )


def test_sequence_doc_specifies_allowed_and_forbidden_files():
    text = _sequence().lower()
    assert "allowed files" in text, "sequence doc must specify allowed files per task"
    assert "forbidden files" in text, "sequence doc must specify forbidden files per task"


def test_sequence_doc_specifies_rollback_conditions():
    text = _sequence().lower()
    assert "rollback condition" in text, "sequence doc must specify rollback conditions"


# ---------------------------------------------------------------------------
# Balance.ge gate doc: must cover all required conditions
# ---------------------------------------------------------------------------

def test_gate_doc_requires_approval_before_execution():
    text = _gate().lower()
    required = [
        "approval",
        "approved draft",
        "approve",
    ]
    for phrase in required:
        assert phrase in text, f"gate doc missing: {phrase}"


def test_gate_doc_requires_dry_run():
    text = _gate().lower()
    assert "dry-run" in text or "dry run" in text, "gate doc must require dry-run verification"


def test_gate_doc_requires_payload_preview():
    text = _gate().lower()
    assert "payload preview" in text, "gate doc must require payload preview"


def test_gate_doc_requires_idempotency():
    text = _gate().lower()
    assert "idempotency" in text, "gate doc must require idempotency verification"


def test_gate_doc_requires_posting_logs():
    text = _gate().lower()
    assert "posting_logs" in text or "posting logs" in text, (
        "gate doc must require posting logs"
    )


def test_gate_doc_requires_encrypted_credentials():
    text = _gate().lower()
    assert "encrypt" in text, "gate doc must require encrypted credentials"


def test_gate_doc_requires_rollback_and_manual_fallback():
    text = _gate().lower()
    assert "rollback" in text, "gate doc must require rollback condition"
    assert "manual fallback" in text, "gate doc must require manual fallback"


def test_gate_doc_requires_test_tenant():
    text = _gate().lower()
    assert "test tenant" in text, "gate doc must require test tenant verification"


def test_gate_doc_requires_accountant_review():
    text = _gate().lower()
    assert "accountant" in text, "gate doc must require accountant review"


def test_gate_doc_has_all_twelve_gate_criteria():
    text = _gate()
    gates = [
        "Gate 1",
        "Gate 2",
        "Gate 3",
        "Gate 4",
        "Gate 5",
        "Gate 6",
        "Gate 7",
        "Gate 8",
        "Gate 9",
        "Gate 10",
        "Gate 11",
        "Gate 12",
    ]
    for gate in gates:
        assert gate in text, f"gate doc missing: {gate}"


def test_gate_doc_explicitly_states_all_gates_must_be_met():
    text = _gate().lower()
    assert "all 12 gates" in text or "all twelve gates" in text or "all 12 gate" in text, (
        "gate doc must state that all 12 gates must be met before activation"
    )


def test_gate_doc_current_state_is_not_met():
    text = _gate()
    assert "NOT MET" in text, "gate doc must document that current state is NOT MET"
    assert "DEMO" in text, "gate doc must confirm Balance.ge is currently in DEMO mode"
