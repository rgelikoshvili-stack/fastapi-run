from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from slowapi.errors import RateLimitExceeded
from app.api.security import limiter, rate_limit_exceeded_handler, SECURITY_HEADERS
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI(title="Bridge Hub v1.0.0", version="1.0.0")


@app.get("/")
def root():
    try:
        return FileResponse("static/index.html")
    except Exception:
        return HTMLResponse("<h1>Bridge Hub v1.0.0</h1><p><a href='/docs'>API Docs</a></p>")


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
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
async def validation_exception_handler(request, exc):
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
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "ok": False,
            "message": "HTTP error",
            "data": None,
            "error": {"code": f"HTTP_{exc.status_code}", "details": str(exc.detail)},
        },
    )


# --- CORE ROUTES ---

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
from app.api.routes_patterns import router as patterns_router
from routes_version import router as version_router
from app.api import routes_invoice
from app.api.routes_expense_articles import router as expense_articles_router
from app.api import routes_erp_memory
from app.api import routes_erp_import
from app.api import routes_erp_connectors
from app.api import routes_transaction_memory


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


# --- FUTURE ROUTES ---
# Keep these disabled until each module is cleaned, tested, and reintroduced.
#
# from app.api import routes_pipeline
# from app.api import routes_balance_ge
# from app.api import routes_dashboard_ui
# from app.api import routes_dashboard_v2
# from app.api import routes_dashboard_full
# from app.api import routes_dashboard_mobile
# from app.api import routes_budget
# from app.api import routes_tax
# from app.api import routes_expenses
# from app.api import routes_crm
# from app.api import routes_contracts
# from app.api import routes_tenants
# from app.api import routes_tenants_v2
# from app.api import routes_reconciliation
# from app.api import routes_reconciliation_v2
# from app.api import routes_financial_statements
# from app.api import routes_fpa
# from app.api import routes_reports
# from app.api import routes_reports_dashboard
# from app.api import routes_rbac
# from app.api import routes_notifications
# from app.api import routes_firestore
# from app.api import routes_launch
# from app.api import routes_chat
# from app.api import routes_search
# from app.api import routes_export
# from app.api import routes_gates
# from app.api import routes_security
# from app.api import routes_webhooks_v2
# from app.api import routes_supervisor
# from app.api import routes_ai_journal
# from app.api import routes_audit_engine
# from app.api import routes_finance_engine
# from app.api import routes_strategy
# from app.api import routes_invoices
# from app.api import routes_invoice
# from app.api import routes_docs
# from app.api import routes_api_docs
# from app.api import routes_pdf_report
# from app.api import routes_bank_accounts
# from app.api import routes_currency
# from app.api import routes_1c
# from app.api import routes_bank


# --- RATE LIMITING & SECURITY ---

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers[k] = v
    return response