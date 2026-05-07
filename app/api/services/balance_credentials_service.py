"""app/api/services/balance_credentials_service.py
Bridge Hub — Per-tenant Balance.ge credentials (Task 3)
Each tenant can have their own BALANCE_API_KEY + COMPANY_ID stored in DB.
Falls back to global env vars if no per-tenant record exists.
"""
import logging
import os
import psycopg2
from datetime import datetime, timezone
from typing import Optional

from app.api.db import get_conn, _q

log = logging.getLogger(__name__)


def ensure_table():
    """Create table if not exists — called at startup."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        return
    conn = psycopg2.connect(url)
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tenant_balance_credentials (
                id          SERIAL PRIMARY KEY,
                tenant_id   TEXT NOT NULL UNIQUE,
                api_key     TEXT NOT NULL,
                company_id  TEXT,
                api_base    TEXT DEFAULT 'https://api.balance.ge',
                active      BOOLEAN DEFAULT TRUE,
                created_at  TIMESTAMPTZ DEFAULT NOW(),
                updated_at  TIMESTAMPTZ DEFAULT NOW()
            );
        """)
    conn.commit()
    conn.close()


async def get_balance_credentials(tenant_id: str) -> dict:
    """
    Return Balance.ge credentials for this tenant.
    Priority: DB record → global env vars.
    """
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(_q(
                "SELECT api_key, company_id, api_base FROM tenant_balance_credentials "
                "WHERE tenant_id = %s AND active = TRUE"
            ), tenant_id)
        if row:
            return {
                "api_key": row["api_key"],
                "company_id": row["company_id"] or "",
                "api_base": row["api_base"] or "https://api.balance.ge",
                "source": "db",
            }
    except Exception as e:
        log.warning("get_balance_credentials DB: %s", e)

    api_key = os.environ.get("BALANCE_API_KEY", "")
    if api_key:
        return {
            "api_key": api_key,
            "company_id": os.environ.get("BALANCE_COMPANY_ID", ""),
            "api_base": os.environ.get("BALANCE_API_BASE", "https://api.balance.ge"),
            "source": "env",
        }
    return {"api_key": "", "company_id": "", "api_base": "https://api.balance.ge", "source": "none"}


async def save_balance_credentials(
    tenant_id: str,
    api_key: str,
    company_id: str = "",
    api_base: str = "https://api.balance.ge",
) -> bool:
    try:
        async with get_conn() as conn:
            await conn.execute(_q("""
                INSERT INTO tenant_balance_credentials
                    (tenant_id, api_key, company_id, api_base, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id) DO UPDATE
                    SET api_key = EXCLUDED.api_key,
                        company_id = EXCLUDED.company_id,
                        api_base = EXCLUDED.api_base,
                        active = TRUE,
                        updated_at = EXCLUDED.updated_at
            """), tenant_id, api_key, company_id, api_base, datetime.now(timezone.utc))
        return True
    except Exception as e:
        log.error("save_balance_credentials: %s", e)
        return False


async def get_credentials_status(tenant_id: str) -> dict:
    """Return status summary for settings UI."""
    creds = await get_balance_credentials(tenant_id)
    configured = bool(creds.get("api_key"))
    return {
        "configured": configured,
        "source": creds.get("source", "none"),
        "company_id": creds.get("company_id", ""),
        "api_base": creds.get("api_base", ""),
        "mode": "live" if configured else "demo",
    }
