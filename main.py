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


# --- ROUTES IMPORTS ---
from app.api import routes_health
from app.api.routes_health import version_router
from app.api import routes_debug
from app.api import routes_bank_csv
from app.api import routes_bank_process
from app.api import routes_approval
from app.api import routes_posting
from app.api import routes_system
from app.api import routes_coa
from app.api import routes_learning
from app.api import routes_transaction_ai
from app.api import routes_export_journal
from app.api import routes_audit_log
from app.api import routes_invoice
from app.api import routes_erp_memory
from app.api import routes_erp_import
from app.api import routes_erp_connectors
from app.api import routes_auth
from app.api import routes_balance_ge
from app.api import routes_1c
from app.api import routes_notifications
from app.api import routes_tax
from app.api import routes_search
from app.api import routes_audit_engine
from app.api import routes_ai_journal
from app.api import routes_bank_accounts
from app.api import routes_budget
from app.api import routes_contracts
from app.api import routes_crm
from app.api import routes_currency
from app.api import routes_expenses
from app.api import routes_invoices
from app.api import routes_pdf_report
from app.api import routes_rbac
from app.api import routes_reconciliation
from app.api import routes_reports
from app.api.routes_financial_statements import router as financial_statements_router
from app.api.routes_fixed_assets import router as fixed_assets_router
from app.api import routes_security
from app.api import routes_webhooks_v2
from app.api import routes_api_docs
from app.api import routes_dashboard
from app.api import routes_docs
from app.api import routes_transaction_memory
from app.api import routes_qa
from app.api import routes_tenants
from app.api import routes_export_v2

from app.api.routes_patterns import router as patterns_router
from app.api.routes_expense_articles import router as expense_articles_router
from app.api.routes_learning_explain import router as learning_explain_router
from app.api import routes_ocr
from app.api.routes_documents import router as routes_documents_router
from app.api.routes_outgoing import router as routes_outgoing_router
from app.api import routes_notifications_ws
from app.api import routes_collaboration
from app.api import routes_dashboard_live
from app.api import routes_client_portal
from app.api.routes_dashboard_insights import router as dashboard_insights_router
from app.api import routes_payroll
from app.api import routes_email_invoice
from app.api.routes_email_collector import router as routes_email_collector
from app.api.routes_balance_credentials import router as routes_balance_credentials
from app.api import routes_bank_sync
from app.api import routes_ai_chat
from app.api.routes_claude_chat import router as routes_claude_chat
from app.api.routes_ai_recommend import router as routes_ai_recommend
from app.api import routes_audit
from app.api.routes_decision_engine import router as decision_engine_router
from app.api.middleware.auth_middleware import auth_middleware
from app.api.middleware.audit_log_middleware import audit_log_middleware
from app.api.middleware.correlation_middleware import correlation_middleware
from app.api.routes_inventory import router as inventory_router
from app.api.routes_audit_trail import router as audit_trail_router
from app.api.routes_2fa import router as totp_router
from app.api.routes_fx import router as fx_router
from app.api.routes_webhooks import router as webhooks_router
from app.api.routes_oauth import router as oauth_router
from app.api.routes_employee_portal import router as employee_portal_router
from app.api.routes_employee_portal import pension_router as pension_transfer_router
from app.api.routes_integrations import router as integrations_router
from app.api.routes_aging import router as aging_router
from app.api.routes_recurring import router as recurring_router
from app.api.routes_period_lock import router as period_lock_router
from app.api.routes_closing import router as closing_router
from app.api.routes_cost_center import router as cost_center_router
from app.api.routes_worker import router as worker_router
from app.api.routes_email_inbound import router as email_inbound_router


