"""app/api/audit.py — Async audit log writer.

log_event() is fire-and-forget: callers use asyncio.ensure_future() so
audit failures never block the main request path.
"""
import asyncio
import json
import logging

from app.api.db import get_conn, _q

log = logging.getLogger(__name__)


async def _log_event_async(
    action: str,
    resource: str,
    resource_id: str = None,
    actor: str = "system",
    role: str = "system",
    old_value: dict = None,
    new_value: dict = None,
    status: str = "success",
    details: str = None,
    tenant_id: str = None,
    ip_address: str = None,
) -> None:
    try:
        async with get_conn() as conn:
            await conn.execute(_q("""
                INSERT INTO audit_log
                (actor, role, action, resource, resource_id, old_value, new_value,
                 ip_address, status, details, tenant_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """),
            actor, role, action, resource,
            str(resource_id) if resource_id else None,
            json.dumps(old_value) if old_value else None,
            json.dumps(new_value) if new_value else None,
            ip_address, status, details,
            str(tenant_id) if tenant_id else None)
    except Exception as e:
        log.warning("audit_log write failed action=%s: %s", action, e)


def log_event(
    action: str,
    resource: str,
    resource_id: str = None,
    actor: str = "system",
    role: str = "system",
    old_value: dict = None,
    new_value: dict = None,
    status: str = "success",
    details: str = None,
    tenant_id: str = None,
    ip_address: str = None,
) -> None:
    """Fire-and-forget audit log. Safe to call from both async and sync contexts."""
    coro = _log_event_async(
        action=action, resource=resource, resource_id=resource_id,
        actor=actor, role=role, old_value=old_value, new_value=new_value,
        status=status, details=details, tenant_id=tenant_id, ip_address=ip_address,
    )
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        # No running loop (sync context) — run directly
        asyncio.run(coro)
