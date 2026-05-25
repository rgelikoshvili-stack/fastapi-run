"""app/api/db.py — Dual-mode DB layer: asyncpg (async) + psycopg2 (sync legacy).

For new async routes:
    async with get_conn() as conn:
        rows = await conn.fetch(_q("SELECT * FROM t WHERE id=%s"), id)

For legacy sync routes (still supported during migration):
    conn = get_db()
    cur = conn.cursor(...)
    ...
    conn.close()

FastAPI Depends:
    async def route(conn=Depends(get_db_dep)):
        rows = await conn.fetch(...)
"""
import asyncpg
import asyncio
import os
import logging
import re
import psycopg2
import psycopg2.pool
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# asyncpg pool
# ─────────────────────────────────────────────────────────────────────────────
_async_pool: Optional[asyncpg.Pool] = None


def _q(sql: str) -> str:
    """Convert psycopg2 %s placeholders → asyncpg $1, $2, $3..."""
    i = 0

    def _replace(_m):
        nonlocal i
        i += 1
        return f"${i}"

    return re.sub(r"%s", _replace, sql)


async def get_pool() -> asyncpg.Pool:
    global _async_pool
    if _async_pool is None:
        from app.config.secrets import get_secret
        db_url = get_secret("DATABASE_URL") or os.environ.get("DATABASE_URL", "")
        if not db_url:
            raise RuntimeError("DATABASE_URL not configured")
        min_size = int(os.getenv("DB_POOL_MIN", "2"))
        max_size = int(os.getenv("DB_POOL_MAX", "16"))
        _async_pool = await asyncpg.create_pool(
            dsn=db_url,
            min_size=min_size,
            max_size=max_size,
            command_timeout=30,
            # Recycle idle connections after 5 min so Cloud SQL proxy never
            # drops them server-side while they sit unused between background
            # task runs.  Default asyncpg value is also 300 s; making it
            # explicit here allows easy tuning without hunting for the default.
            max_inactive_connection_lifetime=300.0,
        )
        log.info(
            "asyncpg pool created min=%d max=%d inactive_lifetime=300s",
            min_size, max_size,
        )
    return _async_pool


@asynccontextmanager
async def get_conn():
    """Async context manager — yields asyncpg connection."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def get_db_dep() -> AsyncGenerator[asyncpg.Connection, None]:
    """FastAPI Depends generator — yields asyncpg connection."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def close_pool():
    global _async_pool
    if _async_pool:
        await _async_pool.close()
        _async_pool = None
        log.info("asyncpg pool closed")


# ─────────────────────────────────────────────────────────────────────────────
# psycopg2 pool (legacy sync — kept for unconverted files)
# ─────────────────────────────────────────────────────────────────────────────
_sync_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None

_RESET_GUC = "SELECT set_config('app.current_tenant_id', '', false)"
_SET_GUC   = "SELECT set_config('app.current_tenant_id', %s, false)"


def _get_sync_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _sync_pool
    if _sync_pool is None or _sync_pool.closed:
        from app.config.secrets import get_secret
        db_url = get_secret("DATABASE_URL") or os.environ.get("DATABASE_URL", "")
        min_conn = int(os.environ.get("DB_POOL_MIN", "2"))
        max_conn = int(os.environ.get("DB_POOL_MAX", "16"))
        _sync_pool = psycopg2.pool.ThreadedConnectionPool(min_conn, max_conn, db_url)
        log.info("psycopg2 pool created min=%d max=%d", min_conn, max_conn)
    return _sync_pool


class _PooledConn:
    """Wraps a psycopg2 connection so close() returns it to the pool."""

    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        try:
            if not self._conn.closed:
                try:
                    with self._conn.cursor() as cur:
                        cur.execute(_RESET_GUC)
                    self._conn.commit()
                except Exception as e:
                    log.warning("unexpected error: %s", e)
                try:
                    self._conn.rollback()
                except Exception as e:
                    log.warning("unexpected error: %s", e)
            self._pool.putconn(self._conn)
        except Exception as e:
            log.warning("pool putconn error: %s", e)
            try:
                self._conn.close()
            except Exception as e:
                log.warning("unexpected error: %s", e)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def get_db(tenant_id: Optional[str] = None):
    """Legacy sync psycopg2 connection — still used by unconverted routes."""
    try:
        pool = _get_sync_pool()
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
        db_url = get_secret("DATABASE_URL") or os.environ.get("DATABASE_URL", "")
        conn = psycopg2.connect(db_url)
        conn.set_client_encoding("UTF8")
        if tenant_id:
            with conn.cursor() as cur:
                cur.execute(_SET_GUC, (tenant_id,))
            conn.commit()
        return conn


def get_db_sync(tenant_id: Optional[str] = None):
    """Alias for get_db() — used by startup/migrations."""
    return get_db(tenant_id)


async def get_db_async(tenant_id: Optional[str] = None):
    """Async wrapper — runs get_db() in thread pool (legacy compat)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: get_db(tenant_id))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def row_to_dict(row) -> dict:
    return dict(row) if row else {}


def rows_to_list(rows) -> list:
    return [dict(r) for r in rows] if rows else []
