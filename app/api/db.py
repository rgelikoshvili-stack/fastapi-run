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
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar, Token, copy_context
from typing import Optional, AsyncGenerator

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# asyncpg pool
# ─────────────────────────────────────────────────────────────────────────────
_async_pool: Optional[asyncpg.Pool] = None
_current_tenant_id: ContextVar[Optional[str]] = ContextVar(
    "current_tenant_id", default=None
)


def set_authenticated_tenant_context(tenant_id: Optional[str]) -> Token:
    """Set request DB context from a verified server-side identity only."""
    if tenant_id is not None:
        _validate_tenant_id(tenant_id)
    active_tenant_id = _current_tenant_id.get()
    if tenant_id is not None and active_tenant_id is not None and active_tenant_id != tenant_id:
        raise ValueError("nested tenant DB context cannot change the active tenant")
    return _current_tenant_id.set(tenant_id)


def _validate_tenant_id(tenant_id: str) -> str:
    if (
        not isinstance(tenant_id, str)
        or not tenant_id
        or tenant_id != tenant_id.strip()
        or tenant_id.casefold() == "default"
    ):
        raise ValueError("tenant_id must be a non-empty canonical tenant identifier")
    return tenant_id


def require_current_tenant_id(expected_tenant_id: Optional[str] = None) -> str:
    """Return the current authorized tenant, optionally checking a caller's hint."""
    active_tenant_id = _current_tenant_id.get()
    if active_tenant_id is None:
        raise ValueError("tenant DB context is required")
    _validate_tenant_id(active_tenant_id)
    if expected_tenant_id is not None:
        _validate_tenant_id(expected_tenant_id)
        if expected_tenant_id != active_tenant_id:
            raise ValueError("tenant hint does not match authorized DB context")
    return active_tenant_id


def reset_authenticated_tenant_context(token: Token) -> None:
    _current_tenant_id.reset(token)


@contextmanager
def authenticated_tenant_context(tenant_id: Optional[str]):
    """Bind a verified tenant identity to the current async request context."""
    token = set_authenticated_tenant_context(tenant_id)
    try:
        yield
    finally:
        reset_authenticated_tenant_context(token)


@contextmanager
def tenant_db_context_sync(trusted_tenant_id: str):
    """Synchronous form of the canonical trusted tenant context for scripts/workers."""
    _validate_tenant_id(trusted_tenant_id)
    with authenticated_tenant_context(trusted_tenant_id):
        yield


@asynccontextmanager
async def tenant_db_context(trusted_tenant_id: str):
    """Bind an authoritative tenant for background work; DB GUC remains transaction-local."""
    _validate_tenant_id(trusted_tenant_id)
    token = set_authenticated_tenant_context(trusted_tenant_id)
    try:
        yield
    finally:
        reset_authenticated_tenant_context(token)


async def run_in_tenant_executor(trusted_tenant_id: str, function, *args):
    """Run synchronous tenant work in a thread with the same trusted context."""
    _validate_tenant_id(trusted_tenant_id)
    loop = asyncio.get_running_loop()
    async with tenant_db_context(trusted_tenant_id):
        context = copy_context()
        return await loop.run_in_executor(None, context.run, function, *args)


def _resolve_tenant_context(expected_tenant_id: Optional[str] = None) -> Optional[str]:
    resolved = _current_tenant_id.get()
    if resolved is not None and (
        not isinstance(resolved, str) or not resolved or resolved != resolved.strip()
        or resolved.casefold() == "default"
    ):
        raise ValueError("tenant_id must be a non-empty canonical string")
    if expected_tenant_id is not None:
        if (
            not isinstance(expected_tenant_id, str)
            or not expected_tenant_id
            or expected_tenant_id != expected_tenant_id.strip()
            or expected_tenant_id.casefold() == "default"
            or expected_tenant_id != resolved
        ):
            raise ValueError("explicit tenant_id must match authenticated DB context")
    return resolved


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
            # Recycle idle connections after 60 s.  email_poller runs every
            # 300 s; with the default 300 s lifetime the pool connection sits
            # idle for exactly 300 s before the next acquire, landing on the
            # boundary where Cloud SQL proxy drops it — causing
            # ConnectionDoesNotExistError every poller cycle.  60 s ensures
            # every background-task acquire gets a fresh connection.
            max_inactive_connection_lifetime=60.0,
        )
        log.info(
            "asyncpg pool created min=%d max=%d inactive_lifetime=60s",
            min_size, max_size,
        )
    return _async_pool


