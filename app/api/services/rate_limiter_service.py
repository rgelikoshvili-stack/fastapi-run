"""app/api/services/rate_limiter_service.py

Rate-limit service with an atomic Redis fixed window for multiple replicas.

Production (ENVIRONMENT=production) and RATE_LIMIT_REQUIRE_SHARED=1
FAIL CLOSED if Redis is absent or unavailable. Only tests/local development
can use a process-local memory fallback. Real Redis tests run in a separate,
explicitly guarded disposable CI job.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional

from app.api.services.rate_limit_policy_service import RateLimitRule

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    limit: int
    retry_after_seconds: int
    reset_at: float          # Unix timestamp
    backend: str             # "redis" | "memory_fallback"
    error_code: Optional[str] = None


# ---------------------------------------------------------------------------
# In-memory fixed-window backend
# ---------------------------------------------------------------------------

class InMemoryRateLimiterBackend:
    """Single-process fixed-window rate limiter.

    Bounded: max 10 000 distinct keys in memory; evicts expired entries on
    access.  Not suitable for multi-instance production, but safe for tests
    and development.
    """

    MAX_KEYS = 10_000

    def __init__(self) -> None:
        self._store: dict[str, dict] = {}   # key → {count, window_start}
        self._lock = threading.Lock()

    def check(self, key: str, rule: RateLimitRule, now: Optional[float] = None) -> RateLimitResult:
        now = now if now is not None else time.time()
        window = rule.window_seconds

        with self._lock:
            entry = self._store.get(key)

            if entry is None or now >= entry["window_start"] + window:
                # New window
                if len(self._store) >= self.MAX_KEYS:
                    self._evict_expired(now)
                entry = {"count": 1, "window_start": now}
                self._store[key] = entry
                remaining = rule.limit - 1
                reset_at = now + window
                return RateLimitResult(
                    allowed=True,
                    remaining=remaining,
                    limit=rule.limit,
                    retry_after_seconds=0,
                    reset_at=reset_at,
                    backend="memory_fallback",
                )

            # Within existing window
            entry["count"] += 1
            count = entry["count"]
            reset_at = entry["window_start"] + window
            remaining = max(0, rule.limit - count)

            if count > rule.limit:
                retry_after = max(1, int(reset_at - now))
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    limit=rule.limit,
                    retry_after_seconds=retry_after,
                    reset_at=reset_at,
                    backend="memory_fallback",
                    error_code=rule.error_code,
                )

            return RateLimitResult(
                allowed=True,
                remaining=remaining,
                limit=rule.limit,
                retry_after_seconds=0,
                reset_at=reset_at,
                backend="memory_fallback",
            )

    def reset(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def _evict_expired(self, now: float) -> None:
        expired = [k for k, v in self._store.items() if now >= v["window_start"] + 3600]
        for k in expired[:500]:
            del self._store[k]


# ---------------------------------------------------------------------------
# Shared Redis backend and explicitly denied shared-storage dependency
# ---------------------------------------------------------------------------

# Redis evaluates this entire script atomically. This avoids the race between
# the old INCR and later EXPIRE which could leave a hot key without any TTL.
_REDIS_FIXED_WINDOW_LUA = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end
local ttl = redis.call('TTL', KEYS[1])
if ttl < 1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
    ttl = redis.call('TTL', KEYS[1])
end
return {count, ttl}
"""

_SHARED_UNAVAILABLE_CODE = "RATE_LIMIT_BACKEND_UNAVAILABLE"
_SHARED_RETRY_SECONDS = 5


def _shared_storage_required() -> bool:
    """Production cannot silently downgrade to per-instance counters."""
    return (
        os.environ.get("ENVIRONMENT", "").strip().casefold() == "production"
        or os.environ.get("RATE_LIMIT_REQUIRE_SHARED", "") == "1"
    )


def _shared_unavailable(rule: RateLimitRule, now: float) -> RateLimitResult:
    return RateLimitResult(
        allowed=False,
        remaining=0,
        limit=rule.limit,
        retry_after_seconds=_SHARED_RETRY_SECONDS,
        reset_at=now + _SHARED_RETRY_SECONDS,
        backend="shared_unavailable",
        error_code=_SHARED_UNAVAILABLE_CODE,
    )


class UnavailableRateLimiterBackend:
    """Explicit denial when shared quota storage is missing in strict mode."""

    def check(
        self, key: str, rule: RateLimitRule, now: Optional[float] = None
    ) -> RateLimitResult:
        return _shared_unavailable(rule, now if now is not None else time.time())

    def reset(self, key: str) -> None:
        raise RuntimeError("Shared quota storage is unavailable")


