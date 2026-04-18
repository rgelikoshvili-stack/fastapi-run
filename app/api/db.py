import os
import logging
import psycopg2
import psycopg2.pool

log = logging.getLogger(__name__)

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        db_url = os.environ["DATABASE_URL"]
        min_conn = int(os.environ.get("DB_POOL_MIN", "2"))
        max_conn = int(os.environ.get("DB_POOL_MAX", "10"))
        _pool = psycopg2.pool.ThreadedConnectionPool(min_conn, max_conn, db_url)
        log.info("DB connection pool created min=%d max=%d", min_conn, max_conn)
    return _pool


def get_db() -> psycopg2.extensions.connection:
    """Get a connection from the pool. Caller must call conn.close() to return it."""
    try:
        pool = _get_pool()
        conn = pool.getconn()
        conn.set_client_encoding("UTF8")
        # Wrap close() so it returns connection to pool instead of closing
        _original_close = conn.close

        def _return_to_pool():
            try:
                if not conn.closed:
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
        return conn
