import os
import sys
import asyncio

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

from app.api.security import limiter, rate_limit_exceeded_handler, SECURITY_HEADERS
from app.api.services.approval_service import autopilot_approve_service
from app.api.services.learning_service import run_decay_service
from app.api.middleware.tenant_middleware import tenant_middleware
from app.api.middleware.rbac_middleware import rbac_middleware

# --- APP ---
app = FastAPI(
    title="Bridge Hub v1.0.0",
    version="1.0.0",
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
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "message": "Internal server error",
            "data": None,
            "error": {"code": "INTERNAL_ERROR", "details": str(exc)},
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "ok": False,
            "message": "Validation failed",
            "data": None,
            "error": {
                "code": "VALIDATION_ERROR",
                "details": jsonable_encoder(exc.errors()),
            },
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "ok": False,
            "message": "HTTP error",
            "data": None,
            "error": {"code": f"HTTP_{exc.status_code}", "details": str(exc.detail)},
        },
    )


# --- CORE ROUTES IMPORTS ---
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
from app.api import routes_transaction_memory
from app.api import routes_qa
from app.api import routes_tenants

from app.api.routes_patterns import router as patterns_router
from app.api.routes_expense_articles import router as expense_articles_router
from app.api.routes_learning_explain import router as learning_explain_router
from routes_version import router as version_router


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
app.include_router(patterns_router)
app.include_router(version_router)
app.include_router(routes_invoice.router)
app.include_router(expense_articles_router)
app.include_router(routes_erp_memory.router)
app.include_router(routes_erp_import.router)
app.include_router(routes_erp_connectors.router)
app.include_router(routes_transaction_memory.router)
app.include_router(learning_explain_router)
app.include_router(routes_qa.router)
app.include_router(routes_tenants.router)


# --- FUTURE ROUTES ---
# from app.api import routes_pipeline
# from app.api import routes_balance_ge
# ... (დანარჩენი commented routes)


# --- RATE LIMITING ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


# --- MIDDLEWARE (თანმიმდევრობა მნიშვნელოვანია!) ---
# 1. tenant — პირველი: tenant_id-ს ადგენს request-ზე
app.middleware("http")(tenant_middleware)

# 2. rbac — მეორე: tenant-ის შემდეგ, role-ს ამოწმებს
app.middleware("http")(rbac_middleware)

# 3. security headers — ბოლო: response-ზე headers-ს ამატებს
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
                None,
                lambda: autopilot_approve_service("default")
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