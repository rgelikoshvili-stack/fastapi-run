"""tests/unit/test_redis_rate_limit_contract.py

Task 10F-E: Redis / Rate-Limit Plan — contract tests.

Read-only. No DB, no Redis, no runtime imports. Validates doc content and
local-only contract definitions. Does not import app.* modules.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
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
CREDENTIAL_VAULT_DESIGN = _DOCS / "credential-vault-design.md"


def _doc() -> str:
    return RATE_LIMIT_PLAN.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Contract definitions (test-only — no runtime imports)
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
    "public_health_version",
    "auth_login",
    "auth_register",
    "password_reset_request",
    "password_reset_confirm",
    "totp_verify",
    "credential_save",
    "credential_test",
    "connector_status",
    "connector_execution",
    "document_upload",
    "ocr_processing",
    "ai_classification",
    "journal_draft_creation",
    "approval_action",
    "reporting_read",
    "exports",
    "admin_actions",
})

SENSITIVE_GROUPS: frozenset[str] = frozenset({
    "auth_login",
    "password_reset_request",
    "password_reset_confirm",
    "totp_verify",
    "credential_save",
    "credential_test",
    "connector_execution",
    "document_upload",
    "ocr_processing",
    "ai_classification",
})

REQUIRED_ERROR_CODES: frozenset[str] = frozenset({
    "RATE_LIMIT_EXCEEDED",
    "AUTH_RATE_LIMIT_EXCEEDED",
    "PASSWORD_RESET_RATE_LIMIT_EXCEEDED",
    "TOTP_RATE_LIMIT_EXCEEDED",
    "CREDENTIAL_RATE_LIMIT_EXCEEDED",
    "CONNECTOR_RATE_LIMIT_EXCEEDED",
    "OCR_RATE_LIMIT_EXCEEDED",
    "AI_RATE_LIMIT_EXCEEDED",
    "EXPORT_RATE_LIMIT_EXCEEDED",
    "RATE_LIMIT_BACKEND_UNAVAILABLE",
})

# Forbidden fields in any rate-limit key, log, or audit record
FORBIDDEN_RATE_LIMIT_FIELDS: frozenset[str] = frozenset({
    "api_key",
    "password",
    "app_password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "webhook_secret",
    "totp_secret",
    "encrypted_value",
})

# ---------------------------------------------------------------------------
# G) Test-only policy helper (pure — no runtime imports, no DB, no Redis)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SampleRateLimitPolicy:
    endpoint_group: str
    limit: int
    window_seconds: int
    key_strategy: str
    sensitive: bool
    # If True, non-sensitive group may explicitly fall back; still requires audit.
    explicit_fallback_allowed: bool


SAMPLE_POLICIES: dict[str, SampleRateLimitPolicy] = {
    "public_health_version": SampleRateLimitPolicy(
        "public_health_version", 1000, 60, "per_ip", False, True
    ),
    "auth_login": SampleRateLimitPolicy(
        "auth_login", 5, 60, "per_ip_and_user", True, False
    ),
    "password_reset_request": SampleRateLimitPolicy(
        "password_reset_request", 3, 3600, "per_ip_and_email_hash", True, False
    ),
    "totp_verify": SampleRateLimitPolicy(
        "totp_verify", 5, 300, "per_ip_and_user", True, False
    ),
    "credential_test": SampleRateLimitPolicy(
        "credential_test", 5, 3600, "per_tenant_and_provider", True, False
    ),
    "connector_execution": SampleRateLimitPolicy(
        "connector_execution", 10, 3600, "per_tenant_and_provider", True, False
    ),
    "ocr_processing": SampleRateLimitPolicy(
        "ocr_processing", 20, 3600, "per_tenant_and_user", True, False
    ),
    "ai_classification": SampleRateLimitPolicy(
        "ai_classification", 30, 3600, "per_tenant_and_user", True, False
    ),
    "reporting_read": SampleRateLimitPolicy(
        "reporting_read", 60, 60, "per_tenant", False, True
    ),
    "exports": SampleRateLimitPolicy(
        "exports", 10, 3600, "per_tenant", False, True
    ),
}


def check_rate_limit(group: str, request_count: int) -> tuple[bool, str | None]:
    """Return (allowed, error_code). Pure test-only function — no runtime imports."""
    policy = SAMPLE_POLICIES.get(group)
    if policy is None:
        return True, None
    if request_count >= policy.limit:
        return False, _error_code_for_group(group)
    return True, None


def _error_code_for_group(group: str) -> str:
    _map = {
        "auth_login": "AUTH_RATE_LIMIT_EXCEEDED",
        "auth_register": "AUTH_RATE_LIMIT_EXCEEDED",
        "password_reset_request": "PASSWORD_RESET_RATE_LIMIT_EXCEEDED",
        "password_reset_confirm": "PASSWORD_RESET_RATE_LIMIT_EXCEEDED",
        "totp_verify": "TOTP_RATE_LIMIT_EXCEEDED",
        "credential_save": "CREDENTIAL_RATE_LIMIT_EXCEEDED",
        "credential_test": "CREDENTIAL_RATE_LIMIT_EXCEEDED",
        "connector_execution": "CONNECTOR_RATE_LIMIT_EXCEEDED",
        "connector_status": "CONNECTOR_RATE_LIMIT_EXCEEDED",
        "ocr_processing": "OCR_RATE_LIMIT_EXCEEDED",
        "ai_classification": "AI_RATE_LIMIT_EXCEEDED",
        "exports": "EXPORT_RATE_LIMIT_EXCEEDED",
    }
    return _map.get(group, "RATE_LIMIT_EXCEEDED")


def get_fallback_policy(group: str) -> dict[str, Any]:
    """Return fallback behavior when Redis is unavailable. Pure test-only function."""
    policy = SAMPLE_POLICIES.get(group)
    if policy is None:
        return {"allow": True, "audit_required": True}
    if policy.sensitive:
        # Sensitive: in-memory fallback still enforces limits; never unlimited.
        return {"allow": False, "fallback_mode": "in_memory_enforce", "audit_required": True}
    if policy.explicit_fallback_allowed:
        # Non-sensitive: explicit fallback allowed but must be audited.
        return {"allow": True, "fallback_mode": "in_memory_allow", "audit_required": True}
    return {"allow": False, "fallback_mode": "in_memory_enforce", "audit_required": True}


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


def test_credential_vault_design_exists():
    assert CREDENTIAL_VAULT_DESIGN.exists(), f"Missing: {CREDENTIAL_VAULT_DESIGN}"


# ---------------------------------------------------------------------------
# B) Contract content checks
# ---------------------------------------------------------------------------

def test_doc_mentions_redis_backed_rate_limiting():
    assert "Redis-backed rate limiting" in _doc() or "Redis-backed rate-limit" in _doc()


def test_doc_mentions_redis_url():
    assert "REDIS_URL" in _doc()


def test_doc_mentions_auth_login():
    assert "auth_login" in _doc() or "auth/login" in _doc()


def test_doc_mentions_password_reset():
    assert "password_reset" in _doc() or "password reset" in _doc().lower()


def test_doc_mentions_totp():
    assert "TOTP" in _doc() or "totp_verify" in _doc()


def test_doc_mentions_credential_save_and_test():
    doc = _doc()
    assert "credential_save" in doc or "credential save" in doc.lower()
    assert "credential_test" in doc or "credential test" in doc.lower()


def test_doc_mentions_connector_execution():
    assert "connector_execution" in _doc() or "connector execution" in _doc().lower()


def test_doc_mentions_document_upload():
    assert "document_upload" in _doc() or "document upload" in _doc().lower()


def test_doc_mentions_ocr():
    doc = _doc()
    assert "OCR" in doc or "ocr_processing" in doc


def test_doc_mentions_ai_classification():
    assert "AI classification" in _doc() or "ai_classification" in _doc()


def test_doc_states_balance_ge_remains_inactive():
    doc = _doc()
    assert "Balance.ge remains inactive" in doc or (
        "Balance.ge" in doc and "inactive" in doc
    )


def test_doc_states_no_runtime_behavior_change():
    doc = _doc()
    assert "No runtime behavior is changed in this task" in doc or \
           "No runtime code is changed in this task" in doc


def test_doc_states_no_middleware_edit():
    doc = _doc()
    assert "No middleware is edited" in doc or "no middleware edit" in doc.lower()


def test_doc_states_no_security_py_edit():
    doc = _doc()
    assert "security.py" in doc and (
        "No app/api/security.py edit" in doc or "is edited" in doc or
        "not changed" in doc or "not edit" in doc.lower()
    )


def test_doc_states_no_migration():
    doc = _doc()
    assert "No migration is created" in doc or "no migration" in doc.lower()


def test_doc_states_no_db_touch():
    doc = _doc()
    assert "Production DB" in doc and "untouched" in doc


def test_doc_states_no_balance_ge_activation():
    doc = _doc()
    assert "No Balance.ge activation" in doc or (
        "Balance.ge activation" in doc and ("blocked" in doc or "inactive" in doc)
    )


# ---------------------------------------------------------------------------
# C) Component set
# ---------------------------------------------------------------------------

def test_seven_components_defined():
    assert len(RATE_LIMIT_COMPONENTS) == 7


def test_all_components_documented():
    doc = _doc()
    for component in RATE_LIMIT_COMPONENTS:
        assert component in doc, f"Component not documented: {component}"


def test_rate_limit_service_present():
    assert "RateLimitService" in RATE_LIMIT_COMPONENTS


def test_rate_limit_repository_present():
    assert "RateLimitRepository" in RATE_LIMIT_COMPONENTS


def test_redis_backend_present():
    assert "RedisRateLimitBackend" in RATE_LIMIT_COMPONENTS


def test_memory_backend_present():
    assert "InMemoryRateLimitBackend" in RATE_LIMIT_COMPONENTS


def test_policy_registry_present():
    assert "RateLimitPolicyRegistry" in RATE_LIMIT_COMPONENTS


def test_audit_logger_present():
    assert "RateLimitAuditLogger" in RATE_LIMIT_COMPONENTS


def test_decision_present():
    assert "RateLimitDecision" in RATE_LIMIT_COMPONENTS


# ---------------------------------------------------------------------------
# D) Endpoint group set
# ---------------------------------------------------------------------------

def test_eighteen_endpoint_groups_defined():
    assert len(ENDPOINT_GROUPS) == 18, f"Got {len(ENDPOINT_GROUPS)}"


def test_all_endpoint_groups_documented():
    doc = _doc()
    for group in ENDPOINT_GROUPS:
        assert group in doc, f"Endpoint group not in doc: {group}"


def test_public_health_version_present():
    assert "public_health_version" in ENDPOINT_GROUPS


def test_auth_login_group_present():
    assert "auth_login" in ENDPOINT_GROUPS


def test_auth_register_group_present():
    assert "auth_register" in ENDPOINT_GROUPS


def test_password_reset_request_present():
    assert "password_reset_request" in ENDPOINT_GROUPS


def test_password_reset_confirm_present():
    assert "password_reset_confirm" in ENDPOINT_GROUPS


def test_totp_verify_present():
    assert "totp_verify" in ENDPOINT_GROUPS


def test_credential_save_present():
    assert "credential_save" in ENDPOINT_GROUPS


def test_credential_test_present():
    assert "credential_test" in ENDPOINT_GROUPS


def test_connector_status_present():
    assert "connector_status" in ENDPOINT_GROUPS


def test_connector_execution_present():
    assert "connector_execution" in ENDPOINT_GROUPS


def test_document_upload_present():
    assert "document_upload" in ENDPOINT_GROUPS


def test_ocr_processing_present():
    assert "ocr_processing" in ENDPOINT_GROUPS


def test_ai_classification_present():
    assert "ai_classification" in ENDPOINT_GROUPS


def test_journal_draft_creation_present():
    assert "journal_draft_creation" in ENDPOINT_GROUPS


def test_approval_action_present():
    assert "approval_action" in ENDPOINT_GROUPS


def test_reporting_read_present():
    assert "reporting_read" in ENDPOINT_GROUPS


def test_exports_present():
    assert "exports" in ENDPOINT_GROUPS


def test_admin_actions_present():
    assert "admin_actions" in ENDPOINT_GROUPS


# ---------------------------------------------------------------------------
# E) Sensitive groups
# ---------------------------------------------------------------------------

def test_ten_sensitive_groups():
    assert len(SENSITIVE_GROUPS) == 10, f"Got {len(SENSITIVE_GROUPS)}"


def test_sensitive_groups_subset_of_endpoint_groups():
    assert SENSITIVE_GROUPS.issubset(ENDPOINT_GROUPS)


def test_auth_login_is_sensitive():
    assert "auth_login" in SENSITIVE_GROUPS


def test_password_reset_request_is_sensitive():
    assert "password_reset_request" in SENSITIVE_GROUPS


def test_password_reset_confirm_is_sensitive():
    assert "password_reset_confirm" in SENSITIVE_GROUPS


def test_totp_verify_is_sensitive():
    assert "totp_verify" in SENSITIVE_GROUPS


def test_credential_save_is_sensitive():
    assert "credential_save" in SENSITIVE_GROUPS


def test_credential_test_is_sensitive():
    assert "credential_test" in SENSITIVE_GROUPS


def test_connector_execution_is_sensitive():
    assert "connector_execution" in SENSITIVE_GROUPS


def test_document_upload_is_sensitive():
    assert "document_upload" in SENSITIVE_GROUPS


def test_ocr_processing_is_sensitive():
    assert "ocr_processing" in SENSITIVE_GROUPS


def test_ai_classification_is_sensitive():
    assert "ai_classification" in SENSITIVE_GROUPS


# ---------------------------------------------------------------------------
# F) Error code set
# ---------------------------------------------------------------------------

def test_ten_error_codes():
    assert len(REQUIRED_ERROR_CODES) == 10, f"Got {len(REQUIRED_ERROR_CODES)}"


def test_all_error_codes_documented():
    doc = _doc()
    for code in REQUIRED_ERROR_CODES:
        assert code in doc, f"Error code not in doc: {code}"


def test_rate_limit_exceeded_present():
    assert "RATE_LIMIT_EXCEEDED" in REQUIRED_ERROR_CODES


def test_auth_rate_limit_exceeded_present():
    assert "AUTH_RATE_LIMIT_EXCEEDED" in REQUIRED_ERROR_CODES


def test_password_reset_rate_limit_exceeded_present():
    assert "PASSWORD_RESET_RATE_LIMIT_EXCEEDED" in REQUIRED_ERROR_CODES


def test_totp_rate_limit_exceeded_present():
    assert "TOTP_RATE_LIMIT_EXCEEDED" in REQUIRED_ERROR_CODES


def test_credential_rate_limit_exceeded_present():
    assert "CREDENTIAL_RATE_LIMIT_EXCEEDED" in REQUIRED_ERROR_CODES


def test_connector_rate_limit_exceeded_present():
    assert "CONNECTOR_RATE_LIMIT_EXCEEDED" in REQUIRED_ERROR_CODES


def test_ocr_rate_limit_exceeded_present():
    assert "OCR_RATE_LIMIT_EXCEEDED" in REQUIRED_ERROR_CODES


def test_ai_rate_limit_exceeded_present():
    assert "AI_RATE_LIMIT_EXCEEDED" in REQUIRED_ERROR_CODES


def test_export_rate_limit_exceeded_present():
    assert "EXPORT_RATE_LIMIT_EXCEEDED" in REQUIRED_ERROR_CODES


def test_rate_limit_backend_unavailable_present():
    assert "RATE_LIMIT_BACKEND_UNAVAILABLE" in REQUIRED_ERROR_CODES


# ---------------------------------------------------------------------------
# G) Test-only policy helper
# ---------------------------------------------------------------------------

def test_health_version_stays_allowed_under_high_threshold():
    allowed, code = check_rate_limit("public_health_version", 999)
    assert allowed is True
    assert code is None


def test_health_version_blocks_at_limit():
    allowed, code = check_rate_limit("public_health_version", 1000)
    assert allowed is False


def test_auth_login_blocks_after_strict_threshold():
    allowed, code = check_rate_limit("auth_login", 5)
    assert allowed is False
    assert code == "AUTH_RATE_LIMIT_EXCEEDED"


def test_auth_login_allows_below_threshold():
    allowed, code = check_rate_limit("auth_login", 4)
    assert allowed is True
    assert code is None


def test_credential_test_blocks_after_strict_threshold():
    allowed, code = check_rate_limit("credential_test", 5)
    assert allowed is False
    assert code == "CREDENTIAL_RATE_LIMIT_EXCEEDED"


def test_connector_execution_blocks_after_provider_threshold():
    allowed, code = check_rate_limit("connector_execution", 10)
    assert allowed is False
    assert code == "CONNECTOR_RATE_LIMIT_EXCEEDED"


def test_ocr_processing_blocks_after_quota_threshold():
    allowed, code = check_rate_limit("ocr_processing", 20)
    assert allowed is False
    assert code == "OCR_RATE_LIMIT_EXCEEDED"


def test_ai_classification_blocks_after_quota_threshold():
    allowed, code = check_rate_limit("ai_classification", 30)
    assert allowed is False
    assert code == "AI_RATE_LIMIT_EXCEEDED"


def test_error_code_mapping_for_password_reset():
    assert _error_code_for_group("password_reset_request") == "PASSWORD_RESET_RATE_LIMIT_EXCEEDED"
    assert _error_code_for_group("password_reset_confirm") == "PASSWORD_RESET_RATE_LIMIT_EXCEEDED"


def test_error_code_mapping_for_totp():
    assert _error_code_for_group("totp_verify") == "TOTP_RATE_LIMIT_EXCEEDED"


def test_error_code_mapping_for_exports():
    assert _error_code_for_group("exports") == "EXPORT_RATE_LIMIT_EXCEEDED"


def test_error_code_mapping_for_unknown_group():
    assert _error_code_for_group("some_unknown_group") == "RATE_LIMIT_EXCEEDED"


# ---------------------------------------------------------------------------
# H) Fallback policy checks
# ---------------------------------------------------------------------------

def test_sensitive_auth_login_does_not_allow_unlimited_fallback():
    policy = get_fallback_policy("auth_login")
    assert policy["allow"] is False, "auth_login must not silently allow unlimited fallback"
    assert policy["audit_required"] is True


def test_sensitive_totp_does_not_allow_unlimited_fallback():
    policy = get_fallback_policy("totp_verify")
    assert policy["allow"] is False
    assert policy["audit_required"] is True


def test_sensitive_credential_test_does_not_allow_unlimited_fallback():
    policy = get_fallback_policy("credential_test")
    assert policy["allow"] is False
    assert policy["audit_required"] is True


def test_sensitive_connector_execution_does_not_allow_unlimited_fallback():
    policy = get_fallback_policy("connector_execution")
    assert policy["allow"] is False
    assert policy["audit_required"] is True


def test_reporting_read_may_allow_explicit_fallback():
    # Non-sensitive reporting_read may allow explicit fallback when Redis is down.
    policy = get_fallback_policy("reporting_read")
    assert policy["allow"] is True
    assert policy["audit_required"] is True


def test_all_fallback_policies_require_audit():
    for group in SAMPLE_POLICIES:
        policy = get_fallback_policy(group)
        assert policy["audit_required"] is True, f"Fallback for {group} must require audit"


def test_doc_mentions_fallback_must_not_be_silent():
    doc = _doc()
    assert "never silent" in doc or "not silent" in doc or "must be logged" in doc


def test_doc_mentions_explicit_fallback():
    doc = _doc()
    assert "explicit" in doc.lower()


# ---------------------------------------------------------------------------
# I) Secret safety checks
# ---------------------------------------------------------------------------

def test_doc_states_no_secrets_in_rate_limit_keys():
    doc = _doc()
    assert "no secret values in rate-limit keys" in doc or \
           "Never stores" in doc or "must never appear in any rate-limit key" in doc


def test_doc_states_no_raw_secrets_in_logs():
    doc = _doc()
    assert "no raw secrets in rate-limit logs" in doc or \
           "must never log raw credentials" in doc or "never appear in logs" in doc


def test_doc_states_api_key_password_token_forbidden():
    doc = _doc()
    assert "api_key" in doc or "api key" in doc.lower()
    assert "password" in doc.lower()
    assert "token" in doc.lower()


def test_forbidden_fields_include_core_credentials():
    for field in ("api_key", "password", "token", "secret"):
        assert field in FORBIDDEN_RATE_LIMIT_FIELDS


def test_safe_audit_record_has_no_forbidden_fields():
    safe_record = {
        "tenant_id": "tenant-abc",
        "ip_hash": "a1b2c3d4",
        "endpoint_group": "credential_test",
        "provider": "balance",
        "result": "blocked",
        "backend": "redis",
        "limit": 5,
        "remaining": 0,
        "error_code": "CREDENTIAL_RATE_LIMIT_EXCEEDED",
    }
    violations = _scan_forbidden_fields(safe_record, FORBIDDEN_RATE_LIMIT_FIELDS)
    assert violations == [], f"Forbidden fields in audit record: {violations}"


def test_unsafe_audit_record_detected():
    unsafe_record = {
        "tenant_id": "t1",
        "ip_hash": "abc",
        "api_key": "live_balance_key",
        "endpoint_group": "credential_test",
        "result": "blocked",
    }
    violations = _scan_forbidden_fields(unsafe_record, FORBIDDEN_RATE_LIMIT_FIELDS)
    assert "api_key" in violations


def test_nested_forbidden_field_detected():
    nested = {
        "tenant_id": "t2",
        "context": {
            "endpoint": "connector_execution",
            "credential": {"password": "should-not-be-here"},
        },
    }
    violations = _scan_forbidden_fields(nested, FORBIDDEN_RATE_LIMIT_FIELDS)
    assert "password" in violations


# ---------------------------------------------------------------------------
# J) Subscription integration checks
# ---------------------------------------------------------------------------

def test_doc_states_expired_suspended_blocked_before_rate_limit():
    doc = _doc()
    assert "expired" in doc and "suspended" in doc
    assert "blocked by subscription enforcement before" in doc or \
           "remain blocked" in doc


def test_doc_states_trial_tenants_stricter_quotas():
    doc = _doc()
    assert "trial" in doc
    assert "stricter" in doc or "stricter quotas" in doc or "50%" in doc


def test_doc_states_rate_limit_must_not_bypass_subscription():
    doc = _doc()
    assert "rate limit must not bypass subscription" in doc or \
           "must not bypass subscription blocking" in doc


def test_doc_references_subscription_enforcement_plan():
    doc = _doc()
    assert "subscription-enforcement-plan" in doc or "subscription enforcement" in doc.lower()


# ---------------------------------------------------------------------------
# K) Active script safety
# ---------------------------------------------------------------------------

def test_no_drop_table_if_exists_users_in_startup_scripts():
    """Startup/migration scripts must not contain DROP TABLE IF EXISTS users."""
    startup_dir = _REPO / "app" / "startup"
    dangerous = "DROP " + "TABLE IF EXISTS users"
    if startup_dir.exists():
        for script in startup_dir.glob("*.py"):
            content = script.read_text(encoding="utf-8")
            assert dangerous not in content, f"Dangerous DDL in {script.name}"


def test_no_drop_table_in_doc():
    doc = _doc()
    assert "DROP TABLE" not in doc


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


def test_no_app_module_imported():
    imported = _get_module_imports()
    assert "app" not in imported, "Must not import any app.* module"


def test_no_db_module_imported():
    imported = _get_module_imports()
    db_modules = {"asyncpg", "psycopg2", "sqlalchemy"}
    assert not (imported & db_modules)


def test_no_redis_module_imported():
    imported = _get_module_imports()
    redis_modules = {"redis", "aioredis", "coredis"}
    assert not (imported & redis_modules)


def test_no_slowapi_module_imported():
    imported = _get_module_imports()
    assert "slowapi" not in imported


def test_doc_non_goals_state_no_runtime_change():
    doc = _doc()
    assert "No runtime behavior is changed in this task" in doc or \
           "No runtime code is changed in this task" in doc


def test_all_test_only_helpers_are_defined():
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    for name in ("check_rate_limit", "_error_code_for_group", "get_fallback_policy",
                 "_scan_forbidden_fields", "_get_module_imports"):
        assert name in defined, f"Helper not defined: {name}"


# ---------------------------------------------------------------------------
# L) Balance.ge safety
# ---------------------------------------------------------------------------

def test_doc_states_balance_ge_inactive():
    doc = _doc()
    assert "Balance.ge" in doc
    assert "inactive" in doc


def test_doc_states_balance_ge_requires_all_gates():
    doc = _doc()
    assert "12 gates" in doc or "all 12" in doc


def test_doc_references_balance_ge_activation_gate():
    doc = _doc()
    assert "balance-ge-activation-gate" in doc


def test_doc_states_balance_ge_not_bypassed_by_rate_limit():
    doc = _doc()
    assert "Balance.ge" in doc
    assert "12 gates" in doc or "all 12" in doc
    assert "MET" in doc or "met" in doc.lower()
