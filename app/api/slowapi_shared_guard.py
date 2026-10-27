"""SlowAPI 0.1.9 guard: preserve per-route limits without fail-open fallback.

The package's middleware assumes every limiter exception is RateLimitExceeded.
Redis connection errors can therefore reach an incompatible 429 handler.
Translate ONLY non-quota storage errors to a dedicated safe 503 in strict mode.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app.api.services.rate_limiter_service import _shared_storage_required

log = logging.getLogger(__name__)


class SharedRateLimitStoreUnavailable(RuntimeError):
    """Strict shared rate-limit storage cannot be used; no local fallback."""


class GuardedSlowAPILimiter(Limiter):
    """Keep SlowAPI's normal decorator quotas, translating strict failures."""

    def __init__(self, *args: Any, unavailable: bool = False, **kwargs: Any):
        self._shared_unavailable_on_startup = unavailable
        super().__init__(*args, **kwargs)
        if _shared_storage_required():
            # SlowAPI can also read RATELIMIT_ENABLED from an inherited .env.
            # Do not permit a config file to disable strict route-specific
            # limits or enable process-local memory fallback in Production.
            self.enabled = True
            self._in_memory_fallback_enabled = False
            self._fallback_limiter = None
            self._swallow_errors = False

    def _check_request_limit(
        self,
        request: Request,
        endpoint_func: Optional[Callable[..., Any]],
        in_middleware: bool = True,
    ) -> None:
        if self._shared_unavailable_on_startup:
            raise SharedRateLimitStoreUnavailable()
        try:
            return super()._check_request_limit(
                request, endpoint_func, in_middleware
            )
        except RateLimitExceeded:
            raise  # legitimate SlowAPI 429, preserve the route-specific quota
        except Exception as exc:
            if _shared_storage_required():
                # Avoid including Redis URL, key, headers or credentials.
                log.error(
                    "slowapi_shared_store_unavailable error_type=%s",
                    type(exc).__name__,
                )
                raise SharedRateLimitStoreUnavailable() from None
            raise


def shared_rate_limit_unavailable_handler(
    request: Request, exc: SharedRateLimitStoreUnavailable,
) -> JSONResponse:
    """Safe response used by both SlowAPIMiddleware and decorated routes."""
    response = JSONResponse(
        status_code=503,
        content={
            "ok": False,
            "message": "Service temporarily unavailable",
            "data": None,
            "error": {
                "code": "RATE_LIMIT_BACKEND_UNAVAILABLE",
                "details": None,
            },
        },
    )
    response.headers["Retry-After"] = "5"
    response.headers["Cache-Control"] = "no-store"
    return response
