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


def test_cache_ttl_constants_present():
    from app.api.services.cache_service import CACHE_TTL
    assert "dashboard_live" in CACHE_TTL
    assert "dashboard_kpis" in CACHE_TTL
    assert "coa_list" in CACHE_TTL
    assert "exchange_rates" in CACHE_TTL
    assert "approval_stats" in CACHE_TTL
    assert CACHE_TTL["exchange_rates"] == 86400
    assert CACHE_TTL["coa_list"] == 300


# ── health endpoint structural tests ─────────────────────────────────────────

def test_health_fast_endpoint_has_no_db_calls():
    """Fast /health must not call DB — keep it sub-50ms."""
    import inspect
    import app.api.routes_health as mod
    src = inspect.getsource(mod.health_check)
    assert "get_conn" not in src
    assert "fetchrow" not in src
    assert "fetchval" not in src


def test_deep_health_endpoint_exists():
    import app.api.routes_health as mod
    assert callable(getattr(mod, "health_check_deep", None))


def test_health_ping_endpoint_exists():
    import app.api.routes_health as mod
    assert callable(getattr(mod, "ping", None))


def test_health_has_uptime():
    import inspect
    import app.api.routes_health as mod
    assert "uptime" in inspect.getsource(mod.health_check)


def test_deep_health_calls_db():
    import inspect
    import app.api.routes_health as mod
    src = inspect.getsource(mod.health_check_deep)
    assert "get_conn" in src or "_check_db_deep" in src


# ── cached() async helper ─────────────────────────────────────────────────────

def test_cached_helper_calls_loader_on_miss():
    import asyncio
    from app.api.services.cache_service import cached
    _cache.clear()
    calls = []

    async def loader():
        calls.append(1)
        return {"v": 42}

    result = asyncio.run(cached("test:miss", 60, loader))
    assert result == {"v": 42}
    assert len(calls) == 1


def test_cached_helper_returns_cached_value():
    import asyncio
    from app.api.services.cache_service import cached
    _cache.clear()
    cache_set("test:hit", {"v": 99}, ttl=60)
    calls = []

    async def loader():
        calls.append(1)
        return {"v": 0}

    result = asyncio.run(cached("test:hit", 60, loader))
    assert result == {"v": 99}
    assert len(calls) == 0  # loader not called on cache hit


def test_cached_helper_stores_result():
    import asyncio
    from app.api.services.cache_service import cached
    _cache.clear()

    async def loader():
        return {"stored": True}

    asyncio.run(cached("test:store", 60, loader))
    assert cache_get("test:store") == {"stored": True}


# ── approval stats index usability ───────────────────────────────────────────

def test_approval_stats_query_has_no_tenant_cast():
    """tenant_id::text cast prevents index use; query must use plain tenant_id = %s."""
    import inspect
    import app.api.routes_approval as mod
    src = inspect.getsource(mod.get_stats)
    assert "tenant_id::text" not in src, (
        "approval stats query uses tenant_id::text cast which prevents index use"
    )


def test_batch_action_query_has_no_tenant_cast():
    """Batch action query must not cast tenant_id to prevent index skip."""
    import inspect
    import app.api.routes_approval as mod
    src = inspect.getsource(mod.batch_action)
    assert "tenant_id::text" not in src


# ── migrations include all required speed indexes ────────────────────────────

def test_migrations_include_bank_transactions_tenant_created_index():
    import inspect
    import app.startup.migrations as mod
    import app.startup.migrations_indexes as mod_idx
    src = inspect.getsource(mod) + inspect.getsource(mod_idx)
    assert "bank_transactions(tenant_id, created_at" in src or \
           "bank_transactions_tenant_created" in src


def test_migrations_include_pipeline_runs_tenant_created_index():
    import inspect
    import app.startup.migrations as mod
    import app.startup.migrations_indexes as mod_idx
    src = inspect.getsource(mod) + inspect.getsource(mod_idx)
    assert "pipeline_runs(tenant_id, created_at" in src or \
           "pipeline_runs_tenant_created" in src
