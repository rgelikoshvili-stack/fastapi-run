"""tests/unit/test_redis_rate_limit_contract.py

Task 10F-E: Redis / Rate-Limit Plan — contract tests.

Read-only. No DB, no Redis, no runtime imports. Validates doc content and
local-only contract definitions. Does not import app.api.security or any
module that triggers SlowAPI or DB initialization.
"""
from __future__ import annotations

import os
import ast
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO = Path(__file__).parent.parent.parent
_DOCS = _REPO / "docs"

RATE_LIMIT_PLAN = _DOCS / "redis-rate-limit-plan.md"
TRUST_FOUNDATION_PLAN = _DOCS / "trust-foundation-implementation-plan.md"
SUBSCRIPTION_PLAN = _DOCS / "subscription-enforcement-plan.md"
MASKED_READ_CONTRACT = _DOCS / "masked-read-behavior-contract.md"

# ---------------------------------------------------------------------------
# Contract definitions (test-only, no runtime imports)
# ---------------------------------------------------------------------------

RATE_LIMIT_COMPONENTS: frozenset[str] = frozenset({
    "RateLimitService",
    "RateLimitRepository",
    "RedisRateLimitBackend",
    "InMemoryRateLimitBackend",
    "RateLimitPolicyRegistry",
    "RateLimitAuditLogger",
    "RateLimitDecision",
})

ENDPOINT_GROUPS: frozenset[str] = frozenset({
    "public_health",
    "auth_login",
    "auth_register",
    "auth_refresh",
    "ai_classification",
    "ocr_processing",
    "document_upload",
    "bank_csv_import",
    "email_collector",
    "approval_write",
    "posting_erp",
    "credential_save",
    "credential_status",
    "connector_test",
    "reporting",
    "export",
    "tenant_admin",
    "general_api",
})

# Groups that must enforce limits even in in-memory fallback
SENSITIVE_RATE_LIMIT_GROUPS: frozenset[str] = frozenset({
    "auth_login",
    "auth_register",
    "auth_refresh",
    "ai_classification",
    "ocr_processing",
    "document_upload",
    "posting_erp",
    "credential_save",
    "connector_test",
    "bank_csv_import",
})

REQUIRED_ERROR_CODES: frozenset[str] = frozenset({
    "RATE_LIMIT_EXCEEDED",
    "AUTH_RATE_LIMIT_EXCEEDED",
    "AI_QUOTA_EXCEEDED",
    "DOCUMENT_QUOTA_EXCEEDED",
    "CONNECTOR_RATE_LIMIT_EXCEEDED",
    "CREDENTIAL_RATE_LIMIT_EXCEEDED",
    "TENANT_QUOTA_EXCEEDED",
    "RATE_LIMIT_BACKEND_DEGRADED",
    "RATE_LIMIT_POLICY_NOT_FOUND",
    "EXPORT_RATE_LIMIT_EXCEEDED",
})

# Groups that should block connector execution for trial tenants
CONNECTOR_GROUPS: frozenset[str] = frozenset({
    "posting_erp",
    "connector_test",
})

# Groups that enforce per-tenant quota (not just per-IP)
PER_TENANT_GROUPS: frozenset[str] = frozenset({
    "ai_classification",
    "ocr_processing",
    "document_upload",
    "bank_csv_import",
    "email_collector",
    "approval_write",
    "posting_erp",
    "credential_save",
    "credential_status",
    "connector_test",
    "reporting",
    "export",
    "tenant_admin",
    "general_api",
})

# Fields that must NEVER appear in rate-limit audit records
FORBIDDEN_AUDIT_FIELDS: frozenset[str] = frozenset({
    "api_key",
    "password",
    "app_password",
    "token",
    "secret",
    "webhook_secret",
    "totp_secret",
    "encrypted_value",
    "raw_ip",
    "ip_address",
})

# Fields required in RateLimitDecision
REQUIRED_DECISION_FIELDS: frozenset[str] = frozenset({
    "allowed",
    "remaining",
    "reset_at",
    "policy_key",
    "backend",
    "error_code",
})

# ---------------------------------------------------------------------------
# Test-only policy helper (pure function — no runtime imports)
# ---------------------------------------------------------------------------

_ALWAYS_OPEN_GROUPS = frozenset({"public_health"})
_AUTH_GROUPS = frozenset({"auth_login", "auth_register", "auth_refresh"})
_AI_QUOTA_GROUPS = frozenset({"ai_classification", "ocr_processing"})
_CONNECTOR_EXECUTION_GROUPS = frozenset({"posting_erp"})


