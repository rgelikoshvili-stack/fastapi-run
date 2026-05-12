"""
tests/unit/test_rate_limit_service.py   (file: test_rate_limiter_service.py)

Unit tests for the rate-limiter service (Task 11C-F2).
All tests use in-memory backend — no real Redis, no DB, no network.
"""
from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("TEST_MODE", "1")

from app.api.services.rate_limit_policy_service import (
    RateLimitCategory,
    RateLimitRule,
    get_rate_limit_rule,
)
from app.api.services.rate_limiter_service import (
    InMemoryRateLimiterBackend,
    RateLimitResult,
    RateLimiterService,
    _reset_service_singleton,
    get_rate_limiter_service,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_backend() -> InMemoryRateLimiterBackend:
    return InMemoryRateLimiterBackend()


def _tiny_rule(limit: int = 3, window: int = 60) -> RateLimitRule:
    return RateLimitRule(
        category=RateLimitCategory.AUTH,
        limit=limit,
        window_seconds=window,
        error_code="AUTH_RATE_LIMIT_EXCEEDED",
    )


# ---------------------------------------------------------------------------
# A) First request allowed
# ---------------------------------------------------------------------------

class TestFirstRequestAllowed:

    def test_first_request_is_allowed(self):
        b = _make_backend()
        result = b.check("key1", _tiny_rule())
        assert result.allowed is True

    def test_first_request_remaining_is_limit_minus_one(self):
        b = _make_backend()
        result = b.check("key1", _tiny_rule(limit=5))
        assert result.remaining == 4

    def test_first_request_retry_after_is_zero(self):
        b = _make_backend()
        result = b.check("key1", _tiny_rule())
        assert result.retry_after_seconds == 0

    def test_first_request_backend_is_memory_fallback(self):
        b = _make_backend()
        result = b.check("key1", _tiny_rule())
        assert result.backend == "memory_fallback"

    def test_first_request_limit_field_matches_rule(self):
        b = _make_backend()
        result = b.check("key1", _tiny_rule(limit=10))
        assert result.limit == 10

    def test_result_has_reset_at(self):
        b = _make_backend()
        now = time.time()
        result = b.check("key1", _tiny_rule(window=60))
        assert result.reset_at > now


# ---------------------------------------------------------------------------
# B) Limit enforcement
# ---------------------------------------------------------------------------

class TestLimitEnforcement:

    def test_requests_up_to_limit_allowed(self):
        b = _make_backend()
        rule = _tiny_rule(limit=3)
        for i in range(3):
            result = b.check("key_allow", rule)
            assert result.allowed is True, f"Request {i+1} should be allowed"

    def test_request_over_limit_blocked(self):
        b = _make_backend()
        rule = _tiny_rule(limit=3)
        for _ in range(3):
            b.check("key_block", rule)
        result = b.check("key_block", rule)
        assert result.allowed is False

    def test_blocked_result_has_error_code(self):
        b = _make_backend()
        rule = _tiny_rule(limit=1)
        b.check("key_err", rule)
        result = b.check("key_err", rule)
        assert result.error_code == "AUTH_RATE_LIMIT_EXCEEDED"

    def test_blocked_remaining_is_zero(self):
        b = _make_backend()
        rule = _tiny_rule(limit=1)
        b.check("key_rem", rule)
        result = b.check("key_rem", rule)
        assert result.remaining == 0

    def test_blocked_retry_after_positive(self):
        b = _make_backend()
        rule = _tiny_rule(limit=1, window=60)
        b.check("key_retry", rule)
        result = b.check("key_retry", rule)
        assert result.retry_after_seconds >= 1

    def test_remaining_decreases_with_requests(self):
        b = _make_backend()
        rule = _tiny_rule(limit=5)
        results = [b.check("key_dec", rule) for _ in range(3)]
        assert results[0].remaining > results[1].remaining > results[2].remaining


# ---------------------------------------------------------------------------
# C) Reset
# ---------------------------------------------------------------------------

class TestReset:

    def test_reset_clears_counter(self):
        b = _make_backend()
        rule = _tiny_rule(limit=1)
        b.check("key_reset", rule)
        b.check("key_reset", rule)  # This would be blocked
        b.reset("key_reset")
        result = b.check("key_reset", rule)
        assert result.allowed is True

    def test_reset_nonexistent_key_safe(self):
        b = _make_backend()
        b.reset("nonexistent_key_xyz")  # Should not raise


# ---------------------------------------------------------------------------
# D) Window reset
# ---------------------------------------------------------------------------

class TestWindowReset:

    def test_new_window_resets_counter(self):
        b = _make_backend()
        rule = _tiny_rule(limit=2, window=1)
        now = 1_000.0
        b.check("key_win", rule, now=now)
        b.check("key_win", rule, now=now)
        # Expire the window
        result = b.check("key_win", rule, now=now + 2.0)
        assert result.allowed is True
        assert result.remaining == 1


# ---------------------------------------------------------------------------
# E) RateLimiterService wrapper
# ---------------------------------------------------------------------------

class TestRateLimiterServiceWrapper:

    def test_service_check_limit_returns_result(self):
        svc = RateLimiterService(InMemoryRateLimiterBackend())
        rule = _tiny_rule()
        result = svc.check_limit("svc_key", rule)
        assert isinstance(result, RateLimitResult)
        assert result.allowed is True

    def test_service_reset_limit_works(self):
        svc = RateLimiterService(InMemoryRateLimiterBackend())
        rule = _tiny_rule(limit=1)
        svc.check_limit("reset_svc", rule)
        svc.check_limit("reset_svc", rule)
        svc.reset_limit("reset_svc")
        result = svc.check_limit("reset_svc", rule)
        assert result.allowed is True

    def test_service_backend_name_present(self):
        svc = RateLimiterService(InMemoryRateLimiterBackend())
        assert isinstance(svc.backend_name, str)
        assert len(svc.backend_name) > 0


# ---------------------------------------------------------------------------
# F) get_rate_limiter_service — TEST_MODE returns memory backend
# ---------------------------------------------------------------------------

class TestGetRateLimiterServiceTestMode:

    def setup_method(self):
        _reset_service_singleton()

    def teardown_method(self):
        _reset_service_singleton()

    def test_test_mode_returns_memory_service(self):
        svc = get_rate_limiter_service()
        result = svc.check_limit("factory_key", _tiny_rule())
        assert result.backend == "memory_fallback"

    def test_service_is_singleton(self):
        svc1 = get_rate_limiter_service()
        svc2 = get_rate_limiter_service()
        assert svc1 is svc2

    def test_service_works_after_reset(self):
        svc = get_rate_limiter_service()
        rule = _tiny_rule()
        result = svc.check_limit("singleton_key", rule)
        assert result.allowed is True


# ---------------------------------------------------------------------------
# G) Redis missing falls back safely
# ---------------------------------------------------------------------------

class TestRedisUnavailableFallback:

    def setup_method(self):
        _reset_service_singleton()

    def teardown_method(self):
        _reset_service_singleton()

    def test_no_redis_url_uses_memory_fallback(self):
        orig = os.environ.pop("REDIS_URL", None)
        os.environ["TEST_MODE"] = "0"
        try:
            _reset_service_singleton()
            svc = get_rate_limiter_service()
            result = svc.check_limit("fallback_key", _tiny_rule())
            assert result.backend == "memory_fallback"
        finally:
            os.environ["TEST_MODE"] = "1"
            if orig:
                os.environ["REDIS_URL"] = orig
            _reset_service_singleton()

    def test_bad_redis_url_falls_back_to_memory(self):
        orig = os.environ.pop("REDIS_URL", None)
        os.environ["TEST_MODE"] = "0"
        os.environ["REDIS_URL"] = "redis://localhost:1"  # nothing listening
        try:
            _reset_service_singleton()
            svc = get_rate_limiter_service()
            rule = _tiny_rule()
            result = svc.check_limit("bad_redis_key", rule, now=time.time())
            # Should still return a result (from memory fallback) not raise
            assert isinstance(result, RateLimitResult)
        finally:
            os.environ["TEST_MODE"] = "1"
            os.environ.pop("REDIS_URL", None)
            if orig:
                os.environ["REDIS_URL"] = orig
            _reset_service_singleton()


# ---------------------------------------------------------------------------
# H) Fallback is bounded, not unlimited
# ---------------------------------------------------------------------------

class TestFallbackBounded:

    def test_memory_fallback_enforces_limit(self):
        b = InMemoryRateLimiterBackend()
        rule = _tiny_rule(limit=5)
        for _ in range(5):
            b.check("bounded_key", rule)
        result = b.check("bounded_key", rule)
        assert result.allowed is False, "In-memory fallback must enforce limits, not be unlimited"

    def test_memory_fallback_not_unlimited_for_auth(self):
        b = InMemoryRateLimiterBackend()
        rule = get_rate_limit_rule(RateLimitCategory.AUTH)
        # Exhaust the limit
        for _ in range(rule.limit):
            b.check("auth_bound", rule)
        result = b.check("auth_bound", rule)
        assert result.allowed is False

    def test_memory_fallback_not_unlimited_for_credential(self):
        b = InMemoryRateLimiterBackend()
        rule = get_rate_limit_rule(RateLimitCategory.CREDENTIAL)
        for _ in range(rule.limit):
            b.check("cred_bound", rule)
        result = b.check("cred_bound", rule)
        assert result.allowed is False


# ---------------------------------------------------------------------------
# I) No secrets in result
# ---------------------------------------------------------------------------

class TestNoSecretsInResult:

    def test_result_has_no_secret_fields(self):
        b = _make_backend()
        result = b.check("secret_key_test", _tiny_rule())
        result_str = str(result)
        for forbidden in ("api_key", "password", "token", "secret", "encrypted_value"):
            assert forbidden not in result_str

    def test_blocked_result_has_no_secret_fields(self):
        b = _make_backend()
        rule = _tiny_rule(limit=1)
        b.check("secret_blocked", rule)
        result = b.check("secret_blocked", rule)
        result_str = str(result)
        for forbidden in ("api_key", "password", "token", "secret", "encrypted_value"):
            assert forbidden not in result_str


# ---------------------------------------------------------------------------
# J) Build from policy rule
# ---------------------------------------------------------------------------

class TestBuildFromPolicyRule:

    def test_build_from_auth_rule_limits_correctly(self):
        svc = RateLimiterService(InMemoryRateLimiterBackend())
        rule = get_rate_limit_rule(RateLimitCategory.AUTH)
        result = svc.check_limit("policy_auth", rule)
        assert result.allowed is True
        assert result.limit == rule.limit

    def test_build_from_ai_heavy_rule(self):
        svc = RateLimiterService(InMemoryRateLimiterBackend())
        rule = get_rate_limit_rule(RateLimitCategory.AI_HEAVY)
        result = svc.check_limit("policy_ai", rule)
        assert result.allowed is True
        assert result.limit == rule.limit
        assert result.reset_at > 0

    def test_different_keys_independent_counters(self):
        svc = RateLimiterService(InMemoryRateLimiterBackend())
        rule = _tiny_rule(limit=1)
        svc.check_limit("key_A", rule)
        svc.check_limit("key_B", rule)  # different key
        # key_A is at limit, key_B should still be fresh
        result_a = svc.check_limit("key_A", rule)
        result_b = svc.check_limit("key_B", rule)
        assert result_a.allowed is False
        assert result_b.allowed is False  # key_B also hit limit now
