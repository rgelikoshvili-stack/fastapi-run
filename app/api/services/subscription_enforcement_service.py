"""app/api/services/subscription_enforcement_service.py

Pure policy layer for tenant subscription/trial enforcement.
No side effects, no DB connections, no network calls.
All DB access is isolated in get_tenant_subscription_record() — mockable in tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Subscription status constants
# ---------------------------------------------------------------------------

class SubscriptionStatus:
    ACTIVE = "active"
    TRIAL = "trial"
    TRIAL_EXPIRED = "trial_expired"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Action categories
# ---------------------------------------------------------------------------

class ActionCategory:
    READ_SAFE = "read_safe"
    AUTH_SAFE = "auth_safe"
    BILLING_SAFE = "billing_safe"
    CREDENTIAL_WRITE = "credential_write"
    CONNECTOR_EXECUTE = "connector_execute"
    POSTING_EXECUTE = "posting_execute"
    APPROVAL_MUTATION = "approval_mutation"
    AI_HEAVY = "ai_heavy"
    DOCUMENT_UPLOAD = "document_upload"
    ADMIN_MUTATION = "admin_mutation"


# ---------------------------------------------------------------------------
# Error codes
# ---------------------------------------------------------------------------

class SubscriptionErrorCode:
    SUBSCRIPTION_REQUIRED = "SUBSCRIPTION_REQUIRED"
    TENANT_SUSPENDED = "TENANT_SUSPENDED"
    TENANT_INACTIVE = "TENANT_INACTIVE"
    TRIAL_EXPIRED = "TRIAL_EXPIRED"
    SUBSCRIPTION_EXPIRED = "SUBSCRIPTION_EXPIRED"
    TENANT_STATUS_UNKNOWN = "TENANT_STATUS_UNKNOWN"


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------

@dataclass
class SubscriptionDecision:
    allowed: bool
    status: str = SubscriptionStatus.UNKNOWN
    error_code: Optional[str] = None
    message: str = ""


# ---------------------------------------------------------------------------
# Sensitive/safe category sets
# ---------------------------------------------------------------------------

_SENSITIVE_CATEGORIES: frozenset[str] = frozenset({
    ActionCategory.CREDENTIAL_WRITE,
    ActionCategory.CONNECTOR_EXECUTE,
    ActionCategory.POSTING_EXECUTE,
    ActionCategory.APPROVAL_MUTATION,
    ActionCategory.AI_HEAVY,
    ActionCategory.DOCUMENT_UPLOAD,
    ActionCategory.ADMIN_MUTATION,
})

_ALWAYS_ALLOWED_CATEGORIES: frozenset[str] = frozenset({
    ActionCategory.AUTH_SAFE,
    ActionCategory.BILLING_SAFE,
    ActionCategory.READ_SAFE,
})

# These categories are blocked even for trial tenants
_TRIAL_BLOCKED_CATEGORIES: frozenset[str] = frozenset({
    ActionCategory.CONNECTOR_EXECUTE,
    ActionCategory.POSTING_EXECUTE,
})

_BLOCKING_STATUSES: frozenset[str] = frozenset({
    SubscriptionStatus.TRIAL_EXPIRED,
    SubscriptionStatus.SUSPENDED,
    SubscriptionStatus.INACTIVE,
    SubscriptionStatus.EXPIRED,
    SubscriptionStatus.UNKNOWN,
})


def is_sensitive_action(action_category: str) -> bool:
    """Return True if the action category requires an active/trial subscription."""
    return action_category in _SENSITIVE_CATEGORIES


# ---------------------------------------------------------------------------
# Status resolution
# ---------------------------------------------------------------------------

def _parse_datetime(value: object) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None
    return None


def _to_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _resolve_status(tenant_record: dict, now: datetime) -> str:
    if not tenant_record:
        return SubscriptionStatus.UNKNOWN

    is_active = tenant_record.get("is_active", True)
    status = (tenant_record.get("status") or "").lower().strip()

    if not is_active:
        return SubscriptionStatus.INACTIVE

    if status == SubscriptionStatus.ACTIVE:
        return SubscriptionStatus.ACTIVE

    if status == SubscriptionStatus.TRIAL:
        trial_ends_at = _parse_datetime(tenant_record.get("trial_ends_at"))
        if trial_ends_at is not None:
            if _to_aware(trial_ends_at) < now:
                return SubscriptionStatus.TRIAL_EXPIRED
        return SubscriptionStatus.TRIAL

    if status in (
        SubscriptionStatus.TRIAL_EXPIRED,
        SubscriptionStatus.SUSPENDED,
        SubscriptionStatus.EXPIRED,
        SubscriptionStatus.INACTIVE,
    ):
        return status

    # Treat any is_active record with unrecognized status as active
    if is_active:
        return SubscriptionStatus.ACTIVE

    return SubscriptionStatus.UNKNOWN


_ERROR_CODE_MAP: dict[str, str] = {
    SubscriptionStatus.TRIAL_EXPIRED: SubscriptionErrorCode.TRIAL_EXPIRED,
    SubscriptionStatus.SUSPENDED: SubscriptionErrorCode.TENANT_SUSPENDED,
    SubscriptionStatus.INACTIVE: SubscriptionErrorCode.TENANT_INACTIVE,
    SubscriptionStatus.EXPIRED: SubscriptionErrorCode.SUBSCRIPTION_EXPIRED,
    SubscriptionStatus.UNKNOWN: SubscriptionErrorCode.TENANT_STATUS_UNKNOWN,
}


# ---------------------------------------------------------------------------
# Main evaluation function
# ---------------------------------------------------------------------------

def evaluate_subscription_access(
    tenant_record: Optional[dict],
    action_category: str,
    now: Optional[datetime] = None,
) -> SubscriptionDecision:
    """Evaluate whether the given action is allowed for this tenant.

    Pure function — no DB, no network, no side effects.
    Fails closed for sensitive actions when tenant state is unknown.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    resolved = _resolve_status(tenant_record or {}, now)

    # Safe categories bypass subscription checks entirely (but report real status)
    if action_category in _ALWAYS_ALLOWED_CATEGORIES:
        return SubscriptionDecision(
            allowed=True,
            status=resolved,
            message="safe category — no subscription check required",
        )

    # Active tenant: full access
    if resolved == SubscriptionStatus.ACTIVE:
        return SubscriptionDecision(allowed=True, status=resolved)

    # Trial tenant: limited access
    if resolved == SubscriptionStatus.TRIAL:
        if action_category in _TRIAL_BLOCKED_CATEGORIES:
            return SubscriptionDecision(
                allowed=False,
                status=resolved,
                error_code=SubscriptionErrorCode.SUBSCRIPTION_REQUIRED,
                message="Active subscription required for connector/posting execution",
            )
        return SubscriptionDecision(allowed=True, status=resolved)

    # Blocking states
    if resolved in _BLOCKING_STATUSES:
        if is_sensitive_action(action_category):
            code = _ERROR_CODE_MAP.get(resolved, SubscriptionErrorCode.SUBSCRIPTION_REQUIRED)
            return SubscriptionDecision(
                allowed=False,
                status=resolved,
                error_code=code,
                message=f"Tenant access blocked: {resolved}",
            )
        # Non-sensitive read is allowed even in blocking states
        return SubscriptionDecision(allowed=True, status=resolved)

    return SubscriptionDecision(allowed=True, status=resolved)


