"""app/api/middleware/rate_limit_middleware.py

Rate-limit enforcement middleware.
Classifies requests, builds safe keys, enforces per-category limits.
Returns 429 with safe error envelope when limit exceeded.

Registration (add to main.py between audit_log and subscription lines):
    app.middleware("http")(rate_limit_middleware)

Execution order in pipeline:
    tenant → auth → rbac → subscription → rate_limit → audit_log → correlation

Subscription/RBAC checks run first so that:
- Unauthenticated requests → 401 from rbac, never reach rate-limit check.
- Blocked-subscription requests → 402 from subscription, never consume quota.
- Only authenticated, subscription-permitted requests consume rate-limit quota.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.api.services.rate_limit_policy_service import (
    RateLimitCategory,
    build_rate_limit_error,
    build_rate_limit_key,
    classify_rate_limit_category,
    get_rate_limit_rule,
    is_rate_limited_category,
)
from app.api.services.rate_limiter_service import get_rate_limiter_service

log = logging.getLogger(__name__)

# Safe paths — never rate-limited, no key lookup
_ALWAYS_SAFE_PREFIXES: tuple[str, ...] = (
    "/health",
    "/static",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/version",
    "/metrics",
)

_ALWAYS_SAFE_EXACT: frozenset[str] = frozenset({
    "/",
    "/health",
    "/health/",
    "/version",
    "/docs",
    "/docs/",
    "/redoc",
    "/redoc/",
    "/openapi.json",
    "/metrics",
})


def _is_always_safe(path: str) -> bool:
    if path in _ALWAYS_SAFE_EXACT:
        return True
    return any(path.startswith(p) for p in _ALWAYS_SAFE_PREFIXES)


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def rate_limit_middleware(request: Request, call_next: Any):
    """Middleware: enforce per-category rate limits.

    - Always allows safe paths without any limit check.
    - Classifies path into a category.
    - Skips rate-limit for SAFE category.
    - Checks in-memory or Redis counter.
    - Returns 429 with safe error envelope when blocked.
    - Adds X-RateLimit-* headers to allowed responses.
    """
    path = request.url.path

    # Fast path — safe endpoints never rate-limited
    if _is_always_safe(path):
        return await call_next(request)

    method = request.method
    category = classify_rate_limit_category(path, method)

    # Safe category by classification — pass through
    if category == RateLimitCategory.SAFE or not is_rate_limited_category(category):
        return await call_next(request)

    # Build rate-limit key from non-secret request context
    tenant_id = getattr(request.state, "tenant_id", None)
    user_id = getattr(request.state, "user_id", None)
    client_ip = _get_client_ip(request)

    key = build_rate_limit_key(tenant_id, user_id, client_ip, category)
    rule = get_rate_limit_rule(category)

    limiter = get_rate_limiter_service()
    result = limiter.check_limit(key, rule)

    if not result.allowed:
        log.warning(
            "rate_limit_blocked tenant=%s category=%s path=%s method=%s "
            "retry_after=%s backend=%s",
            tenant_id, category, path, method,
            result.retry_after_seconds, result.backend,
        )
        error = build_rate_limit_error(rule, result.retry_after_seconds)
        response = JSONResponse(status_code=429, content=error)
        response.headers["Retry-After"] = str(result.retry_after_seconds)
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = "0"
        return response

    response = await call_next(request)

    # Add informational headers to allowed responses
    response.headers["X-RateLimit-Limit"] = str(result.limit)
    response.headers["X-RateLimit-Remaining"] = str(result.remaining)

    return response
