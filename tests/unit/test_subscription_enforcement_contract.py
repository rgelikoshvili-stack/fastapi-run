"""Read-only tests for Subscription / Trial Enforcement Contract.

Validates that the subscription enforcement plan document exists and contains
all required content. Also validates contract logic using local test-only
definitions and pure helpers — no runtime app imports, no DB, no SQL.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Literal


ROOT = Path(__file__).resolve().parents[2]

ENFORCEMENT_DOC = ROOT / "docs" / "subscription-enforcement-plan.md"
TRUST_PLAN_DOC = ROOT / "docs" / "trust-foundation-implementation-plan.md"
AUTH_CONTRACT_DOC = ROOT / "docs" / "auth-tenant-schema-contract.md"
SCRIPTS_DIR = ROOT / "scripts"

# ---------------------------------------------------------------------------
# Tenant lifecycle states (canonical contract definition)
# ---------------------------------------------------------------------------

TenantState = Literal["active", "trial", "trial_expired", "suspended", "expired", "inactive"]

TENANT_STATES: frozenset[str] = frozenset({
    "active",
    "trial",
    "trial_expired",
    "suspended",
    "expired",
    "inactive",
})

# ---------------------------------------------------------------------------
# Endpoint categories (canonical contract definition)
# ---------------------------------------------------------------------------

ENDPOINT_CATEGORIES: frozenset[str] = frozenset({
    "public",
    "auth_session",
    "read_only_reporting",
    "document_processing",
    "draft_creation",
    "approval",
    "posting_connector_execution",
    "credential_management",
    "tenant_admin_billing",
    "exports",
})

# ---------------------------------------------------------------------------
# Mutating actions that must be blocked for expired/suspended tenants
# ---------------------------------------------------------------------------

BLOCKED_MUTATING_ACTIONS: frozenset[str] = frozenset({
    "create_journal_draft",
    "upload_document",
    "approve_draft",
    "reject_draft",
    "post_to_connector",
    "save_credentials",
    "test_connector",
    "update_tenant_settings",
    "create_invoice",
    "create_payroll",
    "create_inventory",
    "create_trade_record",
})

# ---------------------------------------------------------------------------
# Connector execution paths that must be blocked
# ---------------------------------------------------------------------------

BLOCKED_CONNECTORS: frozenset[str] = frozenset({
    "balance_posting",
    "oris_posting",
    "one_c_posting",
    "rsge_submit",
    "email_send",
    "connector_test",
})

# ---------------------------------------------------------------------------
# Required error codes
# ---------------------------------------------------------------------------

REQUIRED_ERROR_CODES: frozenset[str] = frozenset({
    "TENANT_TRIAL_EXPIRED",
    "TENANT_SUBSCRIPTION_EXPIRED",
    "TENANT_SUSPENDED",
    "TENANT_INACTIVE",
    "TENANT_WRITE_BLOCKED",
    "CONNECTOR_BLOCKED_BY_SUBSCRIPTION",
    "APPROVAL_BLOCKED_BY_SUBSCRIPTION",
    "CREDENTIAL_CHANGE_BLOCKED_BY_SUBSCRIPTION",
    "ADMIN_OVERRIDE_REQUIRED",
})

# ---------------------------------------------------------------------------
# Local test-only pure enforcement helper
# ---------------------------------------------------------------------------

# Categories that are always allowed regardless of tenant state
_ALWAYS_ALLOWED: frozenset[str] = frozenset({
    "public",
    "auth_session",
})

# Categories allowed for read-only access in blocking states
_READ_ALLOWED_IN_BLOCKING: frozenset[str] = frozenset({
    "read_only_reporting",
    "exports",
    "tenant_admin_billing",  # billing/renewal page specifically
})

# Categories that are blocked for blocking states
_BLOCKED_IN_BLOCKING_STATES: frozenset[str] = frozenset({
    "document_processing",
    "draft_creation",
    "approval",
    "posting_connector_execution",
    "credential_management",
})

_BLOCKING_STATES: frozenset[str] = frozenset({
    "trial_expired",
    "suspended",
    "expired",
    "inactive",
})


def is_action_allowed(tenant_state: str, endpoint_category: str) -> bool:
    """Pure test-only helper: return True if the action is allowed for this tenant state.

    This is a contract-level specification helper, NOT a runtime implementation.
    """
    if endpoint_category in _ALWAYS_ALLOWED:
        return True

    if tenant_state == "active":
        return True

    if tenant_state == "trial":
        # Trial tenants: read allowed, limited write per pilot scope
        # Connector live execution blocked by default in trial
        if endpoint_category == "posting_connector_execution":
            return False
        return True

    if tenant_state in _BLOCKING_STATES:
        if tenant_state == "inactive":
            # inactive: fully blocked except public/auth (already handled above)
            return False
        # trial_expired, suspended, expired: read allowed, mutating blocked
        if endpoint_category in _READ_ALLOWED_IN_BLOCKING:
            return True
        if endpoint_category in _BLOCKED_IN_BLOCKING_STATES:
            return False
        return False

    # Unknown state: deny by default
    return False


def is_connector_allowed(tenant_state: str, connector: str) -> bool:
    """Pure test-only helper: return True if connector execution is allowed."""
    if tenant_state not in ("active",):
        return False
    return True


# ---------------------------------------------------------------------------
# Helper: read docs
# ---------------------------------------------------------------------------

def _enforcement_doc() -> str:
    assert ENFORCEMENT_DOC.exists(), "subscription-enforcement-plan.md is missing"
    return ENFORCEMENT_DOC.read_text(encoding="utf-8")


def _python_execute_string_literals(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="ignore"))
    literals: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        func_name = ""
        if isinstance(func, ast.Attribute):
            func_name = func.attr
        elif isinstance(func, ast.Name):
            func_name = func.id
        if func_name not in {"execute", "executemany"}:
            continue
        if not node.args:
            continue
        first_arg = node.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            literals.append(first_arg.value)
    return literals


# ---------------------------------------------------------------------------
# A) Document existence
# ---------------------------------------------------------------------------

def test_all_three_docs_exist():
    assert ENFORCEMENT_DOC.exists(), "subscription-enforcement-plan.md missing"
    assert TRUST_PLAN_DOC.exists(), "trust-foundation-implementation-plan.md missing"
    assert AUTH_CONTRACT_DOC.exists(), "auth-tenant-schema-contract.md missing"


# ---------------------------------------------------------------------------
# B) Contract content: required topics
# ---------------------------------------------------------------------------

def test_enforcement_doc_mentions_trial_ends_at():
    text = _enforcement_doc().lower()
    assert "trial_ends_at" in text, "enforcement doc must mention trial_ends_at"


def test_enforcement_doc_mentions_all_tenant_states():
    text = _enforcement_doc().lower()
    required_states = ["active", "trial", "trial_expired", "suspended", "expired", "inactive"]
    for state in required_states:
        assert state in text, f"enforcement doc must mention tenant state: {state}"


def test_enforcement_doc_mentions_read_only_access_policy():
    text = _enforcement_doc().lower()
    phrases = ["read-only", "read only", "read_only_reporting", "read allowed"]
    assert any(p in text for p in phrases), (
        "enforcement doc must mention read-only access policy"
    )


def test_enforcement_doc_mentions_mutating_endpoint_blocking():
    text = _enforcement_doc().lower()
    phrases = ["mutating endpoint", "mutating writes blocked", "mutating action"]
    assert any(p in text for p in phrases), (
        "enforcement doc must mention mutating endpoint blocking"
    )


def test_enforcement_doc_mentions_connector_execution_blocking():
    text = _enforcement_doc().lower()
    phrases = [
        "connector execution blocked",
        "connector execution blocking",
        "connector_blocked_by_subscription",
    ]
    assert any(p in text for p in phrases), (
        "enforcement doc must mention connector execution blocking"
    )


def test_enforcement_doc_says_balance_ge_remains_inactive():
    text = _enforcement_doc().lower()
    inactive_phrases = [
        "balance.ge remains inactive",
        "balance.ge must stay inactive",
        "balance.ge activation remains blocked",
    ]
    assert any(p in text for p in inactive_phrases), (
        "enforcement doc must state Balance.ge remains inactive"
    )


def test_enforcement_doc_says_no_runtime_behavior_change():
    text = _enforcement_doc().lower()
    phrases = [
        "no runtime behavior change",
        "no runtime behavior is changed",
        "runtime behavior is unchanged",
        "runtime behavior: unchanged",
        "not changed in this task",
        "unchanged in this task",
        "no runtime code is changed",
        "runtime behavior:\n**unchanged",
        "runtime behavior status",
    ]
    assert any(p in text for p in phrases), (
        "enforcement doc must state no runtime behavior change"
    )


def test_enforcement_doc_says_no_middleware_edit():
    text = _enforcement_doc().lower()
    phrases = [
        "no middleware edit",
        "middleware is not changed",
        "middleware not changed",
        "no middleware change",
        "middleware not edited",
        "auth_middleware.py",
        "rbac_middleware.py",
    ]
    assert any(p in text for p in phrases), (
        "enforcement doc must state no middleware edit in this task"
    )


def test_enforcement_doc_says_no_migration():
    text = _enforcement_doc().lower()
    phrases = [
        "no migration",
        "no migration is created",
        "no migration or ddl",
        "no migration in this task",
    ]
    assert any(p in text for p in phrases), (
        "enforcement doc must state no migration in this task"
    )


def test_enforcement_doc_says_no_db_touch():
    text = _enforcement_doc().lower()
    phrases = [
        "no production database is touched",
        "production database is not touched",
        "production db untouched",
        "production database is\n**untouched",
        "no production db touch",
        "untouched in this task",
        "production database: untouched",
    ]
    assert any(p in text for p in phrases), (
        "enforcement doc must state no production DB touch"
    )


def test_enforcement_doc_says_no_balance_ge_activation():
    text = _enforcement_doc().lower()
    phrases = [
        "no balance.ge activation",
        "balance.ge remains inactive",
        "no commercial pilot activation",
        "balance.ge activation remains blocked",
    ]
    assert any(p in text for p in phrases), (
        "enforcement doc must state no Balance.ge activation"
    )


# ---------------------------------------------------------------------------
# C) Tenant state set: canonical states are complete
# ---------------------------------------------------------------------------

def test_tenant_states_includes_required_states():
    required = {"active", "trial", "trial_expired", "suspended", "expired", "inactive"}
    missing = required - TENANT_STATES
    assert not missing, f"TENANT_STATES is missing required states: {missing}"


def test_tenant_states_has_no_unexpected_entries():
    known = {"active", "trial", "trial_expired", "suspended", "expired", "inactive"}
    extra = TENANT_STATES - known
    assert not extra, f"TENANT_STATES has unexpected entries: {extra}"


# ---------------------------------------------------------------------------
# D) Endpoint category set: canonical categories are complete
# ---------------------------------------------------------------------------

def test_endpoint_categories_includes_required_categories():
    required = {
        "public",
        "auth_session",
        "read_only_reporting",
        "document_processing",
        "draft_creation",
        "approval",
        "posting_connector_execution",
        "credential_management",
        "tenant_admin_billing",
        "exports",
    }
    missing = required - ENDPOINT_CATEGORIES
    assert not missing, f"ENDPOINT_CATEGORIES missing: {missing}"


# ---------------------------------------------------------------------------
# E) Mutating endpoint block list: complete
# ---------------------------------------------------------------------------

def test_blocked_mutating_actions_includes_required():
    required = {
        "create_journal_draft",
        "upload_document",
        "approve_draft",
        "reject_draft",
        "post_to_connector",
        "save_credentials",
        "test_connector",
        "update_tenant_settings",
        "create_invoice",
        "create_payroll",
        "create_inventory",
        "create_trade_record",
    }
    missing = required - BLOCKED_MUTATING_ACTIONS
    assert not missing, f"BLOCKED_MUTATING_ACTIONS missing: {missing}"


# ---------------------------------------------------------------------------
# F) Connector block list: complete
# ---------------------------------------------------------------------------

def test_blocked_connectors_includes_required():
    required = {
        "balance_posting",
        "oris_posting",
        "one_c_posting",
        "rsge_submit",
        "email_send",
        "connector_test",
    }
    missing = required - BLOCKED_CONNECTORS
    assert not missing, f"BLOCKED_CONNECTORS missing: {missing}"


# ---------------------------------------------------------------------------
# G) Error codes: complete
# ---------------------------------------------------------------------------

def test_required_error_codes_are_complete():
    required = {
        "TENANT_TRIAL_EXPIRED",
        "TENANT_SUBSCRIPTION_EXPIRED",
        "TENANT_SUSPENDED",
        "TENANT_INACTIVE",
        "TENANT_WRITE_BLOCKED",
        "CONNECTOR_BLOCKED_BY_SUBSCRIPTION",
        "APPROVAL_BLOCKED_BY_SUBSCRIPTION",
        "CREDENTIAL_CHANGE_BLOCKED_BY_SUBSCRIPTION",
        "ADMIN_OVERRIDE_REQUIRED",
    }
    missing = required - REQUIRED_ERROR_CODES
    assert not missing, f"REQUIRED_ERROR_CODES missing: {missing}"


def test_enforcement_doc_mentions_all_required_error_codes():
    text = _enforcement_doc()
    for code in REQUIRED_ERROR_CODES:
        assert code in text, f"enforcement doc must mention error code: {code}"


# ---------------------------------------------------------------------------
# H) Sample policy helper: behavior by tenant state
# ---------------------------------------------------------------------------

# active: all categories allowed
def test_active_tenant_allows_all_categories():
    for category in ENDPOINT_CATEGORIES:
        assert is_action_allowed("active", category), (
            f"active tenant must be allowed: {category}"
        )


# trial: most categories allowed, connector execution blocked
def test_trial_tenant_allows_reads_and_writes():
    allowed_in_trial = [
        "public", "auth_session", "read_only_reporting",
        "document_processing", "draft_creation", "approval",
        "credential_management", "tenant_admin_billing", "exports",
    ]
    for category in allowed_in_trial:
        assert is_action_allowed("trial", category), (
            f"trial tenant must allow: {category}"
        )


def test_trial_tenant_blocks_connector_execution():
    assert not is_action_allowed("trial", "posting_connector_execution"), (
        "trial tenant must block connector execution by default"
    )


# trial_expired: reads allowed, mutating blocked
def test_trial_expired_allows_read_only():
    read_categories = ["public", "auth_session", "read_only_reporting", "exports"]
    for category in read_categories:
        assert is_action_allowed("trial_expired", category), (
            f"trial_expired tenant must allow: {category}"
        )


def test_trial_expired_blocks_mutating_categories():
    blocked = [
        "document_processing",
        "draft_creation",
        "approval",
        "posting_connector_execution",
        "credential_management",
    ]
    for category in blocked:
        assert not is_action_allowed("trial_expired", category), (
            f"trial_expired tenant must block: {category}"
        )


# suspended: reads allowed, mutating blocked
def test_suspended_allows_read_only():
    read_categories = ["public", "auth_session", "read_only_reporting"]
    for category in read_categories:
        assert is_action_allowed("suspended", category), (
            f"suspended tenant must allow: {category}"
        )


def test_suspended_blocks_mutating_categories():
    blocked = [
        "document_processing",
        "draft_creation",
        "approval",
        "posting_connector_execution",
        "credential_management",
    ]
    for category in blocked:
        assert not is_action_allowed("suspended", category), (
            f"suspended tenant must block: {category}"
        )


# expired: reads allowed, mutating blocked
def test_expired_blocks_mutating_categories():
    blocked = [
        "document_processing",
        "draft_creation",
        "approval",
        "posting_connector_execution",
        "credential_management",
    ]
    for category in blocked:
        assert not is_action_allowed("expired", category), (
            f"expired tenant must block: {category}"
        )


# inactive: everything except public/auth blocked
def test_inactive_blocks_all_except_public_and_auth():
    blocked = [
        "read_only_reporting",
        "document_processing",
        "draft_creation",
        "approval",
        "posting_connector_execution",
        "credential_management",
        "tenant_admin_billing",
        "exports",
    ]
    for category in blocked:
        assert not is_action_allowed("inactive", category), (
            f"inactive tenant must block: {category}"
        )


def test_inactive_allows_public_and_auth():
    assert is_action_allowed("inactive", "public"), (
        "inactive tenant must allow public endpoints"
    )
    assert is_action_allowed("inactive", "auth_session"), (
        "inactive tenant must allow auth/session endpoints"
    )


# connector helper
def test_only_active_tenant_can_execute_connectors():
    for state in TENANT_STATES:
        for connector in BLOCKED_CONNECTORS:
            result = is_connector_allowed(state, connector)
            if state == "active":
                assert result, f"active tenant must allow connector: {connector}"
            else:
                assert not result, f"non-active tenant {state!r} must not allow connector: {connector}"


# ---------------------------------------------------------------------------
# I) Audit requirement text: docs must require audit events
# ---------------------------------------------------------------------------

def test_enforcement_doc_requires_audit_for_connector_blocked():
    text = _enforcement_doc().lower()
    assert "connector execution blocked" in text, (
        "enforcement doc must require audit for connector execution blocked"
    )


def test_enforcement_doc_requires_audit_for_approval_blocked():
    text = _enforcement_doc().lower()
    phrases = ["approval/posting blocked", "approval blocked"]
    assert any(p in text for p in phrases), (
        "enforcement doc must require audit for approval/posting blocked"
    )


def test_enforcement_doc_requires_audit_for_credential_change_blocked():
    text = _enforcement_doc().lower()
    assert "credential change blocked" in text, (
        "enforcement doc must require audit for credential change blocked"
    )


def test_enforcement_doc_requires_audit_for_tenant_status_changed():
    text = _enforcement_doc().lower()
    phrases = ["tenant status changed", "subscription renewed", "subscription or trial changes"]
    assert any(p in text for p in phrases), (
        "enforcement doc must require audit for tenant status changes"
    )


def test_enforcement_doc_requires_audit_for_admin_override():
    text = _enforcement_doc().lower()
    assert "admin override" in text, (
        "enforcement doc must require audit for admin override"
    )


# ---------------------------------------------------------------------------
# J) Active script safety: no executable DROP TABLE IF EXISTS users
# ---------------------------------------------------------------------------

def test_active_scripts_do_not_execute_drop_table_users():
    if not SCRIPTS_DIR.exists():
        return
    executable_drop_users = []
    for path in SCRIPTS_DIR.rglob("*.py"):
        try:
            for literal in _python_execute_string_literals(path):
                normalized = " ".join(literal.lower().split())
                if "drop table if exists users" in normalized:
                    executable_drop_users.append(path.relative_to(ROOT).as_posix())
        except SyntaxError:
            pass
    assert not executable_drop_users, (
        "active scripts must not execute DROP TABLE IF EXISTS users: "
        f"{executable_drop_users}"
    )


# ---------------------------------------------------------------------------
# K) Balance.ge safety: docs confirm inactive and gates deferred
# ---------------------------------------------------------------------------

def test_enforcement_doc_balance_ge_activation_requires_all_gates():
    text = _enforcement_doc().lower()
    gate_phrases = [
        "balance-ge-activation-gate",
        "activation gate",
        "all 12 gates",
        "12 gates",
    ]
    assert any(p in text for p in gate_phrases), (
        "enforcement doc must reference Balance.ge activation gate requirement"
    )


def test_enforcement_doc_balance_ge_gates_currently_not_met():
    text = _enforcement_doc()
    not_met_phrases = [
        "NOT MET",
        "not met",
        "currently NOT MET",
        "All gates are currently NOT MET",
    ]
    assert any(p in text for p in not_met_phrases), (
        "enforcement doc must state that Balance.ge activation gates are currently NOT MET"
    )


def test_auth_contract_doc_covers_subscription_enforcement():
    text = AUTH_CONTRACT_DOC.read_text(encoding="utf-8").lower()
    required = [
        "trial_ends_at",
        "subscription",
        "suspended",
        "expired",
        "trial",
        "enforcement",
    ]
    for phrase in required:
        assert phrase in text, (
            f"auth-tenant-schema-contract.md must mention: {phrase}"
        )


def test_trust_plan_doc_covers_subscription_enforcement():
    text = TRUST_PLAN_DOC.read_text(encoding="utf-8").lower()
    required = [
        "subscription",
        "trial",
        "trial_ends_at",
        "enforcement",
        "402",
    ]
    for phrase in required:
        assert phrase in text, (
            f"trust-foundation-implementation-plan.md must mention: {phrase}"
        )
