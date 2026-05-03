"""Unit tests for in-memory TTL cache."""
import time
import pytest
from app.api.services.cache_service import (
    cache_get, cache_set, cache_delete, cache_clear_prefix, cache_stats, _cache
)


def setup_function():
    _cache.clear()


def test_set_and_get():
    cache_set("key1", {"value": 42}, ttl=60)
    result = cache_get("key1")
    assert result == {"value": 42}


def test_ttl_expiry(monkeypatch):
    cache_set("key_expire", "hello", ttl=1)
    monkeypatch.setattr(time, "time", lambda: time.time.__wrapped__() + 2 if hasattr(time.time, "__wrapped__") else time.monotonic() + 2)
    # Simulate expiry by manually backdating the entry
    _cache["key_expire"]["expires"] = time.time() - 1
    result = cache_get("key_expire")
    assert result is None


def test_cache_delete():
    cache_set("del_key", "data", ttl=60)
    cache_delete("del_key")
    assert cache_get("del_key") is None


def test_cache_clear_prefix():
    cache_set("approval_stats:tenant1:v1", 1, ttl=60)
    cache_set("approval_stats:tenant1:v2", 2, ttl=60)
    cache_set("dashboard_live:tenant1:pnl", 3, ttl=60)
    cache_clear_prefix("approval_stats:tenant1")
    assert cache_get("approval_stats:tenant1:v1") is None
    assert cache_get("approval_stats:tenant1:v2") is None
    assert cache_get("dashboard_live:tenant1:pnl") == 3


def test_cache_miss_returns_none():
    assert cache_get("nonexistent_key") is None


def test_cache_stats():
    cache_set("s1", 1, ttl=60)
    cache_set("s2", 2, ttl=60)
    stats = cache_stats()
    assert stats["total_keys"] >= 2
    assert "s1" in stats["keys"]
    assert "s2" in stats["keys"]


def test_overwrite():
    cache_set("ow", "first", ttl=60)
    cache_set("ow", "second", ttl=60)
    assert cache_get("ow") == "second"


def test_expired_entry_removed_from_cache():
    cache_set("cleanup", "val", ttl=1)
    _cache["cleanup"]["expires"] = time.time() - 1
    cache_get("cleanup")  # triggers deletion
    assert "cleanup" not in _cache
