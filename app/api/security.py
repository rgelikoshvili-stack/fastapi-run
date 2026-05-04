import os
import logging
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)


def _real_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _make_limiter() -> Limiter:
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            limiter = Limiter(key_func=_real_ip, storage_uri=redis_url)
            log.info("Rate limiter: Redis storage (%s)", redis_url.split("@")[-1])
            return limiter
        except Exception as e:
            log.warning("Redis limiter init failed (%s), falling back to memory: %s", redis_url, e)
    log.info("Rate limiter: in-memory storage (single-instance only)")
    return Limiter(key_func=_real_ip)


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


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self' https://cdn.jsdelivr.net https://unpkg.com; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com https://fonts.googleapis.com; "
        "img-src 'self' data: https: blob:; "
        "font-src 'self' data: https://cdn.jsdelivr.net https://unpkg.com https://fonts.gstatic.com; "
        "connect-src 'self' https://fastapi-run-oobzrmikna-ew.a.run.app https://storage.googleapis.com; "
        "frame-src 'self' blob:; "
        "object-src 'self' blob:;"
    ),
    "X-Powered-By": "BridgeHub/1.0",
}