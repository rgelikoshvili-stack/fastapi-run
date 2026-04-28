import functools
import logging

DEFAULT_TENANT_ID = "default"
log = logging.getLogger(__name__)

# Cache INN → tenant_id lookups so we don't hit DB on every request
@functools.lru_cache(maxsize=128)
def _inn_to_tenant_id(inn: str) -> str:
    try:
        from app.api.db import get_db
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT tenant_id FROM tenants WHERE company_inn = %s LIMIT 1",
                (inn,),
            )
            row = cur.fetchone()
            return row[0] if row else inn
        finally:
            cur.close()
            conn.close()
    except Exception:
        return inn


def resolve_tenant_id(value: str | None) -> str:
    tid = (value or "").strip() or DEFAULT_TENANT_ID
    # If the value is all digits it might be a company INN — resolve to actual tenant_id
    if tid.isdigit():
        tid = _inn_to_tenant_id(tid)
    return tid
