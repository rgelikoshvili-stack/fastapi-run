"""app/api/services/tenant_config_service.py

Thin per-tenant configuration table (tenant_settings).

Schema:
    tenant_settings(tenant_id TEXT, key TEXT, value_json JSONB,
                    created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)
    PRIMARY KEY (tenant_id, key)

Usage:
    threshold = await get_tenant_setting(tenant_id, "approval.cfo_threshold_gel", 10000.0)
    await set_tenant_setting(tenant_id, "approval.cfo_threshold_gel", 15000.0)
"""
import json
import logging
from typing import Any

from app.api.db import get_conn, _q

log = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tenant_settings (
    tenant_id   TEXT NOT NULL,
    key         TEXT NOT NULL,
    value_json  JSONB NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (tenant_id, key)
);
"""


def ensure_tenant_settings_table(conn) -> None:
    """Create the tenant_settings table if it doesn't exist (psycopg2 conn)."""
    cur = conn.cursor()
    try:
        cur.execute(_CREATE_TABLE_SQL)
        conn.commit()
    except Exception as _e:
        conn.rollback()
        log.warning("tenant_settings table migration skipped: %s", _e)
    finally:
        cur.close()


async def get_tenant_setting(tenant_id: str, key: str, default: Any) -> Any:
    """Return the stored value for (tenant_id, key), or *default* if missing / on any error."""
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(
                _q("SELECT value_json FROM tenant_settings WHERE tenant_id = %s AND key = %s"),
                tenant_id, key,
            )
            if row is None:
                return default
            val = row["value_json"]
            # asyncpg returns JSONB as a Python object already
            if isinstance(val, str):
                val = json.loads(val)
            return val
    except Exception as _e:
        log.warning("get_tenant_setting(%s, %s) failed — returning default %r: %s",
                    tenant_id, key, default, _e)
        return default


async def set_tenant_setting(tenant_id: str, key: str, value: Any) -> bool:
    """Upsert (tenant_id, key) → value. Returns True on success."""
    try:
        async with get_conn() as conn:
            await conn.execute(
                _q("""
                    INSERT INTO tenant_settings (tenant_id, key, value_json, updated_at)
                    VALUES (%s, %s, %s::jsonb, NOW())
                    ON CONFLICT (tenant_id, key)
                    DO UPDATE SET value_json = EXCLUDED.value_json, updated_at = NOW()
                """),
                tenant_id, key, json.dumps(value),
            )
        return True
    except Exception as _e:
        log.warning("set_tenant_setting(%s, %s) failed: %s", tenant_id, key, _e)
        return False
