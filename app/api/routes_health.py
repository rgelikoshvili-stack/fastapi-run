import os
import time
import logging
from datetime import datetime, timezone
from fastapi import APIRouter
from app.api.db import get_conn, _q
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


async def _check_db() -> dict:
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(_q("SELECT version(), pg_database_size(current_database())"))
            total_runs = await conn.fetchval(_q("SELECT COUNT(*) FROM pipeline_runs"))
        return {
            "status": "connected",
            "pg_version": (row[0] or "").split(" ")[1] if row else "unknown",
            "db_size_mb": round(int(row[1] or 0) / 1_048_576, 1) if row else 0,
            "total_pipeline_runs": total_runs,
        }
    except Exception as e:
        log.error("health db check failed: %s", e)
        return {"status": "error", "detail": str(e)}


def _check_gcs() -> dict:
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


@router.get("/")
async def health_check():
    db = await _check_db()
    gcs = _check_gcs()
    env = _check_env()
    uptime_s = int(time.time() - _START_TIME)
    uptime = f"{uptime_s // 3600}h {(uptime_s % 3600) // 60}m {uptime_s % 60}s"
    all_ok = db["status"] == "connected" and gcs.get("status") in ("ok", "not_configured")

    data = {
        "service": "Bridge Hub",
        "version": os.environ.get("APP_VERSION", "1.0.0"),
        "environment": os.environ.get("ENVIRONMENT", "production"),
        "uptime": uptime,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "db": db,
        "gcs": gcs,
        "env_vars": env,
        "connectors": {
            "balance": "configured" if os.environ.get("BALANCE_API_KEY") else "demo_mode",
            "anthropic": "configured" if os.environ.get("ANTHROPIC_API_KEY") else "missing",
            "openrouter": "configured" if os.environ.get("OPENROUTER_API_KEY") else "missing",
        },
    }

    if all_ok:
        return ok_response("Health check OK", data)
    return error_response("Health check failed", "HEALTH_ERROR", data)


@router.get("/ping")
def ping():
    return {"ok": True, "pong": True, "ts": datetime.now(timezone.utc).isoformat()}


# Standalone /version endpoint
version_router = APIRouter(tags=["health"])

@version_router.get("/version")
def get_version():
    return ok_response("Version", {
        "version": os.environ.get("APP_VERSION", "1.0.0"),
        "service": "Bridge Hub",
        "environment": os.environ.get("ENVIRONMENT", "production"),
    })