@asynccontextmanager
async def _tenant_connection():
    """Acquire a connection and bind tenant context only for its transaction."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            resolved_tenant_id = _resolve_tenant_context()
            if resolved_tenant_id is not None:
                await conn.execute(
                    "SELECT set_config('app.current_tenant_id', $1, true)",
                    resolved_tenant_id,
                )
            yield conn


@asynccontextmanager
async def get_conn():
    """Async DB context; authenticated tenant scope is transaction-local."""
    async with _tenant_connection() as conn:
        yield conn


async def get_db_dep() -> AsyncGenerator[asyncpg.Connection, None]:
    """FastAPI Depends generator — yields asyncpg connection."""
    async with _tenant_connection() as conn:
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

_CHECK_GUC = "SELECT current_setting('app.current_tenant_id', true)"
_SET_LOCAL_GUC = "SELECT set_config('app.current_tenant_id', %s, true)"


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
                    # SET LOCAL is cleared by ending the transaction. If the
                    # rollback fails, discard the physical connection.
                    self._conn.rollback()
                    self._pool.putconn(self._conn)
                except Exception as e:
                    log.warning("pooled transaction cleanup failed; discarding connection: %s", e)
                    self._pool.putconn(self._conn, close=True)
            else:
                self._pool.putconn(self._conn, close=True)
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
    resolved_tenant_id = _resolve_tenant_context(tenant_id)
    try:
        pool = _get_sync_pool()
        raw_conn = pool.getconn()
    except Exception as e:
        log.error("DB pool getconn failed: %s — falling back to direct connect", e)
        from app.config.secrets import get_secret
        db_url = get_secret("DATABASE_URL") or os.environ.get("DATABASE_URL", "")
        conn = psycopg2.connect(db_url)
        try:
            conn.set_client_encoding("UTF8")
            if resolved_tenant_id is not None:
                with conn.cursor() as cur:
                    cur.execute(_SET_LOCAL_GUC, (resolved_tenant_id,))
            return conn
        except Exception:
            conn.close()
            raise

    try:
        raw_conn.set_client_encoding("UTF8")
        try:
            raw_conn.rollback()
            with raw_conn.cursor() as cur:
                cur.execute(_CHECK_GUC)
                existing_tenant_id = cur.fetchone()[0]
            if existing_tenant_id not in (None, ""):
                raise RuntimeError("pooled connection has non-transactional tenant context")
            if resolved_tenant_id is not None:
                with raw_conn.cursor() as cur:
                    cur.execute(_SET_LOCAL_GUC, (resolved_tenant_id,))
        except Exception:
            pool.putconn(raw_conn, close=True)
            raise
        return _PooledConn(raw_conn, pool)
    except Exception:
        raise


def get_db_sync(tenant_id: Optional[str] = None):
    """Alias for get_db() — used by startup/migrations."""
    return get_db(tenant_id)


async def get_db_async(tenant_id: Optional[str] = None):
    """Async wrapper — runs get_db() in thread pool (legacy compat)."""
    loop = asyncio.get_running_loop()
    context = copy_context()
    return await loop.run_in_executor(None, context.run, get_db, tenant_id)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def row_to_dict(row) -> dict:
    return dict(row) if row else {}


def rows_to_list(rows) -> list:
    return [dict(r) for r in rows] if rows else []
