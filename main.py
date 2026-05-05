import os
import sys
import asyncio
import json
import logging

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
os.environ["PYTHONIOENCODING"] = "utf-8"


class _CloudRunJsonFormatter(logging.Formatter):
    """Emit Cloud Run / GCP-compatible structured JSON log lines."""
    SEVERITY = {
        logging.DEBUG: "DEBUG", logging.INFO: "INFO",
        logging.WARNING: "WARNING", logging.ERROR: "ERROR",
        logging.CRITICAL: "CRITICAL",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "severity": self.SEVERITY.get(record.levelno, "DEFAULT"),
            "message": record.getMessage(),
            "logger": record.name,
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
        }
        if getattr(record, "correlation_id", None):
            payload["correlation_id"] = record.correlation_id
        if getattr(record, "tenant_id", None):
            payload["tenant_id"] = record.tenant_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _setup_logging():
    root = logging.getLogger()
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_CloudRunJsonFormatter())
        root.addHandler(handler)
    root.setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


_setup_logging()

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.security import limiter, rate_limit_exceeded_handler, SECURITY_HEADERS

try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    _PROM_REQUESTS = Counter("http_requests_total", "Total HTTP requests", ["method", "path", "status"])
    _PROM_LATENCY  = Histogram("http_request_duration_seconds", "HTTP request latency", ["method", "path"])
    _PROM_ACTIVE   = Gauge("http_active_requests", "Active HTTP requests")
    _PROM_OK = True
except ImportError:
    _PROM_OK = False
from app.api.services.email_collector import _ensure_tables as _ensure_email_tables
from app.api.middleware.tenant_middleware import tenant_middleware
from app.api.middleware.rbac_middleware import rbac_middleware
from app.startup.background import autopilot_loop, decay_loop, email_poller_loop
from app.startup.migrations import run_db_migrations as _run_db_migrations


# --- GEORGIAN JSON RESPONSE ---
class GeorgianJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")


# --- APP ---
app = FastAPI(
    title="Bridge Hub v1.0.0",
    version="1.0.0",
    default_response_class=GeorgianJSONResponse,
)

# --- STATIC FILES ---
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


# --- ROOT ---
@app.get("/")
def root():
    try:
        return FileResponse("static/approval.html")
    except Exception:
        return HTMLResponse("<h1>Bridge Hub v1.0.0</h1><p><a href='/docs'>API Docs</a></p>")


@app.get("/hub-map")
def hub_map():
    try:
        return FileResponse("static/bridge_hub_map.html")
    except Exception:
        return HTMLResponse("<h1>404</h1>")


@app.get("/metrics", include_in_schema=False)
def metrics():
    """Prometheus metrics endpoint — internal use only."""
    from fastapi.responses import Response
    if not _PROM_OK:
        return Response("# prometheus-client not installed\n", media_type="text/plain")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# --- EXCEPTION HANDLERS ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import logging as _log
    _log.getLogger(__name__).exception("Unhandled error: %s %s", request.method, request.url.path)
    return GeorgianJSONResponse(
        status_code=500,
        content={"ok": False, "message": "Internal server error", "data": None,
                 "error": {"code": "INTERNAL_ERROR", "details": "სისტემური შეცდომა. გთხოვთ სცადოთ თავიდან."}},
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return GeorgianJSONResponse(
        status_code=422,
        content={"ok": False, "message": "Validation failed", "data": None,
                 "error": {"code": "VALIDATION_ERROR", "details": jsonable_encoder(exc.errors())}},
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return GeorgianJSONResponse(
        status_code=exc.status_code,
        content={"ok": False, "message": "HTTP error", "data": None,
                 "error": {"code": f"HTTP_{exc.status_code}", "details": str(exc.detail)}},
    )


# --- ROUTES ---
from app.core.router_registry import register_routers
from app.api.middleware.auth_middleware import auth_middleware
from app.api.middleware.audit_log_middleware import audit_log_middleware
from app.api.middleware.correlation_middleware import correlation_middleware

register_routers(app)


# --- CORS ---
_cors_env = os.getenv("ALLOWED_ORIGINS", "")
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] or [
    "http://localhost:3000",
    "http://localhost:8000",
    "https://fastapi-run-226875230147.europe-west1.run.app",
    "https://bridge-hub-ui-j3dm.vercel.app",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Tenant-ID", "X-Idempotent-Key", "X-Correlation-ID"],
)

# --- RATE LIMITING ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


# --- MIDDLEWARE ---
# Starlette executes HTTP middleware in reverse registration order.
app.middleware("http")(correlation_middleware)  # registered first; Starlette wraps later middleware outside it
app.middleware("http")(audit_log_middleware)
app.middleware("http")(rbac_middleware)
app.middleware("http")(auth_middleware)
app.middleware("http")(tenant_middleware)

@app.middleware("http")
async def https_redirect(request: Request, call_next):
    """Redirect HTTP → HTTPS when behind a proxy (Cloud Run / load balancer)."""
    proto = request.headers.get("X-Forwarded-Proto", "")
    if proto == "http" and request.url.path != "/health":
        https_url = str(request.url).replace("http://", "https://", 1)
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=https_url, status_code=301)
    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers[k] = v
    if "X-Powered-By" in response.headers:
        del response.headers["X-Powered-By"]
    return response