# --- INCLUDE ROUTERS ---
app.include_router(routes_health.router)
app.include_router(version_router)
app.include_router(inventory_router)
app.include_router(audit_trail_router)
app.include_router(totp_router)
app.include_router(fx_router)
app.include_router(webhooks_router)
app.include_router(oauth_router)
app.include_router(employee_portal_router)
app.include_router(pension_transfer_router)
app.include_router(integrations_router)
app.include_router(aging_router)
app.include_router(recurring_router)
app.include_router(period_lock_router)
app.include_router(worker_router)
app.include_router(email_inbound_router)
app.include_router(closing_router)
app.include_router(cost_center_router)
app.include_router(routes_debug.router)
app.include_router(routes_bank_csv.router)
app.include_router(routes_bank_process.router)
app.include_router(routes_approval.router)
app.include_router(routes_posting.router)
app.include_router(routes_system.router)
app.include_router(routes_coa.router)
app.include_router(routes_learning.router)
app.include_router(routes_transaction_ai.router)
app.include_router(routes_export_journal.router)
app.include_router(routes_audit_log.router)
app.include_router(routes_audit.router)
app.include_router(patterns_router)
app.include_router(routes_invoice.router)
app.include_router(expense_articles_router)
app.include_router(routes_erp_memory.router)
app.include_router(routes_erp_import.router)
app.include_router(routes_erp_connectors.router)
app.include_router(routes_auth.router)
app.include_router(routes_balance_ge.router)
app.include_router(routes_1c.router)
app.include_router(routes_notifications.router)
app.include_router(routes_tax.router)
app.include_router(routes_search.router)
app.include_router(routes_audit_engine.router)
app.include_router(routes_ai_journal.router)
app.include_router(routes_bank_accounts.router)
app.include_router(routes_budget.router)
app.include_router(routes_contracts.router)
app.include_router(routes_crm.router)
app.include_router(routes_currency.router)
app.include_router(routes_expenses.router)
app.include_router(routes_invoices.router)
app.include_router(routes_pdf_report.router)
app.include_router(routes_rbac.router)
app.include_router(routes_reconciliation.router)
app.include_router(financial_statements_router)
app.include_router(routes_reports.router)
app.include_router(fixed_assets_router)
app.include_router(routes_security.router)
app.include_router(routes_webhooks_v2.router)
app.include_router(routes_api_docs.router)
app.include_router(routes_dashboard.router)
app.include_router(routes_docs.router)
app.include_router(routes_transaction_memory.router)
app.include_router(learning_explain_router)
app.include_router(routes_qa.router)
app.include_router(routes_tenants.router)
app.include_router(routes_export_v2.router)
app.include_router(routes_ocr.router)
app.include_router(routes_documents_router)
app.include_router(routes_outgoing_router)
app.include_router(routes_notifications_ws.router)
app.include_router(routes_collaboration.router)
app.include_router(routes_dashboard_live.router)
app.include_router(dashboard_insights_router)
app.include_router(routes_client_portal.router)
app.include_router(routes_payroll.router)
app.include_router(routes_email_invoice.router)
app.include_router(routes_email_collector)
app.include_router(routes_balance_credentials)
app.include_router(routes_bank_sync.router)
app.include_router(routes_ai_chat.router)
app.include_router(routes_ai_recommend)
app.include_router(routes_claude_chat)
app.include_router(decision_engine_router)


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
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.on_event("startup")
async def start_background_tasks():
    print("🚀 Starting background scheduler...")
    # Warm up asyncpg pool
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
    # DB column migrations
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _run_db_migrations)
    # Email collector tables
    try:
        await loop.run_in_executor(None, _ensure_email_tables)
        print("✅ Email collector tables OK")
    except Exception as e:
        print(f"⚠️ Email tables migration error (non-fatal): {e}")
    # Balance.ge per-tenant credentials table
    try:
        from app.api.services.balance_credentials_service import ensure_table as _ensure_balance_table
        await loop.run_in_executor(None, _ensure_balance_table)
        print("✅ Balance credentials table OK")
    except Exception as e:
        print(f"⚠️ Balance credentials table migration (non-fatal): {e}")
    # JSON → DB one-time migration
    try:
        from app.knowledge.knowledge_loader import migrate_json_to_db
        await loop.run_in_executor(None, migrate_json_to_db)
    except Exception as e:
        print(f"⚠️ KB migration error (non-fatal): {e}")
    # Inventory tables
    try:
        from app.api.services.inventory_service import ensure_inventory_tables
        await loop.run_in_executor(None, ensure_inventory_tables)
        print("✅ Inventory tables OK")
    except Exception as e:
        print(f"⚠️ Inventory tables migration (non-fatal): {e}")
    # NBG live exchange rates
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
    # Knowledge Base preload
    try:
        from app.knowledge.knowledge_loader import _load_files as _kb_load
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _kb_load)
        print("✅ Knowledge Base loaded!")
    except Exception as e:
        print(f"⚠️ KB load error: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    from app.api.db import close_pool
    await close_pool()
    print("✅ asyncpg pool closed")