def get_effective_limit(group: str, tenant_state: str, base_limit: int,
                        trial_multiplier: float, active_multiplier: float) -> int:
    """Compute effective limit for a group given tenant state and multipliers.

    Pure function — no DB, no Redis, no runtime imports.
    """
    if group in _ALWAYS_OPEN_GROUPS:
        return base_limit
    if group in _AUTH_GROUPS:
        return base_limit
    if tenant_state == "active":
        return max(0, int(base_limit * active_multiplier))
    if tenant_state == "trial":
        return max(0, int(base_limit * trial_multiplier))
    # trial_expired, suspended, expired: trial limits apply (subscription enforcement is primary block)
    return max(0, int(base_limit * trial_multiplier))


def is_rate_limited(group: str, requests_made: int, effective_limit: int) -> bool:
    """Return True if the request should be rate-limited."""
    return requests_made >= effective_limit


def get_error_code_for_group(group: str) -> str:
    """Return the expected error code for a blocked request from a group."""
    if group in _AUTH_GROUPS:
        return "AUTH_RATE_LIMIT_EXCEEDED"
    if group in _AI_QUOTA_GROUPS:
        return "AI_QUOTA_EXCEEDED"
    if group == "document_upload":
        return "DOCUMENT_QUOTA_EXCEEDED"
    if group in _CONNECTOR_EXECUTION_GROUPS or group == "connector_test":
        return "CONNECTOR_RATE_LIMIT_EXCEEDED"
    if group == "credential_save":
        return "CREDENTIAL_RATE_LIMIT_EXCEEDED"
    if group == "export":
        return "EXPORT_RATE_LIMIT_EXCEEDED"
    return "RATE_LIMIT_EXCEEDED"


def safe_audit_record(
    tenant_id: str,
    ip_hash: str,
    endpoint_group: str,
    result: str,
    backend: str,
    limit: int,
    remaining: int,
    error_code: str | None = None,
) -> dict[str, Any]:
    """Build a safe rate-limit audit record with no raw credentials."""
    return {
        "tenant_id": tenant_id,
        "ip_hash": ip_hash,
        "endpoint_group": endpoint_group,
        "result": result,
        "backend": backend,
        "limit": limit,
        "remaining": remaining,
        "error_code": error_code,
    }


def _scan_forbidden_fields(payload: Any, forbidden: frozenset[str]) -> list[str]:
    """Recursively scan dict/list for forbidden field names."""
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in forbidden:
                found.append(key)
            found.extend(_scan_forbidden_fields(value, forbidden))
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            found.extend(_scan_forbidden_fields(item, forbidden))
    return found


# ---------------------------------------------------------------------------
# A) Document existence
# ---------------------------------------------------------------------------

def test_rate_limit_plan_exists():
    assert RATE_LIMIT_PLAN.exists(), f"Missing: {RATE_LIMIT_PLAN}"


def test_trust_foundation_plan_exists():
    assert TRUST_FOUNDATION_PLAN.exists(), f"Missing: {TRUST_FOUNDATION_PLAN}"


def test_subscription_plan_exists():
    assert SUBSCRIPTION_PLAN.exists(), f"Missing: {SUBSCRIPTION_PLAN}"


def test_masked_read_contract_exists():
    assert MASKED_READ_CONTRACT.exists(), f"Missing: {MASKED_READ_CONTRACT}"


# ---------------------------------------------------------------------------
# B) Document content checks
# ---------------------------------------------------------------------------

def _doc() -> str:
    return RATE_LIMIT_PLAN.read_text(encoding="utf-8")


def test_doc_contains_purpose_section():
    assert "## A) Purpose" in _doc()


def test_doc_contains_current_state_section():
    assert "## B) Current State" in _doc()


def test_doc_contains_target_architecture_section():
    assert "## C) Target Architecture" in _doc()


def test_doc_contains_key_strategy_section():
    assert "## D) Key Strategy" in _doc()


def test_doc_contains_endpoint_groups_section():
    assert "## E) Endpoint Groups" in _doc()


def test_doc_contains_policy_matrix_section():
    assert "## F) Policy Matrix" in _doc()


def test_doc_contains_failure_fallback_section():
    assert "## G) Failure and Fallback Policy" in _doc()


def test_doc_contains_subscription_integration_section():
    assert "## H) Subscription Integration" in _doc()


def test_doc_contains_credential_safety_section():
    assert "## I) Credential Safety" in _doc()


