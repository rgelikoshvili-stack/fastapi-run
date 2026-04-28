"""app/api/services/idempotency_service.py
Idempotency key support for approval + posting endpoints.

Usage in route:
    key = request.headers.get("X-Idempotent-Key")
    if key:
        hit = idempotency_check(tenant_id, key, "approve")
        if hit is not None:
            return hit
    result = ... do work ...
    if key:
        idempotency_store(tenant_id, key, "approve", result)
    return result
"""
import json
import logging
from typing import Optional

from app.api.db import get_db

log = logging.getLogger(__name__)


def idempotency_check(tenant_id: str, key: str, endpoint: str) -> Optional[dict]:
    """Return cached response dict if key already seen, else None."""
    try:
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT response_json FROM idempotency_keys
                WHERE tenant_id = %s AND idempotent_key = %s AND endpoint = %s
                LIMIT 1
                """,
                (tenant_id, key, endpoint),
            )
            row = cur.fetchone()
            if row:
                log.info("idempotency_hit tenant=%s key=%s endpoint=%s", tenant_id, key, endpoint)
                return row[0]  # psycopg2 returns JSONB as dict
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        log.warning("idempotency_check failed (non-fatal): %s", e)
    return None


def idempotency_store(tenant_id: str, key: str, endpoint: str, response: dict) -> None:
    """Persist response so future identical keys return the same result."""
    try:
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO idempotency_keys (tenant_id, idempotent_key, endpoint, response_json)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tenant_id, idempotent_key, endpoint) DO NOTHING
                """,
                (tenant_id, key, endpoint, json.dumps(response)),
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        log.warning("idempotency_store failed (non-fatal): %s", e)
