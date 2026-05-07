"""app/api/services/entity_audit_service.py — Entity-level immutable audit trail.

Usage:
    with audit_change(conn, "journal_drafts", draft_id, actor, tenant_id):
        cur.execute("UPDATE journal_drafts SET status=... WHERE id=...")
        conn.commit()

    # Or without context manager:
    log_entity_change(conn, "invoices", 5, old_data, new_data, actor, tenant_id)
"""
import json
import logging
from contextlib import contextmanager
from typing import Optional

log = logging.getLogger(__name__)

# Tables we track — entity_type → (table, pk_column)
_TRACKED = {
    "journal_drafts": ("journal_drafts", "id"),
    "journal_entries": ("journal_entries", "id"),
    "expenses": ("expenses", "id"),
    "invoices": ("invoices", "id"),
    "contracts": ("contracts", "id"),
    "customers": ("customers", "id"),
    "bank_transactions": ("bank_transactions", "id"),
    "fixed_assets": ("fixed_assets", "id"),
    "inventory_items": ("inventory_items", "id"),
    "purchase_orders": ("purchase_orders", "id"),
    "budgets": ("budgets", "id"),
}


def _fetch_entity(cur, table: str, pk_col: str, entity_id, tenant_id: str) -> Optional[dict]:
    try:
        cur.execute(
            f"SELECT * FROM {table} WHERE {pk_col} = %s AND tenant_id = %s",
            (entity_id, tenant_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = [d[0] for d in cur.description]
        data = dict(zip(cols, row))
        # Serialize non-JSON-safe types
        for k, v in data.items():
            if hasattr(v, "isoformat"):
                data[k] = v.isoformat()
            elif isinstance(v, memoryview):
                data[k] = "<binary>"
        return data
    except Exception as e:
        log.debug("audit fetch failed table=%s id=%s: %s", table, entity_id, e)
        return None


def _write_audit(conn, entity_type: str, entity_id, action: str,
                 old_data: Optional[dict], new_data: Optional[dict],
                 actor: str, tenant_id: str, details: str = None):
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO audit_log
                (actor, role, action, resource, resource_id,
                 old_value, new_value, status, details, tenant_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            actor, "system", action, entity_type, str(entity_id),
            json.dumps(old_data, default=str) if old_data else None,
            json.dumps(new_data, default=str) if new_data else None,
            "success", details, tenant_id,
        ))
        cur.close()
    except Exception as e:
        log.warning("audit write failed entity=%s id=%s: %s", entity_type, entity_id, e)


@contextmanager
def audit_change(conn, entity_type: str, entity_id,
                 actor: str, tenant_id: str, action: str = None):
    """
    Context manager: captures before state, yields, then captures after state.
    The conn must NOT be committed inside the block — commit happens outside or
    the caller commits after the block.

    Example:
        with audit_change(conn, "expenses", 7, "user@x.com", "tenant1"):
            cur.execute("UPDATE expenses SET status='approved' WHERE id=7")
        conn.commit()
    """
    tracked = _TRACKED.get(entity_type)
    if not tracked:
        yield
        return

    table, pk_col = tracked
    cur = conn.cursor()
    old_data = _fetch_entity(cur, table, pk_col, entity_id, tenant_id)
    cur.close()

    resolved_action = action or ("CREATE" if old_data is None else "UPDATE")

    yield  # caller executes the mutation

    cur = conn.cursor()
    new_data = _fetch_entity(cur, table, pk_col, entity_id, tenant_id)
    cur.close()

    resolved_action = "DELETE" if new_data is None else resolved_action
    _write_audit(conn, entity_type, entity_id, resolved_action,
                 old_data, new_data, actor, tenant_id)


def log_entity_change(conn, entity_type: str, entity_id,
                      old_data: Optional[dict], new_data: Optional[dict],
                      actor: str, tenant_id: str, action: str = "UPDATE",
                      details: str = None):
    """Direct call when you already have before/after data."""
    _write_audit(conn, entity_type, entity_id, action,
                 old_data, new_data, actor, tenant_id, details)


async def get_entity_history_async(conn, entity_type: str, entity_id,
                                   tenant_id: str, limit: int = 50) -> list:
    """asyncpg version — pass an asyncpg connection from get_conn()."""
    from app.api.db import _q
    try:
        rows = await conn.fetch(_q("""
            SELECT id, actor, action, old_value, new_value, details, created_at
            FROM audit_log
            WHERE resource = %s AND resource_id = %s AND tenant_id::text = %s
            ORDER BY created_at DESC LIMIT %s
        """), entity_type, str(entity_id), tenant_id, limit)
        result = []
        for r in rows:
            d = dict(r)
            if d.get("created_at"):
                d["created_at"] = d["created_at"].isoformat()
            for field in ("old_value", "new_value"):
                if isinstance(d.get(field), str):
                    try:
                        d[field] = json.loads(d[field])
                    except Exception as e:
                        log.warning("unexpected error: %s", e)
            result.append(d)
        return result
    except Exception as e:
        log.warning("get_entity_history_async failed: %s", e)
        return []


async def async_log_entity_change(
    entity_type: str,
    entity_id,
    old_data: Optional[dict],
    new_data: Optional[dict],
    actor: str,
    tenant_id: str,
    action: str = "UPDATE",
    details: str = None,
):
    """asyncpg version of log_entity_change — no psycopg2 conn required."""
    from app.api.db import get_conn, _q
    try:
        async with get_conn() as conn:
            await conn.execute(_q("""
                INSERT INTO audit_log
                    (actor, role, action, resource, resource_id,
                     old_value, new_value, status, details, tenant_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """),
                actor, "system", action, entity_type, str(entity_id),
                json.dumps(old_data, default=str) if old_data else None,
                json.dumps(new_data, default=str) if new_data else None,
                "success", details, tenant_id,
            )
    except Exception as e:
        log.warning("async audit write failed entity=%s id=%s: %s", entity_type, entity_id, e)


def get_entity_history(conn, entity_type: str, entity_id,
                       tenant_id: str, limit: int = 50) -> list:
    """Fetch full audit history for a single entity."""
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, actor, action, old_value, new_value,
                   details, created_at
            FROM audit_log
            WHERE resource = %s AND resource_id = %s AND tenant_id::text = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (entity_type, str(entity_id), tenant_id, limit))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.close()
        for r in rows:
            if r.get("created_at"):
                r["created_at"] = r["created_at"].isoformat()
            for field in ("old_value", "new_value"):
                if isinstance(r.get(field), str):
                    try:
                        r[field] = json.loads(r[field])
                    except Exception as e:
                        log.warning("unexpected error: %s", e)
        return rows
    except Exception as e:
        log.warning("get_entity_history failed: %s", e)
        return []