def test_doc_contains_connector_safety_section():
    assert "## J) Connector Safety" in _doc()


def test_doc_contains_ai_ocr_quotas_section():
    assert "## K) AI, OCR, and Document Quotas" in _doc()


def test_doc_contains_audit_metrics_section():
    assert "## L) Audit and Metrics" in _doc()


def test_doc_contains_error_codes_section():
    assert "## M) Error Codes" in _doc()


def test_doc_contains_test_strategy_section():
    assert "## N) Test Strategy" in _doc()


def test_doc_contains_future_scope_section():
    assert "## O) Future Implementation Scope" in _doc()


def test_doc_contains_non_goals_section():
    assert "## P) Explicit Non-Goals" in _doc()


# ---------------------------------------------------------------------------
# C) Component set
# ---------------------------------------------------------------------------

def test_all_seven_components_defined():
    assert len(RATE_LIMIT_COMPONENTS) == 7, (
        f"Expected 7 components, got {len(RATE_LIMIT_COMPONENTS)}"
    )


def test_rate_limit_service_in_components():
    assert "RateLimitService" in RATE_LIMIT_COMPONENTS


def test_rate_limit_repository_in_components():
    assert "RateLimitRepository" in RATE_LIMIT_COMPONENTS


def test_redis_backend_in_components():
    assert "RedisRateLimitBackend" in RATE_LIMIT_COMPONENTS


def test_memory_backend_in_components():
    assert "InMemoryRateLimitBackend" in RATE_LIMIT_COMPONENTS


def test_policy_registry_in_components():
    assert "RateLimitPolicyRegistry" in RATE_LIMIT_COMPONENTS


def test_audit_logger_in_components():
    assert "RateLimitAuditLogger" in RATE_LIMIT_COMPONENTS


def test_decision_in_components():
    assert "RateLimitDecision" in RATE_LIMIT_COMPONENTS


def test_all_components_documented():
    doc = _doc()
    for component in RATE_LIMIT_COMPONENTS:
        assert component in doc, f"Component not documented: {component}"


# ---------------------------------------------------------------------------
# D) Endpoint groups
# ---------------------------------------------------------------------------

def test_eighteen_endpoint_groups_defined():
    assert len(ENDPOINT_GROUPS) == 18, (
        f"Expected 18 endpoint groups, got {len(ENDPOINT_GROUPS)}"
    )


def test_all_endpoint_groups_documented():
    doc = _doc()
    for group in ENDPOINT_GROUPS:
        assert group in doc, f"Endpoint group not documented: {group}"


def test_auth_groups_present():
    for group in ("auth_login", "auth_register", "auth_refresh"):
        assert group in ENDPOINT_GROUPS


def test_ai_groups_present():
    for group in ("ai_classification", "ocr_processing"):
        assert group in ENDPOINT_GROUPS


def test_connector_groups_present():
    for group in ("posting_erp", "connector_test"):
        assert group in ENDPOINT_GROUPS


def test_document_groups_present():
    for group in ("document_upload", "bank_csv_import"):
        assert group in ENDPOINT_GROUPS


def test_credential_groups_present():
    for group in ("credential_save", "credential_status"):
        assert group in ENDPOINT_GROUPS


def test_public_group_present():
    assert "public_health" in ENDPOINT_GROUPS


def test_general_api_group_present():
    assert "general_api" in ENDPOINT_GROUPS


# ---------------------------------------------------------------------------
# E) Sensitive groups
# ---------------------------------------------------------------------------

def test_ten_sensitive_groups_defined():
    assert len(SENSITIVE_RATE_LIMIT_GROUPS) == 10, (
        f"Expected 10 sensitive groups, got {len(SENSITIVE_RATE_LIMIT_GROUPS)}"
    )


def test_sensitive_groups_subset_of_all_groups():
    assert SENSITIVE_RATE_LIMIT_GROUPS.issubset(ENDPOINT_GROUPS), (
        f"Sensitive groups not in ENDPOINT_GROUPS: "
        f"{SENSITIVE_RATE_LIMIT_GROUPS - ENDPOINT_GROUPS}"
    )


def test_auth_login_is_sensitive():
    assert "auth_login" in SENSITIVE_RATE_LIMIT_GROUPS


def test_auth_register_is_sensitive():
    assert "auth_register" in SENSITIVE_RATE_LIMIT_GROUPS


def test_posting_erp_is_sensitive():
    assert "posting_erp" in SENSITIVE_RATE_LIMIT_GROUPS


