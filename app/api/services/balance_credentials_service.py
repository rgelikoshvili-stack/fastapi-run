"""app/api/services/balance_credentials_service.py
Bridge Hub — Per-tenant Balance.ge credentials (Task 3)
Each tenant can have their own BALANCE_API_KEY + COMPANY_ID stored in DB.
Falls back to global env vars if no per-tenant record exists.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

log = logging.getLogger(__name__)


def _get_db():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not configured")
    return psycopg2.connect(url)


def ensure_table():
    """Create table if not exists — called at startup."""
    conn = _get_db()
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


def get_balance_credentials(tenant_id: str) -> dict:
    """
    Return Balance.ge credentials for this tenant.
    Priority: DB record → global env vars.
    """
    try:
        conn = _get_db()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT api_key, company_id, api_base FROM tenant_balance_credentials "
                "WHERE tenant_id = %s AND active = TRUE",
                (tenant_id,),
            )
            row = cur.fetchone()
        conn.close()
        if row:
            return {
                "api_key": row["api_key"],
                "company_id": row["company_id"] or "",
                "api_base": row["api_base"] or "https://api.balance.ge",
                "source": "db",
            }
    except Exception as e:
        log.warning("get_balance_credentials DB: %s", e)

    # Fall back to global env vars
    api_key = os.environ.get("BALANCE_API_KEY", "")
    if api_key:
        return {
            "api_key": api_key,
            "company_id": os.environ.get("BALANCE_COMPANY_ID", ""),
            "api_base": os.environ.get("BALANCE_API_BASE", "https://api.balance.ge"),
            "source": "env",
        }
    return {"api_key": "", "company_id": "", "api_base": "https://api.balance.ge", "source": "none"}


def save_balance_credentials(
    tenant_id: str,
    api_key: str,
    company_id: str = "",
    api_base: str = "https://api.balance.ge",
) -> bool:
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tenant_balance_credentials
                    (tenant_id, api_key, company_id, api_base, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id) DO UPDATE
                    SET api_key = EXCLUDED.api_key,
                        company_id = EXCLUDED.company_id,
                        api_base = EXCLUDED.api_base,
                        active = TRUE,
                        updated_at = EXCLUDED.updated_at
                """,
                (tenant_id, api_key, company_id, api_base, datetime.now(timezone.utc)),
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        log.error("save_balance_credentials: %s", e)
        return False


def get_credentials_status(tenant_id: str) -> dict:
    """Return status summary for settings UI."""
    creds = get_balance_credentials(tenant_id)
    configured = bool(creds.get("api_key"))
    return {
        "configured": configured,
        "source": creds.get("source", "none"),
        "company_id": creds.get("company_id", ""),
        "api_base": creds.get("api_base", ""),
        "mode": "live" if configured else "demo",
    }
