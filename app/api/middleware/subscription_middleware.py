"""app/api/middleware/subscription_middleware.py

Subscription/trial enforcement middleware.
Blocks sensitive requests for expired, suspended, or inactive tenants.
Safe paths (health, version, static, auth) always pass through.

Registration (add to main.py after auth_middleware registration):
    app.middleware("http")(subscription_middleware)

This middleware must run after tenant_middleware and auth_middleware so that
request.state.tenant_id is already set before the subscription check.
"""
from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app.api.services.subscription_enforcement_service import (
    ActionCategory,
    build_subscription_error,
    evaluate_subscription_access,
    get_tenant_subscription_record,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path sets — always allowed, never touch subscription state
# ---------------------------------------------------------------------------

_ALWAYS_SAFE_EXACT: frozenset[str] = frozenset({
    "/",
    "/health",
    "/health/",
    "/health/deep",
    "/health/ping",
    "/version",
    "/openapi.json",
    "/docs",
    "/docs/",
    "/redoc",
    "/redoc/",
})

_ALWAYS_SAFE_PREFIXES: tuple[str, ...] = (
    "/health",
    "/static",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/auth/login",
    "/auth/register",
    "/auth/refresh",
    "/auth/",
    "/subscriptions/",
    "/billing/",
    "/version",
)

# ---------------------------------------------------------------------------
# Read-safe exact paths (status/reporting — always allowed)
# ---------------------------------------------------------------------------

_READ_SAFE_EXACT: frozenset[str] = frozenset({
    "/posting/balance-status",
    "/posting/onec-status",
    "/posting/oris-status",
    "/posting/logs",
    "/posting/history",
    "/posting/approved-drafts",
    "/approval/queue",
    "/balance-credentials/status",
    "/rsge-credentials/status",
})

# ---------------------------------------------------------------------------
# Path prefix → action category (checked in order; more specific first)
# ---------------------------------------------------------------------------

_READ_SAFE_PREFIXES: tuple[str, ...] = (
    "/posting/logs/",
    "/posting/history",
    "/posting/payload/",
    "/posting/preview/",
    "/posting/approved-drafts",
    "/reports/",
    "/balance-credentials/status",
)

_POSTING_EXECUTE_PREFIXES: tuple[str, ...] = (
    "/posting/balance/",
    "/posting/onec/",
    "/posting/oris/",
    "/posting/apply/",
    "/posting/mock/",
)

_APPROVAL_MUTATION_PREFIXES: tuple[str, ...] = (
    "/approval/approve/",
    "/approval/reject/",
    "/approval/correct/",
)

_CREDENTIAL_WRITE_EXACT: frozenset[str] = frozenset({
    "/balance-credentials/save",
    "/balance-credentials/test",
    "/rsge-credentials/save",
    "/rsge-credentials/test",
})

_DOCUMENT_PREFIXES: tuple[str, ...] = (
    "/documents/upload",
)

_AI_PREFIXES: tuple[str, ...] = (
    "/ocr/",
    "/ai-journal/",
    "/ai-chat/",
    "/ai-recommend/",
    "/claude-chat/",
    "/transaction-ai/",
    "/chat/",
)

_ERP_PREFIXES: tuple[str, ...] = (
    "/erp/",
)


def _classify_path(path: str, method: str) -> str:
    """Classify a request path+method into an action category."""

    # Exact read-safe status paths
    if path in _READ_SAFE_EXACT:
        return ActionCategory.READ_SAFE

    # Billing/subscription paths — always safe
    for prefix in ("/subscriptions/", "/billing/"):
        if path.startswith(prefix):
            return ActionCategory.BILLING_SAFE

    # Posting execute (POST/PUT only — GET = read_safe via method fallback)
    for prefix in _POSTING_EXECUTE_PREFIXES:
        if path.startswith(prefix):
            if method in ("GET", "HEAD"):
                return ActionCategory.READ_SAFE
            return ActionCategory.POSTING_EXECUTE

    # Approval mutations
    if path.startswith("/approval/queue") and method == "GET":
        return ActionCategory.READ_SAFE
    for prefix in _APPROVAL_MUTATION_PREFIXES:
        if path.startswith(prefix):
            return ActionCategory.APPROVAL_MUTATION
    if path.startswith("/approval/") and method not in ("GET", "HEAD", "OPTIONS"):
        return ActionCategory.APPROVAL_MUTATION

    # Credential writes
    if path in _CREDENTIAL_WRITE_EXACT:
        return ActionCategory.CREDENTIAL_WRITE
    if path.startswith("/balance-credentials/") and method not in ("GET", "HEAD"):
        return ActionCategory.CREDENTIAL_WRITE
    if path.startswith("/rsge-credentials/") and method not in ("GET", "HEAD"):
        return ActionCategory.CREDENTIAL_WRITE

    # Document upload
    for prefix in _DOCUMENT_PREFIXES:
        if path.startswith(prefix):
            return ActionCategory.DOCUMENT_UPLOAD
    if path.startswith("/documents/") and method not in ("GET", "HEAD"):
        return ActionCategory.DOCUMENT_UPLOAD

    # AI/heavy paths
    for prefix in _AI_PREFIXES:
        if path.startswith(prefix):
            return ActionCategory.AI_HEAVY

    # ERP/admin mutations
    for prefix in _ERP_PREFIXES:
        if path.startswith(prefix):
            return ActionCategory.ADMIN_MUTATION

    # Read-safe prefixes
    for prefix in _READ_SAFE_PREFIXES:
        if path.startswith(prefix):
            return ActionCategory.READ_SAFE

    # Default: read_safe for GET, read_safe for unclassified (fail-open)
    return ActionCategory.READ_SAFE


def _is_safe_path(path: str) -> bool:
    """Return True if the path is always safe — never needs a subscription check."""
    if path in _ALWAYS_SAFE_EXACT:
        return True
    return any(path == p or path.startswith(p) for p in _ALWAYS_SAFE_PREFIXES)


async def subscription_middleware(request: Request, call_next):
    """Middleware: block sensitive requests for blocked tenants.

    - Always allows health/version/static/auth paths without DB lookup.
    - Loads tenant subscription record (one DB call per request for sensitive paths).
    - Returns 402 with safe error envelope if tenant is blocked.
    """
    path = request.url.path
    method = request.method

    # Fast path: always-safe endpoints skip DB lookup entirely
    if _is_safe_path(path):
        return await call_next(request)

    # Classify the action
    action_category = _classify_path(path, method)

    # Read-safe actions are always allowed without DB lookup
    if action_category in (ActionCategory.READ_SAFE, ActionCategory.BILLING_SAFE, ActionCategory.AUTH_SAFE):
        return await call_next(request)

    # Sensitive action — load tenant subscription record
    tenant_id = getattr(request.state, "tenant_id", None) or "default"
    tenant_record = await get_tenant_subscription_record(tenant_id)

    decision = evaluate_subscription_access(tenant_record, action_category)

    if not decision.allowed:
        log.warning(
            "subscription_block tenant=%s path=%s method=%s status=%s code=%s",
            tenant_id, path, method, decision.status, decision.error_code,
        )
        error = build_subscription_error(decision)
        return JSONResponse(status_code=402, content=error)

    return await call_next(request)