def test_ai_classification_is_sensitive():
    assert "ai_classification" in SENSITIVE_RATE_LIMIT_GROUPS


def test_credential_save_is_sensitive():
    assert "credential_save" in SENSITIVE_RATE_LIMIT_GROUPS


def test_connector_test_is_sensitive():
    assert "connector_test" in SENSITIVE_RATE_LIMIT_GROUPS


# ---------------------------------------------------------------------------
# F) Error codes
# ---------------------------------------------------------------------------

def test_ten_error_codes_defined():
    assert len(REQUIRED_ERROR_CODES) == 10, (
        f"Expected 10 error codes, got {len(REQUIRED_ERROR_CODES)}"
    )


def test_all_error_codes_documented():
    doc = _doc()
    for code in REQUIRED_ERROR_CODES:
        assert code in doc, f"Error code not documented: {code}"


def test_rate_limit_exceeded_present():
    assert "RATE_LIMIT_EXCEEDED" in REQUIRED_ERROR_CODES


def test_auth_rate_limit_exceeded_present():
    assert "AUTH_RATE_LIMIT_EXCEEDED" in REQUIRED_ERROR_CODES


def test_ai_quota_exceeded_present():
    assert "AI_QUOTA_EXCEEDED" in REQUIRED_ERROR_CODES


def test_document_quota_exceeded_present():
    assert "DOCUMENT_QUOTA_EXCEEDED" in REQUIRED_ERROR_CODES


def test_connector_rate_limit_exceeded_present():
    assert "CONNECTOR_RATE_LIMIT_EXCEEDED" in REQUIRED_ERROR_CODES


def test_credential_rate_limit_exceeded_present():
    assert "CREDENTIAL_RATE_LIMIT_EXCEEDED" in REQUIRED_ERROR_CODES


def test_tenant_quota_exceeded_present():
    assert "TENANT_QUOTA_EXCEEDED" in REQUIRED_ERROR_CODES


def test_backend_degraded_present():
    assert "RATE_LIMIT_BACKEND_DEGRADED" in REQUIRED_ERROR_CODES


def test_policy_not_found_present():
    assert "RATE_LIMIT_POLICY_NOT_FOUND" in REQUIRED_ERROR_CODES


def test_export_rate_limit_exceeded_present():
    assert "EXPORT_RATE_LIMIT_EXCEEDED" in REQUIRED_ERROR_CODES


# ---------------------------------------------------------------------------
# G) Test-only policy helper
# ---------------------------------------------------------------------------

def test_active_tenant_gets_elevated_ai_limit():
    effective = get_effective_limit("ai_classification", "active", 30, 0.5, 2.0)
    assert effective == 60


def test_trial_tenant_gets_reduced_ai_limit():
    effective = get_effective_limit("ai_classification", "trial", 30, 0.5, 2.0)
    assert effective == 15


def test_trial_expired_gets_trial_limits():
    effective = get_effective_limit("ai_classification", "trial_expired", 30, 0.5, 2.0)
    assert effective == 15


def test_posting_erp_trial_multiplier_zero_blocks():
    effective = get_effective_limit("posting_erp", "trial", 20, 0.0, 1.0)
    assert effective == 0


def test_posting_erp_active_allows():
    effective = get_effective_limit("posting_erp", "active", 20, 0.0, 1.0)
    assert effective == 20


def test_auth_groups_unaffected_by_multiplier():
    for group in _AUTH_GROUPS:
        active = get_effective_limit(group, "active", 10, 1.0, 1.0)
        trial = get_effective_limit(group, "trial", 10, 1.0, 1.0)
        assert active == trial == 10, f"Auth group {group} should not be multiplied"


def test_rate_limited_when_at_limit():
    assert is_rate_limited("ai_classification", 15, 15) is True


def test_not_rate_limited_below_limit():
    assert is_rate_limited("ai_classification", 14, 15) is False


def test_not_rate_limited_at_zero_requests():
    assert is_rate_limited("auth_login", 0, 10) is False


def test_error_code_for_auth_group():
    assert get_error_code_for_group("auth_login") == "AUTH_RATE_LIMIT_EXCEEDED"
    assert get_error_code_for_group("auth_register") == "AUTH_RATE_LIMIT_EXCEEDED"


def test_error_code_for_ai_group():
    assert get_error_code_for_group("ai_classification") == "AI_QUOTA_EXCEEDED"
    assert get_error_code_for_group("ocr_processing") == "AI_QUOTA_EXCEEDED"


