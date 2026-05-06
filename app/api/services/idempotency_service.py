"""app/api/services/idempotency_service.py
Idempotency key support for approval + posting endpoints.

Usage in route:
    key = request.headers.get("X-Idempotent-Key")
    if key:
        hit = await idempotency_check(tenant_id, key, "approve")
        if hit is not None:
            return hit
    result = ... do work ...
    if key:
        await idempotency_store(tenant_id, key, "approve", result)
    return result
"""
import json
import logging
from typing import Optional

from app.api.db import get_conn, _q

log = logging.getLogger(__name__)


async def idempotency_check(tenant_id: str, key: str, endpoint: str) -> Optional[dict]:
    """Return cached response dict if key already seen, else None."""
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(_q("""
                SELECT response_json FROM idempotency_keys
                WHERE tenant_id = %s AND idempotent_key = %s AND endpoint = %s
                LIMIT 1
            """), tenant_id, key, endpoint)
            if row:
                log.info("idempotency_hit tenant=%s key=%s endpoint=%s", tenant_id, key, endpoint)
                val = row["response_json"]
                return val if isinstance(val, dict) else json.loads(val)
    except Exception as e:
        log.warning("idempotency_check failed (non-fatal): %s", e)
    return None


async def idempotency_store(tenant_id: str, key: str, endpoint: str, response: dict) -> None:
    """Persist response so future identical keys return the same result."""
    try:
        async with get_conn() as conn:
            await conn.execute(_q("""
                INSERT INTO idempotency_keys (tenant_id, idempotent_key, endpoint, response_json)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tenant_id, idempotent_key, endpoint) DO NOTHING
            """), tenant_id, key, endpoint, json.dumps(response))
    except Exception as e:
        log.warning("idempotency_store failed (non-fatal): %s", e)