# ---------------------------------------------------------------------------
# Error response builder
# ---------------------------------------------------------------------------

def build_subscription_error(decision: SubscriptionDecision) -> dict:
    """Build a safe HTTP error response — no raw tenant data, no secrets."""
    return {
        "ok": False,
        "message": decision.message or "Access denied: subscription required",
        "data": None,
        "error": {
            "code": decision.error_code or SubscriptionErrorCode.SUBSCRIPTION_REQUIRED,
            "details": decision.message or "Tenant subscription does not permit this action",
        },
    }


# ---------------------------------------------------------------------------
# Tenant record loader — mockable in unit tests
# ---------------------------------------------------------------------------

async def get_tenant_subscription_record(tenant_id: str) -> Optional[dict]:
    """Load the tenant's subscription record from the database.

    Returns None if the tenant is not found or on any DB error.
    This function is designed to be patched in unit tests — do not
    inline DB calls into policy logic.
    """
    try:
        from app.api.db import get_conn, _q
        async with get_conn() as conn:
            row = await conn.fetchrow(_q(
                "SELECT tenant_id, status, is_active, plan, "
                "trial_ends_at, subscription_expires_at "
                "FROM tenants WHERE tenant_id = %s"
            ), tenant_id)
        if row:
            return dict(row)
        return None
    except Exception:
        return None
