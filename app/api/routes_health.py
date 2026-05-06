import asyncio
import os
import time
import logging
from datetime import datetime, timezone
from fastapi import APIRouter
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/health", tags=["health"])
log = logging.getLogger(__name__)

_START_TIME = time.time()

_REQUIRED_ENV = [
    "DATABASE_URL", "JWT_SECRET", "ANTHROPIC_API_KEY",
    "BALANCE_API_KEY", "OPENROUTER_API_KEY",
]


def _check_env() -> dict:
    return {k: ("set" if os.environ.get(k) else "missing") for k in _REQUIRED_ENV}


# ── Fast health (no DB, no GCS) — target < 50 ms ────────────────────────────

@router.get("")
@router.get("/")
async def health_check():
    """Lightweight liveness probe — env vars + uptime only, no DB I/O."""
    uptime_s = int(time.time() - _START_TIME)
    uptime = f"{uptime_s // 3600}h {(uptime_s % 3600) // 60}m {uptime_s % 60}s"
    env = _check_env()
    missing = [k for k, v in env.items() if v == "missing"]

    data = {
        "service": "Bridge Hub",
        "version": os.environ.get("APP_VERSION", "1.0.0"),
        "environment": os.environ.get("ENVIRONMENT", "production"),
        "uptime": uptime,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "degraded" if missing else "ok",
        "env_vars": env,
        "warnings": [f"{k} not configured" for k in missing],
        "connectors": {
            "balance":    "configured" if os.environ.get("BALANCE_API_KEY")    else "demo_mode",
            "anthropic":  "configured" if os.environ.get("ANTHROPIC_API_KEY")  else "missing",
            "openrouter": "configured" if os.environ.get("OPENROUTER_API_KEY") else "missing",
        },
    }

    # /health is a liveness probe — the process is alive regardless of which
    # optional third-party API keys are configured.  Missing keys are surfaced
    # as warnings, not errors.  Use /health/deep for a full connectivity check.
    return ok_response("Health check OK", data)


# ── Deep health — full DB + GCS check, max 5 s timeout ──────────────────────

async def _check_db_deep() -> dict:
    try:
        from app.api.db import get_conn, _q
        async with get_conn() as conn:
            row = await asyncio.wait_for(
                conn.fetchrow(_q("SELECT version(), pg_database_size(current_database())")),
                timeout=3.0,
            )
            total_runs = await asyncio.wait_for(
                conn.fetchval(_q("SELECT COUNT(*) FROM pipeline_runs")),
                timeout=3.0,
            )
        return {
            "status": "connected",
            "pg_version": (row[0] or "").split(" ")[1] if row else "unknown",
            "db_size_mb": round(int(row[1] or 0) / 1_048_576, 1) if row else 0,
            "total_pipeline_runs": total_runs,
        }
    except asyncio.TimeoutError:
        return {"status": "timeout", "detail": "DB did not respond within 3 s"}
    except Exception as e:
        log.error("health deep db check failed: %s", e)
        return {"status": "error", "detail": str(e)}


def _check_gcs_deep() -> dict:
    bucket_name = os.environ.get("GCS_BUCKET_NAME", "")
    if not bucket_name:
        return {"status": "not_configured"}
    try:
        from google.cloud import storage as gcs
        client = gcs.Client()
        bucket = client.bucket(bucket_name)
        bucket.reload()
        return {"status": "ok", "bucket": bucket_name}
    except Exception as e:
        log.error("health gcs check failed: %s", e)
        return {"status": "error", "detail": str(e)}


@router.get("/deep")
async def health_check_deep():
    """Full health check: DB ping + GCS + env. Use for startup probes only."""
    t0 = time.time()
    db = await _check_db_deep()
    gcs = await asyncio.get_event_loop().run_in_executor(None, _check_gcs_deep)
    env = _check_env()
    elapsed_ms = round((time.time() - t0) * 1000)

    uptime_s = int(time.time() - _START_TIME)
    uptime = f"{uptime_s // 3600}h {(uptime_s % 3600) // 60}m {uptime_s % 60}s"
    all_ok = db["status"] == "connected" and gcs.get("status") in ("ok", "not_configured")

    data = {
        "service": "Bridge Hub",
        "version": os.environ.get("APP_VERSION", "1.0.0"),
        "environment": os.environ.get("ENVIRONMENT", "production"),
        "uptime": uptime,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "check_duration_ms": elapsed_ms,
        "db": db,
        "gcs": gcs,
        "env_vars": env,
    }

    if all_ok:
        return ok_response("Deep health check OK", data)
    return error_response("Deep health check failed", "HEALTH_ERROR", data)


# ── Ping (sub-1ms) ───────────────────────────────────────────────────────────

@router.get("/ping")
def ping():
    return ok_response("ok", {"pong": True, "ts": datetime.now(timezone.utc).isoformat()})


# ── Version (standalone router) ──────────────────────────────────────────────

version_router = APIRouter(tags=["health"])


@version_router.get("/version")
def get_version():
    return ok_response("Version", {
        "version": os.environ.get("APP_VERSION", "1.0.0"),
        "service": "Bridge Hub",
        "environment": os.environ.get("ENVIRONMENT", "production"),
    })