class RedisRateLimiterBackend:
    """Atomic Redis fixed-window counters shared by all app replicas.

    With require_shared=True Redis errors block *all* limited requests.
    Local development can opt into historical memory fallback without
    weakening production. This class never clears Redis keys on outage.
    """

    def __init__(self, redis_url: str, require_shared: bool = False) -> None:
        import redis as _redis  # lazy import, no network call at construction
        self._client = _redis.from_url(
            redis_url, socket_connect_timeout=1, socket_timeout=1,
        )
        self._require_shared = require_shared
        self._fallback = (
            None if require_shared else InMemoryRateLimiterBackend()
        )
        self._redis_ok = True

    def check(
        self, key: str, rule: RateLimitRule, now: Optional[float] = None
    ) -> RateLimitResult:
        now = now if now is not None else time.time()
        try:
            count, ttl = self._client.eval(
                _REDIS_FIXED_WINDOW_LUA, 1, key, rule.window_seconds,
            )
            count, ttl = int(count), int(ttl)
            if count < 1 or ttl < 1:
                raise ValueError("Redis counter or TTL was invalid")
            remaining = max(0, rule.limit - count)
            if not self._redis_ok:
                log.info("rate_limit_redis_recovered")
                self._redis_ok = True
            return RateLimitResult(
                allowed=count <= rule.limit,
                remaining=remaining,
                limit=rule.limit,
                retry_after_seconds=0 if count <= rule.limit else max(1, ttl),
                reset_at=now + ttl,
                backend="redis",
                error_code=rule.error_code if count > rule.limit else None,
            )
        except Exception as exc:
            if self._redis_ok:
                # Neither keys nor Redis URLs are logged (privacy/secrets).
                log.error(
                    "rate_limit_redis_unavailable error_type=%s strict=%s",
                    type(exc).__name__, self._require_shared,
                )
                self._redis_ok = False
            if self._require_shared:
                return _shared_unavailable(rule, now)
            return self._fallback.check(key, rule, now)

    def reset(self, key: str) -> None:
        try:
            self._client.delete(key)
        except Exception:
            if self._require_shared:
                raise RuntimeError("Shared quota reset unavailable") from None
            self._fallback.reset(key)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class RateLimiterService:
    """Thin service wrapper over a backend."""

    def __init__(self, backend) -> None:
        self._backend = backend

    def check_limit(self, key: str, rule: RateLimitRule, now: Optional[float] = None) -> RateLimitResult:
        return self._backend.check(key, rule, now)

    def reset_limit(self, key: str) -> None:
        self._backend.reset(key)

    @property
    def backend_name(self) -> str:
        return getattr(self._backend, "__class__", type(self._backend)).__name__


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_service: Optional[RateLimiterService] = None
_service_lock = threading.Lock()


def get_rate_limiter_service() -> RateLimiterService:
    """Return the singleton rate-limiter service.

    Production or RATE_LIMIT_REQUIRE_SHARED=1 requires shared Redis.
    Missing Redis, initialization errors, and runtime outage all deny requests.
    In local development or tests, process-local memory may be used.
    """
    global _service
    if _service is not None:
        return _service

    with _service_lock:
        if _service is not None:
            return _service

        test_mode = os.environ.get("TEST_MODE", "0") == "1"
        redis_url = os.environ.get("REDIS_URL", "").strip()
        strict = _shared_storage_required()

        if redis_url and (strict or not test_mode):
            try:
                backend = RedisRateLimiterBackend(
                    redis_url, require_shared=strict,
                )
                log.info("rate_limit_redis_configured strict=%s", strict)
                _service = RateLimiterService(backend)
                return _service
            except Exception as exc:
                log.error(
                    "rate_limit_redis_init_failed error_type=%s strict=%s",
                    type(exc).__name__, strict,
                )

        if strict:
            # Never create a per-process quota silo in Production.
            log.error("rate_limit_shared_storage_required_but_unavailable")
            _service = RateLimiterService(UnavailableRateLimiterBackend())
            return _service

        log.info(
            "rate_limit_in_memory_local_only test_mode=%s redis_configured=%s",
            test_mode, bool(redis_url),
        )
        _service = RateLimiterService(InMemoryRateLimiterBackend())
        return _service


def _reset_service_singleton() -> None:
    """Test helper — reset the singleton so tests get a fresh instance."""
    global _service
    _service = None
