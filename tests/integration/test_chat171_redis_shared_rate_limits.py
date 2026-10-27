"""Chat171: real Redis 7 disposable CI tests of two independent quota clients.

Only a dedicated localhost Redis service on port 56379 / database 14 is
permitted; never accept production URLs, credentials or other hosts.
No keyspace-wide FLUSH, no Cloud Run/Cloud SQL, no customer data.
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
import redis

from app.api.services.rate_limiter_service import RedisRateLimiterBackend
from app.api.services.rate_limit_policy_service import (
    RateLimitCategory, RateLimitRule,
)


def _local_disposable_url():
    dsn = os.environ.get("CHAT171_TEST_REDIS_URL", "")
    if not dsn:
        pytest.skip("Only the explicit disposable Chat171 localhost Redis is allowed")
    uri = urlsplit(dsn)
    if (
        uri.scheme != "redis"
        or uri.hostname != "127.0.0.1"
        or uri.port != 56379
        or uri.path != "/14"
        or uri.username is not None
        or uri.password is not None
        or uri.query
        or uri.fragment
    ):
        raise RuntimeError("Refusing to run against non-disposable Redis endpoint")
    return dsn


@pytest.fixture
def disposable_redis():
    dsn = _local_disposable_url()
    client = redis.Redis.from_url(
        dsn, socket_connect_timeout=1, socket_timeout=1,
    )
    assert client.ping() is True
    keys = []

    def new_key():
        key = "rl:chat171:synthetic:" + uuid4().hex
        keys.append(key)
        return key

    try:
        yield dsn, client, new_key
    finally:
        # Only remove our exact synthetic keys, never FLUSHDB.
        if keys:
            client.delete(*keys)
        client.close()


def _rule(limit=20, window=60):
    return RateLimitRule(
        category=RateLimitCategory.AUTH,
        limit=limit,
        window_seconds=window,
        error_code="AUTH_RATE_LIMIT_EXCEEDED",
    )


def test_independent_clients_share_one_atomic_counter_under_concurrency(disposable_redis):
    dsn, client, new_key = disposable_redis
    key = new_key()
    rule = _rule(limit=20, window=60)
    replica_a = RedisRateLimiterBackend(dsn, require_shared=True)
    replica_b = RedisRateLimiterBackend(dsn, require_shared=True)
    assert replica_a._client is not replica_b._client

    def send_request(index):
        limiter = replica_a if index % 2 == 0 else replica_b
        return limiter.check(key, rule)

    with ThreadPoolExecutor(max_workers=20) as workers:
        outcomes = list(workers.map(send_request, range(60)))

    assert len([r for r in outcomes if r.allowed]) == rule.limit
    assert len([r for r in outcomes if not r.allowed]) == 40
    assert {r.backend for r in outcomes} == {"redis"}
    assert all(r.limit == 20 for r in outcomes)
    assert all(r.retry_after_seconds > 0 for r in outcomes if not r.allowed)
    assert int(client.get(key)) == 60
    ttl = client.ttl(key)
    assert 1 <= ttl <= 60  # first request got its TTL atomically


def test_new_key_expires_and_can_reopen_window(disposable_redis):
    dsn, client, new_key = disposable_redis
    key = new_key()
    a = RedisRateLimiterBackend(dsn, require_shared=True)
    b = RedisRateLimiterBackend(dsn, require_shared=True)
    rule = _rule(limit=2, window=1)
    assert a.check(key, rule).allowed
    assert b.check(key, rule).allowed
    assert not a.check(key, rule).allowed
    assert client.ttl(key) <= 1
    time.sleep(1.3)
    assert client.get(key) is None
    again = b.check(key, rule)
    assert again.allowed and again.remaining == 1 and again.backend == "redis"


def test_strict_mode_does_not_reset_shared_quota_on_redis_error(disposable_redis):
    dsn, client, new_key = disposable_redis
    key = new_key()
    a = RedisRateLimiterBackend(dsn, require_shared=True)
    b = RedisRateLimiterBackend(dsn, require_shared=True)
    rule = _rule(limit=2)
    assert a.check(key, rule).allowed
    assert b.check(key, rule).allowed

    class NetworkFailure:
        def eval(self, *_args):
            raise redis.exceptions.ConnectionError("synthetic network outage")

    saved = b._client
    b._client = NetworkFailure()
    try:
        denied = b.check(key, rule)
        assert denied.allowed is False
        assert denied.error_code == "RATE_LIMIT_BACKEND_UNAVAILABLE"
        assert denied.backend == "shared_unavailable"
        # The Redis key/counter must remain untouched during failed requests.
        assert int(client.get(key)) == 2
    finally:
        b._client = saved

    after = a.check(key, rule)
    assert after.allowed is False
    assert after.backend == "redis"
    assert int(client.get(key)) == 3
