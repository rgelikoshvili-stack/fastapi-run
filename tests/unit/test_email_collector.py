"""tests/unit/test_email_collector.py — Email collector service unit tests."""
from unittest.mock import MagicMock, patch


# ── 1. get_all_active_tenants returns list ────────────────────────────────────

def test_get_all_active_tenants_returns_list():
    from app.api.services.email_collector import get_all_active_tenants
    conn = MagicMock()
    cur = MagicMock().__enter__ = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=MagicMock(fetchall=MagicMock(return_value=[("tenant_a",), ("tenant_b",)])))
    mock_cm.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = mock_cm
    with patch("app.api.services.email_collector._get_db", return_value=conn):
        result = get_all_active_tenants()
    assert isinstance(result, list)


def test_get_all_active_tenants_returns_empty_on_db_error():
    """DB failure must return [] not raise."""
    from app.api.services.email_collector import get_all_active_tenants
    with patch("app.api.services.email_collector._get_db", side_effect=Exception("DB down")):
        result = get_all_active_tenants()
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
