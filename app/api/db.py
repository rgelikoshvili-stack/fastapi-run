import os
import logging
import psycopg2
import psycopg2.pool
from typing import Optional

log = logging.getLogger(__name__)

_pool: psycopg2.pool.ThreadedConnectionPool | None = None

_RESET_GUC = "SELECT set_config('app.current_tenant_id', '', false)"
_SET_GUC = "SELECT set_config('app.current_tenant_id', %s, false)"


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        db_url = os.environ["DATABASE_URL"]
        min_conn = int(os.environ.get("DB_POOL_MIN", "2"))
        max_conn = int(os.environ.get("DB_POOL_MAX", "10"))
        _pool = psycopg2.pool.ThreadedConnectionPool(min_conn, max_conn, db_url)
        log.info("DB connection pool created min=%d max=%d", min_conn, max_conn)
    return _pool


def get_db(tenant_id: Optional[str] = None) -> psycopg2.extensions.connection:
    """Get a connection from the pool.
    If tenant_id is provided, sets app.current_tenant_id on the session
    so RLS policies are enforced. Caller must call conn.close() to return it.
    """
    try:
        pool = _get_pool()
        conn = pool.getconn()
        conn.set_client_encoding("UTF8")

        if tenant_id:
            with conn.cursor() as cur:
                cur.execute(_SET_GUC, (tenant_id,))
            conn.commit()

        _original_close = conn.close

        def _return_to_pool():
            try:
                if not conn.closed:
                    # Reset GUC so the pooled connection doesn't carry tenant state
                    try:
                        with conn.cursor() as cur:
                            cur.execute(_RESET_GUC)
                        conn.commit()
                    except Exception:
                        pass
                    conn.rollback()
                pool.putconn(conn)
            except Exception as e:
                log.warning("pool putconn error: %s", e)
                try:
                    _original_close()
                except Exception:
                    pass

        conn.close = _return_to_pool
        return conn
    except Exception as e:
        log.error("DB pool getconn failed: %s — falling back to direct connect", e)
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        conn.set_client_encoding("UTF8")
        if tenant_id:
            with conn.cursor() as cur:
                cur.execute(_SET_GUC, (tenant_id,))
            conn.commit()
        return conn
