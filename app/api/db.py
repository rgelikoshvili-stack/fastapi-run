import asyncio
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
        from app.config.secrets import get_secret
        db_url = get_secret("DATABASE_URL") or os.environ["DATABASE_URL"]
        min_conn = int(os.environ.get("DB_POOL_MIN", "2"))
        max_conn = int(os.environ.get("DB_POOL_MAX", "10"))
        _pool = psycopg2.pool.ThreadedConnectionPool(min_conn, max_conn, db_url)
        log.info("DB connection pool created min=%d max=%d", min_conn, max_conn)
    return _pool


class _PooledConn:
    """Wraps a psycopg2 connection so close() returns it to the pool."""

    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool

    # proxy every attribute/method to the real connection
    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        try:
            if not self._conn.closed:
                try:
                    with self._conn.cursor() as cur:
                        cur.execute(_RESET_GUC)
                    self._conn.commit()
                except Exception:
                    pass
                try:
                    self._conn.rollback()
                except Exception:
                    pass
            self._pool.putconn(self._conn)
        except Exception as e:
            log.warning("pool putconn error: %s", e)
            try:
                self._conn.close()
            except Exception:
                pass

    # context manager support
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # cursor() must return real cursor (already proxied via __getattr__)


def get_db(tenant_id: Optional[str] = None):
    """Get a pooled connection. Caller must call conn.close() to return it to pool."""
    try:
        pool = _get_pool()
        raw_conn = pool.getconn()
        raw_conn.set_client_encoding("UTF8")

        if tenant_id:
            with raw_conn.cursor() as cur:
                cur.execute(_SET_GUC, (tenant_id,))
            raw_conn.commit()

        return _PooledConn(raw_conn, pool)

    except Exception as e:
        log.error("DB pool getconn failed: %s — falling back to direct connect", e)
        from app.config.secrets import get_secret
        db_url = get_secret("DATABASE_URL") or os.environ["DATABASE_URL"]
        conn = psycopg2.connect(db_url)
        conn.set_client_encoding("UTF8")
        if tenant_id:
            with conn.cursor() as cur:
                cur.execute(_SET_GUC, (tenant_id,))
            conn.commit()
        return conn


async def get_db_async(tenant_id: Optional[str] = None):
    """Async wrapper — runs get_db() in a thread pool to avoid blocking the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: get_db(tenant_id))