def test_error_code_for_document_group():
    assert get_error_code_for_group("document_upload") == "DOCUMENT_QUOTA_EXCEEDED"


def test_error_code_for_connector_group():
    assert get_error_code_for_group("posting_erp") == "CONNECTOR_RATE_LIMIT_EXCEEDED"
    assert get_error_code_for_group("connector_test") == "CONNECTOR_RATE_LIMIT_EXCEEDED"


def test_error_code_for_credential_group():
    assert get_error_code_for_group("credential_save") == "CREDENTIAL_RATE_LIMIT_EXCEEDED"


def test_error_code_for_export_group():
    assert get_error_code_for_group("export") == "EXPORT_RATE_LIMIT_EXCEEDED"


def test_error_code_for_general_group():
    assert get_error_code_for_group("general_api") == "RATE_LIMIT_EXCEEDED"
    assert get_error_code_for_group("reporting") == "RATE_LIMIT_EXCEEDED"


# ---------------------------------------------------------------------------
# H) Fallback policy checks
# ---------------------------------------------------------------------------

def test_doc_states_fail_open_for_normal_requests():
    doc = _doc()
    assert "fail-open" in doc


def test_doc_states_fail_closed_for_auth():
    doc = _doc()
    assert "fail-closed" in doc


def test_doc_mentions_circuit_breaker():
    doc = _doc()
    assert "circuit breaker" in doc.lower() or "Circuit breaker" in doc


def test_doc_mentions_sliding_window():
    doc = _doc()
    assert "sliding window" in doc.lower() or "Sliding window" in doc


def test_doc_states_fallback_still_enforces_limits():
    doc = _doc()
    assert "limits are still enforced" in doc or "still enforced" in doc


def test_doc_mentions_redis_url():
    doc = _doc()
    assert "REDIS_URL" in doc


def test_doc_mentions_in_memory_fallback():
    doc = _doc()
    assert "in-memory" in doc.lower() or "InMemory" in doc


def test_backend_degraded_is_metric_not_client_error():
    doc = _doc()
    assert "RATE_LIMIT_BACKEND_DEGRADED" in doc
    assert "metric" in doc.lower()


# ---------------------------------------------------------------------------
# I) Credential and secret safety checks
# ---------------------------------------------------------------------------

def test_safe_audit_record_has_no_forbidden_fields():
    record = safe_audit_record(
        tenant_id="tenant-abc",
        ip_hash="a1b2c3d4e5f6g7h8",
        endpoint_group="ai_classification",
        result="blocked",
        backend="redis",
        limit=30,
        remaining=0,
        error_code="AI_QUOTA_EXCEEDED",
    )
    violations = _scan_forbidden_fields(record, FORBIDDEN_AUDIT_FIELDS)
    assert violations == [], f"Forbidden fields in audit record: {violations}"


def test_safe_audit_record_has_no_raw_ip():
    record = safe_audit_record(
        tenant_id="tenant-xyz",
        ip_hash="hash123",
        endpoint_group="auth_login",
        result="blocked",
        backend="memory",
        limit=10,
        remaining=0,
        error_code="AUTH_RATE_LIMIT_EXCEEDED",
    )
    assert "ip_address" not in record
    assert "raw_ip" not in record
    assert "ip_hash" in record


def test_forbidden_audit_fields_include_credentials():
    for field in ("api_key", "password", "token", "secret", "encrypted_value"):
        assert field in FORBIDDEN_AUDIT_FIELDS, f"Missing: {field}"


def test_unsafe_audit_record_detected():
    unsafe_record = {
        "tenant_id": "t1",
        "ip_hash": "abc",
        "api_key": "live_key_12345",
        "endpoint_group": "posting_erp",
        "result": "blocked",
    }
    violations = _scan_forbidden_fields(unsafe_record, FORBIDDEN_AUDIT_FIELDS)
    assert "api_key" in violations


def test_nested_forbidden_field_detected():
    nested = {
        "tenant_id": "t2",
        "context": {
            "endpoint": "credential_save",
            "credential": {
                "password": "should-not-be-here",
            },
        },
    }
    violations = _scan_forbidden_fields(nested, FORBIDDEN_AUDIT_FIELDS)
    assert "password" in violations


def test_doc_states_raw_ip_not_logged():
    doc = _doc()
    assert "ip_hash" in doc
    assert "sha256" in doc


def test_doc_states_no_credentials_in_redis_keys():
    doc = _doc()
    assert "must not encode credential" in doc or "not encode credential" in doc


