"""app/api/services/rate_limiter_service.py

Rate-limiter service with Redis backend (when REDIS_URL is set) and a
safe in-memory fixed-window fallback for TEST_MODE, local dev, and when
Redis is unavailable.

Tests never call real Redis — get_rate_limiter_service() returns the
in-memory backend when TEST_MODE=1 or when REDIS_URL is not configured.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
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
# Redis backend (optional — only used when REDIS_URL is set and redis importable)
# ---------------------------------------------------------------------------

class RedisRateLimiterBackend:
    """Fixed-window rate limiter backed by Redis (sync client, non-async).

    Uses INCR + EXPIRE pipeline for atomic increment.  Falls back to the
    in-memory backend on any Redis error.
    """

    def __init__(self, redis_url: str) -> None:
        import redis as _redis  # lazy import — tested in non-TEST_MODE only
        self._client = _redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
        self._fallback = InMemoryRateLimiterBackend()
        self._redis_ok = True

    def check(self, key: str, rule: RateLimitRule, now: Optional[float] = None) -> RateLimitResult:
        now = now if now is not None else time.time()
        try:
            pipe = self._client.pipeline()
            pipe.incr(key)
            pipe.ttl(key)
            count, ttl = pipe.execute()

            if ttl < 0:
                # Key exists but has no TTL — set it now
                self._client.expire(key, rule.window_seconds)
                ttl = rule.window_seconds

            remaining = max(0, rule.limit - count)
            reset_at = now + ttl

            if not self._redis_ok:
                log.info("Redis rate limiter recovered")
                self._redis_ok = True

            if count > rule.limit:
                retry_after = max(1, ttl)
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    limit=rule.limit,
                    retry_after_seconds=retry_after,
                    reset_at=reset_at,
                    backend="redis",
                    error_code=rule.error_code,
                )

            # First request in new window: set TTL
            if count == 1:
                self._client.expire(key, rule.window_seconds)

            return RateLimitResult(
                allowed=True,
                remaining=remaining,
                limit=rule.limit,
                retry_after_seconds=0,
                reset_at=reset_at,
                backend="redis",
            )

        except Exception as exc:
            if self._redis_ok:
                log.warning(
                    "rate_limit_redis_unavailable key=%s error=%s — falling back to memory",
                    key, exc,
                )
                self._redis_ok = False
            return self._fallback.check(key, rule, now)

    def reset(self, key: str) -> None:
        try:
            self._client.delete(key)
        except Exception:
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

    In TEST_MODE or when REDIS_URL is not set, returns in-memory fallback.
    In production with REDIS_URL set, returns Redis-backed service.
    """
    global _service
    if _service is not None:
        return _service

    with _service_lock:
        if _service is not None:
            return _service

        test_mode = os.environ.get("TEST_MODE", "0") == "1"
        redis_url = os.environ.get("REDIS_URL", "").strip()

        if not test_mode and redis_url:
            try:
                backend = RedisRateLimiterBackend(redis_url)
                log.info("Rate limiter: Redis backend (%s)", redis_url.split("@")[-1])
                _service = RateLimiterService(backend)
                return _service
            except Exception as exc:
                log.warning("Redis rate limiter init failed (%s), using memory fallback", exc)

        log.info("Rate limiter: in-memory fallback (TEST_MODE=%s REDIS_URL=%s)",
                 test_mode, bool(redis_url))
        _service = RateLimiterService(InMemoryRateLimiterBackend())
        return _service


def _reset_service_singleton() -> None:
    """Test helper — reset the singleton so tests get a fresh instance."""
    global _service
    _service = None