@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    if not _PROM_OK or request.url.path == "/metrics":
        return await call_next(request)
    import time
    path = request.url.path
    method = request.method
    _PROM_ACTIVE.inc()
    start = time.perf_counter()
    try:
        response = await call_next(request)
        _PROM_REQUESTS.labels(method=method, path=path, status=response.status_code).inc()
        return response
    finally:
        _PROM_LATENCY.labels(method=method, path=path).observe(time.perf_counter() - start)
        _PROM_ACTIVE.dec()




async def _nbg_sync_loop():
    """Sync NBG exchange rates daily at startup and every 24 h."""
    import asyncio as _asyncio
    loop = _asyncio.get_running_loop()
    while True:
        try:
            from app.integrations.nbg_api import sync_rates_to_db as _sync
            from app.api.db import get_db as _get_db
            def _do_sync():
                conn = _get_db()
                try:
                    n = _sync(conn)
                    print(f"✅ NBG daily sync: {n} currencies")
                finally:
                    conn.close()
            await loop.run_in_executor(None, _do_sync)
        except Exception as e:
            print(f"⚠️ NBG daily sync failed: {e}")
        await _asyncio.sleep(86400)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── startup ────────────────────────────────────────────────────────────────
    print("🚀 Starting background scheduler...")
    try:
        from app.api.db import get_pool
        await get_pool()
        print("✅ asyncpg pool ready")
    except Exception as e:
        print(f"⚠️ asyncpg pool init (non-fatal): {e}")
    asyncio.create_task(autopilot_loop())
    asyncio.create_task(decay_loop())
    asyncio.create_task(email_poller_loop())
    asyncio.create_task(_nbg_sync_loop())
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _run_db_migrations)
    try:
        await loop.run_in_executor(None, _ensure_email_tables)
        print("✅ Email collector tables OK")
    except Exception as e:
        print(f"⚠️ Email tables migration error (non-fatal): {e}")
    try:
        from app.api.services.balance_credentials_service import ensure_table as _ensure_balance_table
        await loop.run_in_executor(None, _ensure_balance_table)
        print("✅ Balance credentials table OK")
    except Exception as e:
        print(f"⚠️ Balance credentials table migration (non-fatal): {e}")
    try:
        from app.knowledge.knowledge_loader import migrate_json_to_db
        await loop.run_in_executor(None, migrate_json_to_db)
    except Exception as e:
        print(f"⚠️ KB migration error (non-fatal): {e}")
    try:
        from app.api.services.inventory_service import ensure_inventory_tables
        await loop.run_in_executor(None, ensure_inventory_tables)
        print("✅ Inventory tables OK")
    except Exception as e:
        print(f"⚠️ Inventory tables migration (non-fatal): {e}")
    try:
        from app.integrations.nbg_api import sync_rates_to_db
        from app.api.db import get_db_sync as _get_db_sync
        def _nbg_sync():
            conn = _get_db_sync()
            try:
                n = sync_rates_to_db(conn)
                print(f"✅ NBG rates synced: {n} currencies")
            finally:
                conn.close()
        await loop.run_in_executor(None, _nbg_sync)
    except Exception as e:
        print(f"⚠️ NBG rate sync (non-fatal): {e}")
    try:
        from app.knowledge.knowledge_loader import _load_files as _kb_load
        await loop.run_in_executor(None, _kb_load)
        print("✅ Knowledge Base loaded!")
    except Exception as e:
        print(f"⚠️ KB load error: {e}")

    yield

    # ── shutdown ───────────────────────────────────────────────────────────────
    from app.api.db import close_pool
    await close_pool()
    print("✅ asyncpg pool closed")


# Wire lifespan into the app (defined after app to avoid forward-reference NameError)
app.router.lifespan_context = lifespan