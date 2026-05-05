"""app/api/services/cache_service.py — Simple in-memory TTL cache for Cloud Run single-instance."""
import time
from typing import Any, Optional

_cache: dict = {}

CACHE_TTL = {
    "dashboard_live":    30,
    "dashboard_kpis":    60,
    "coa_list":          300,
    "exchange_rates":    86400,
    "approval_stats":    60,
    "learning_patterns": 300,
    "tenant_info":       600,
    "counterparties":    120,
}


def cache_get(key: str) -> Optional[Any]:
    entry = _cache.get(key)
    if not entry:
        return None
    if time.time() > entry["expires"]:
        del _cache[key]
        return None
    return entry["value"]


def cache_set(key: str, value: Any, ttl: int) -> None:
    _cache[key] = {"value": value, "expires": time.time() + ttl}


def cache_delete(key: str) -> None:
    _cache.pop(key, None)


def cache_clear_prefix(prefix: str) -> None:
    keys = [k for k in list(_cache) if k.startswith(prefix)]
    for k in keys:
        _cache.pop(k, None)


async def cached(key: str, ttl: int, loader):
    """Async read-through helper: return cached value or call loader() and cache result."""
    hit = cache_get(key)
    if hit is not None:
        return hit
    value = await loader()
    cache_set(key, value, ttl)
    return value


def cache_stats() -> dict:
    now = time.time()
    alive = {k: v for k, v in _cache.items() if v["expires"] > now}
    return {"total_keys": len(alive), "keys": list(alive.keys())}