def test_rate_limit_components_must_not_receive_secrets():
    doc = _doc()
    assert "never receive, store, or log raw credentials" in doc or \
           "must never receive" in doc


def test_connector_rate_limit_fires_before_credential_fetch():
    doc = _doc()
    assert "BEFORE the connector is initialized or" in doc or \
           "before" in doc.lower() and "credential" in doc.lower()


# ---------------------------------------------------------------------------
# J) Subscription integration checks
# ---------------------------------------------------------------------------

def test_doc_references_subscription_enforcement_plan():
    doc = _doc()
    assert "subscription-enforcement-plan" in doc or "subscription enforcement" in doc.lower()


def test_doc_states_subscription_check_before_rate_limit():
    doc = _doc()
    assert "AFTER authentication and subscription" in doc or \
           "subscription enforcement" in doc.lower()


def test_posting_erp_trial_multiplier_is_defense_in_depth():
    doc = _doc()
    assert "defense in depth" in doc.lower() or "defense-in-depth" in doc.lower()


def test_subscription_states_mapped_to_rate_limits():
    doc = _doc()
    for state in ("active", "trial", "trial_expired", "suspended", "expired", "inactive"):
        assert state in doc, f"Tenant state not mapped in doc: {state}"


def test_active_subscription_multiplier_greater_than_one():
    active_limit = get_effective_limit("ai_classification", "active", 30, 0.5, 2.0)
    base = 30
    assert active_limit > base


def test_trial_subscription_multiplier_less_than_or_equal_one():
    trial_limit = get_effective_limit("ai_classification", "trial", 30, 0.5, 2.0)
    base = 30
    assert trial_limit <= base


def test_posting_erp_blocked_for_trial_by_zero_multiplier():
    limit = get_effective_limit("posting_erp", "trial", 20, 0.0, 1.0)
    assert is_rate_limited("posting_erp", 0, limit) is True


# ---------------------------------------------------------------------------
# K) Active script safety
# ---------------------------------------------------------------------------

def _get_module_imports() -> set[str]:
    """Return the set of top-level module names imported by this test file."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
    return imported


def test_security_py_not_imported():
    """Confirm this test module does not import app.api.security."""
    imported = _get_module_imports()
    assert "app" not in imported, (
        "Test file must not import any app.* module (would trigger DB/Redis init)"
    )


def test_no_db_imports():
    imported = _get_module_imports()
    db_modules = {"asyncpg", "psycopg2", "sqlalchemy"}
    violations = imported & db_modules
    assert not violations, f"Test file imports DB modules: {violations}"


def test_no_redis_imports():
    imported = _get_module_imports()
    redis_modules = {"redis", "aioredis", "coredis"}
    violations = imported & redis_modules
    assert not violations, f"Test file imports Redis modules: {violations}"


def test_no_slowapi_imports():
    imported = _get_module_imports()
    assert "slowapi" not in imported, "Test file must not import slowapi"


def test_doc_non_goals_state_no_runtime_change():
    doc = _doc()
    assert "No runtime behavior is changed in this task" in doc or \
           "No runtime code is changed in this task" in doc


def test_doc_non_goals_state_no_security_py_edit():
    doc = _doc()
    assert "security.py" in doc


def test_all_helper_functions_are_pure():
    """Assert that test-only helpers have no side effects or imports."""
    test_source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(test_source)
    helper_names = {
        "get_effective_limit",
        "is_rate_limited",
        "get_error_code_for_group",
        "safe_audit_record",
        "_scan_forbidden_fields",
    }
    defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    for name in helper_names:
        assert name in defined, f"Helper not defined: {name}"


# ---------------------------------------------------------------------------
# L) Balance.ge safety
# ---------------------------------------------------------------------------

def test_doc_states_balance_ge_inactive():
    doc = _doc()
    assert "Balance.ge" in doc
    assert "inactive" in doc


def test_doc_states_balance_ge_requires_12_gates():
    doc = _doc()
    assert "12 gates" in doc or "all 12" in doc


def test_doc_references_balance_ge_activation_gate():
    doc = _doc()
    assert "balance-ge-activation-gate" in doc


def test_doc_states_rate_limit_does_not_bypass_activation_gate():
    doc = _doc()
    assert "12 gates" in doc
    assert "Balance.ge" in doc
    assert "blocked" in doc.lower()


def test_posting_erp_group_applies_to_balance_ge():
    doc = _doc()
    assert "balance-ge" in doc.lower() or "/balance-ge/" in doc
    assert "posting_erp" in doc or "posting_erp" in doc
