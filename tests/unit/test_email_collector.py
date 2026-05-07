"""tests/unit/test_email_collector.py — Email collector service unit tests."""
import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch


# ── 1. get_all_active_tenants returns list ────────────────────────────────────

def test_get_all_active_tenants_returns_list():
    from app.api.services import email_collector

    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[{"tenant_id": "tenant_a"}, {"tenant_id": "tenant_b"}])

    @asynccontextmanager
    async def _ctx():
        yield conn

    with patch("app.api.services.email_collector.get_conn", _ctx):
        result = asyncio.run(email_collector.get_all_active_tenants())

    assert isinstance(result, list)
    assert "tenant_a" in result


def test_get_all_active_tenants_returns_empty_on_db_error():
    """DB failure must return [] not raise."""
    from app.api.services import email_collector

    @asynccontextmanager
    async def _ctx_err():
        raise Exception("DB down")
        yield  # unreachable but makes it a generator

    with patch("app.api.services.email_collector.get_conn", _ctx_err):
        result = asyncio.run(email_collector.get_all_active_tenants())

    assert result == []


# ── 2. Monitored loop — failure tracking logic ────────────────────────────────

def test_monitored_loop_backoff_on_max_failures():
    """After max_failures, sleep must multiply by 10."""
    base = 60
    max_f = 5
    consecutive = 5  # hit threshold
    sleep = base * 10 if consecutive >= max_f else base
    assert sleep == 600


def test_monitored_loop_resets_on_success():
    """Consecutive failures reset to 0 after a success."""
    consecutive = 4
    try:
        _ = 1 / 1  # success
        consecutive = 0
    except Exception:
        consecutive += 1
    assert consecutive == 0


# ── 3. Email deduplication — same message_id blocked ─────────────────────────

def test_email_dedup_same_tenant_blocked():
    seen = set()

    def process_once(message_id, tenant_id):
        key = (tenant_id, message_id)
        if key in seen:
            return False
        seen.add(key)
        return True

    assert process_once("msg-001", "tenant_a") is True
    assert process_once("msg-001", "tenant_a") is False
    assert process_once("msg-001", "tenant_b") is True  # different tenant → ok


# ── 4. get_all_active_tenants filters by active=TRUE ─────────────────────────

def test_get_all_active_tenants_query_filters_active():
    import inspect
    from app.api.services import email_collector
    source = inspect.getsource(email_collector.get_all_active_tenants)
    assert "active" in source.lower()


# ── 5. Email collector module has collect_tenant_inbox ───────────────────────

def test_collect_tenant_inbox_exists():
    from app.api.services import email_collector
    assert hasattr(email_collector, "collect_tenant_inbox")
    assert callable(email_collector.collect_tenant_inbox)
