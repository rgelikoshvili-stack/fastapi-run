"""tests/unit/test_tenant_config_service.py

Tests for tenant_config_service: get_tenant_setting, ensure_tenant_settings_table,
and the approval_service confidence-threshold constants.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# ── ensure_tenant_settings_table ─────────────────────────────────────────────

def test_ensure_table_creates_if_not_exists():
    """ensure_tenant_settings_table commits without raising on a clean connection."""
    from app.api.services.tenant_config_service import ensure_tenant_settings_table

    cur = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cur

    ensure_tenant_settings_table(conn)

    cur.execute.assert_called_once()
    conn.commit.assert_called_once()


def test_ensure_table_tolerates_existing_table():
    """ensure_tenant_settings_table must not raise when table already exists."""
    from app.api.services.tenant_config_service import ensure_tenant_settings_table
    import psycopg2

    cur = MagicMock()
    cur.execute.side_effect = Exception("table already exists")
    conn = MagicMock()
    conn.cursor.return_value = cur

    # must not raise
    ensure_tenant_settings_table(conn)
    conn.rollback.assert_called_once()


# ── get_tenant_setting ────────────────────────────────────────────────────────

def _make_mock_conn(row):
    """Build an async-context-manager mock for get_conn() returning *row*."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=row)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def test_get_tenant_setting_returns_default_when_row_missing():
    """get_tenant_setting returns the default value when no row exists."""
    from app.api.services.tenant_config_service import get_tenant_setting

    with patch("app.api.services.tenant_config_service.get_conn",
               return_value=_make_mock_conn(None)):
        result = asyncio.run(get_tenant_setting("tenant-a", "approval.cfo_threshold_gel", 10000.0))

    assert result == 10000.0


def test_get_tenant_setting_returns_stored_value():
    """get_tenant_setting returns the stored JSONB value when a row exists."""
    from app.api.services.tenant_config_service import get_tenant_setting

    row = {"value_json": 15000.0}
    with patch("app.api.services.tenant_config_service.get_conn",
               return_value=_make_mock_conn(row)):
        result = asyncio.run(get_tenant_setting("tenant-a", "approval.cfo_threshold_gel", 10000.0))

    assert result == 15000.0


def test_get_tenant_setting_returns_default_on_db_error():
    """get_tenant_setting returns the default value when DB raises."""
    from app.api.services.tenant_config_service import get_tenant_setting

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(side_effect=RuntimeError("connection refused"))
    cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.api.services.tenant_config_service.get_conn", return_value=cm):
        result = asyncio.run(get_tenant_setting("tenant-a", "approval.cfo_threshold_gel", 10000.0))

    assert result == 10000.0, "Must fall back to default when DB is unavailable"


def test_get_tenant_setting_handles_string_json():
    """get_tenant_setting handles when asyncpg returns JSONB as a raw JSON string."""
    from app.api.services.tenant_config_service import get_tenant_setting

    row = {"value_json": '{"amount": 20000}'}
    with patch("app.api.services.tenant_config_service.get_conn",
               return_value=_make_mock_conn(row)):
        result = asyncio.run(get_tenant_setting("tenant-a", "some.key", {}))

    assert result == {"amount": 20000}


# ── Confidence threshold constants ────────────────────────────────────────────

def test_confidence_constants_have_expected_defaults():
    """Confidence threshold module-level constants must equal documented defaults."""
    from app.api.services.approval_service import (
        CONFIDENCE_THRESHOLD_HIGH_RISK,
        CONFIDENCE_THRESHOLD_LOW_RISK,
        CONFIDENCE_THRESHOLD_DEFAULT,
        HIGH_RISK_AMOUNT_GEL,
        LOW_RISK_AMOUNT_GEL,
        CFO_APPROVAL_THRESHOLD_DEFAULT,
    )
    assert CONFIDENCE_THRESHOLD_HIGH_RISK  == 0.95
    assert CONFIDENCE_THRESHOLD_LOW_RISK   == 0.75
    assert CONFIDENCE_THRESHOLD_DEFAULT    == 0.85
    assert HIGH_RISK_AMOUNT_GEL            == 1000.0
    assert LOW_RISK_AMOUNT_GEL             == 50.0
    assert CFO_APPROVAL_THRESHOLD_DEFAULT  == 10000.0


def test_effective_threshold_uses_named_constants():
    """effective_threshold must return the named constant values, not raw literals."""
    from app.api.services.approval_service import (
        effective_threshold,
        CONFIDENCE_THRESHOLD_HIGH_RISK,
        CONFIDENCE_THRESHOLD_LOW_RISK,
        CONFIDENCE_THRESHOLD_DEFAULT,
        HIGH_RISK_AMOUNT_GEL,
        LOW_RISK_AMOUNT_GEL,
    )
    assert effective_threshold(HIGH_RISK_AMOUNT_GEL + 1) == CONFIDENCE_THRESHOLD_HIGH_RISK
    assert effective_threshold(LOW_RISK_AMOUNT_GEL  - 1) == CONFIDENCE_THRESHOLD_LOW_RISK
    assert effective_threshold(500.0)                    == CONFIDENCE_THRESHOLD_DEFAULT


# ── CFO threshold default doc guard ──────────────────────────────────────────

def test_cfo_threshold_default_matches_historic_value():
    """CFO_APPROVAL_THRESHOLD_DEFAULT must remain 10000.0 (change requires migration + notice)."""
    from app.api.services.approval_service import CFO_APPROVAL_THRESHOLD_DEFAULT
    assert CFO_APPROVAL_THRESHOLD_DEFAULT == 10000.0, (
        "Changing CFO threshold default requires a migration note and stakeholder sign-off"
    )
