import os
import logging
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse
from app.api.client_ip import client_ip_for_rate_limit
from app.api.services.rate_limiter_service import _shared_storage_required
from app.api.slowapi_shared_guard import GuardedSlowAPILimiter

log = logging.getLogger(__name__)


def _real_ip(request: Request) -> str:
    # SlowAPI and the category limiter must use the same verified identity.
    return client_ip_for_rate_limit(request)


def _make_limiter() -> Limiter:
    """Preserve existing @limiter.limit quotas with safe strict-mode storage.

    Strict mode must not silently use in-memory counters. If Redis is missing
    or a limiter cannot be constructed, keep decorators active and return a
    controlled 503 instead of using a replica-local quota silo.
    """
    redis_url = os.environ.get("REDIS_URL", "").strip()
    strict = _shared_storage_required()
    if strict:
        if redis_url.startswith(("redis://", "rediss://")):
            try:
                limiter = GuardedSlowAPILimiter(
                    key_func=_real_ip,
                    storage_uri=redis_url,
                    storage_options={
                        "socket_connect_timeout": 1,
                        "socket_timeout": 1,
                    },
                    in_memory_fallback_enabled=False,
                    swallow_errors=False,
                )
                log.info("slowapi_shared_store_configured")
                return limiter
            except Exception as exc:
                log.error(
                    "slowapi_shared_store_initialization_failed error_type=%s",
                    type(exc).__name__,
                )
        else:
            log.error("slowapi_strict_mode_missing_valid_redis_url")
        return GuardedSlowAPILimiter(
            key_func=_real_ip,
            storage_uri="memory://",  # inert: checked before any access
            unavailable=True,
            in_memory_fallback_enabled=False,
            swallow_errors=False,
        )

    # Local/development compatibility: existing per-route SlowAPI limits
    # remain unchanged, with isolated memory only when Redis is unavailable.
    if redis_url:
        try:
            return GuardedSlowAPILimiter(
                key_func=_real_ip, storage_uri=redis_url,
                in_memory_fallback_enabled=False, swallow_errors=False,
            )
        except Exception as exc:
            log.warning(
                "slowapi_dev_storage_init_failed error_type=%s",
                type(exc).__name__,
            )
    log.info("slowapi_local_in_memory_only")
    return GuardedSlowAPILimiter(key_func=_real_ip, storage_uri="memory://")


limiter = _make_limiter()


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "ok": False,
            "message": "Rate limit exceeded",
            "data": None,
            "error": {
                "code": "RATE_LIMIT",
                "details": str(exc.detail),
            },
        },
    )


# CSP policy — two tiers:
#   SECURITY_HEADERS       : strict — applied to all /api/ routes (no unsafe-inline)
#   SECURITY_HEADERS_STATIC: lenient — applied to /static/ HTML pages that still use inline scripts
# TODO(security): migrate static HTML to external JS files and remove SECURITY_HEADERS_STATIC.

_CSP_COMMON = (
    "default-src 'self' https://cdn.jsdelivr.net https://unpkg.com; "
    "img-src 'self' data: https: blob:; "
    "font-src 'self' data: https://cdn.jsdelivr.net https://unpkg.com https://fonts.gstatic.com; "
    f"connect-src 'self' {os.getenv('APP_BASE_URL', '')} https://storage.googleapis.com; "
    "frame-src 'self' blob:; "
    "object-src 'none';"
)

_CSP_STRICT = (
    _CSP_COMMON
    + "script-src 'self' https://cdn.jsdelivr.net https://unpkg.com; "
    + "style-src 'self' https://cdn.jsdelivr.net https://unpkg.com https://fonts.googleapis.com; "
)

_CSP_STATIC = (
    _CSP_COMMON
    + "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
    + "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com https://fonts.googleapis.com; "
)

_BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

SECURITY_HEADERS = {**_BASE_HEADERS, "Content-Security-Policy": _CSP_STRICT}
SECURITY_HEADERS_STATIC = {**_BASE_HEADERS, "Content-Security-Policy": _CSP_STATIC}