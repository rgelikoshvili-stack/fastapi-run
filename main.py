import os
import sys
import asyncio
import json

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
os.environ["PYTHONIOENCODING"] = "utf-8"

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.security import limiter, rate_limit_exceeded_handler, SECURITY_HEADERS
from app.api.services.approval_service import autopilot_approve_service
from app.api.services.learning_service import run_decay_service
from app.api.middleware.tenant_middleware import tenant_middleware
from app.api.middleware.rbac_middleware import rbac_middleware


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
        return FileResponse("static/index.html")
    except Exception:
        return HTMLResponse("<h1>Bridge Hub v1.0.0</h1><p><a href='/docs'>API Docs</a></p>")


# --- EXCEPTION HANDLERS ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return GeorgianJSONResponse(
        status_code=500,
        content={"ok": False, "message": "Internal server error", "data": None,
                 "error": {"code": "INTERNAL_ERROR", "details": str(exc)}},
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
# from app.api import routes_chat
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
from app.api import routes_notifications_ws
from app.api import routes_collaboration
from app.api import routes_dashboard_live
from app.api import routes_client_portal
from app.api import routes_payroll
from app.api import routes_email_invoice
from app.api import routes_bank_sync
from app.api import routes_ai_chat
from app.api.routes_ai_recommend import router as routes_ai_recommend
from app.api import routes_audit
from app.api.middleware.auth_middleware import auth_middleware
from app.api.middleware.audit_log_middleware import audit_log_middleware


# --- INCLUDE ROUTERS ---
app.include_router(routes_health.router)
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
# app.include_router(routes_chat.router)
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
app.include_router(routes_reports.router)
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
app.include_router(routes_notifications_ws.router)
app.include_router(routes_collaboration.router)
app.include_router(routes_dashboard_live.router)
app.include_router(routes_client_portal.router)
app.include_router(routes_payroll.router)
app.include_router(routes_email_invoice.router)
app.include_router(routes_bank_sync.router)
app.include_router(routes_ai_chat.router)
app.include_router(routes_ai_recommend)


# --- RATE LIMITING ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


# --- MIDDLEWARE ---
app.middleware("http")(audit_log_middleware)
app.middleware("http")(rbac_middleware)
app.middleware("http")(auth_middleware)
app.middleware("http")(tenant_middleware)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers[k] = v
    return response


# --- BACKGROUND TASKS ---
async def autopilot_loop():
    while True:
        try:
            print("🤖 Autopilot running...")
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, lambda: autopilot_approve_service("default")
            )
            print(f"✅ Autopilot result: {result}")
        except Exception as e:
            print(f"❌ Autopilot error: {e}")
        await asyncio.sleep(60)


async def decay_loop():
    while True:
        try:
            print("🧠 Decay running...")
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, run_decay_service)
            print(f"✅ Decay result: {result}")
        except Exception as e:
            print(f"❌ Decay error: {e}")
        await asyncio.sleep(3600)


@app.on_event("startup")
async def start_background_tasks():
    print("🚀 Starting background scheduler...")
    asyncio.create_task(autopilot_loop())
    asyncio.create_task(decay_loop())
    # JSON → DB one-time migration
    try:
        from bridge_hub_knowledge import migrate_json_to_db
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, migrate_json_to_db)
    except Exception as e:
        print(f"⚠️ KB migration error (non-fatal): {e}")
    # Knowledge Base preload
    try:
        from bridge_hub_knowledge import _load_files as _kb_load
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _kb_load)
        print("✅ Knowledge Base loaded!")
    except Exception as e:
        print(f"⚠️ KB load error: {e}")