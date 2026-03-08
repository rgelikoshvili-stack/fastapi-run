from fastapi import FastAPI, Request, Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.api.security import limiter, rate_limit_exceeded_handler, SECURITY_HEADERS
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from datetime import datetime, timezone
import os, json

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
            "error": {
                "code": "INTERNAL_ERROR",
                "details": str(exc),
            },
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
                "details": exc.errors(),
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
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "details": str(exc.detail),
            },
        },
    )


from app.api import routes_pipeline
app.include_router(routes_pipeline.router)

from app.api import routes_coa
app.include_router(routes_coa.router)

from app.api import routes_ai_journal
app.include_router(routes_ai_journal.router)

from app.api import routes_supervisor
app.include_router(routes_supervisor.router)

from app.api import routes_audit_engine
app.include_router(routes_audit_engine.router)

from app.api import routes_bank_csv
from app.api import routes_bank_process
from app.api import routes_approval
from app.api import routes_export_journal
from app.api import routes_invoice
from app.api import routes_docs
from app.api import routes_balance_ge
from app.api import routes_1c
from app.api import routes_dashboard_ui
from app.api import routes_dashboard_v2
from app.api import routes_pdf_report
from app.api import routes_webhooks_v2
from app.api import routes_api_docs
from app.api import routes_invoices
from app.api import routes_budget
from app.api import routes_tax
from app.api import routes_dashboard_mobile
from app.api import routes_expenses
from app.api import routes_crm
from app.api import routes_bank_accounts
from app.api import routes_financial_statements
from app.api import routes_audit_log
from app.api import routes_contracts
from app.api import routes_currency
from app.api import routes_reports_dashboard
from app.api import routes_tenants_v2
from app.api import routes_reconciliation_v2
app.include_router(routes_bank_csv.router)
app.include_router(routes_bank_process.router)
app.include_router(routes_approval.router)
app.include_router(routes_export_journal.router)
app.include_router(routes_invoice.router)
app.include_router(routes_docs.router)
app.include_router(routes_balance_ge.router)
app.include_router(routes_1c.router)
app.include_router(routes_dashboard_ui.router)
app.include_router(routes_dashboard_v2.router)
app.include_router(routes_pdf_report.router)
app.include_router(routes_webhooks_v2.router)
app.include_router(routes_api_docs.router)
app.include_router(routes_invoices.router)
app.include_router(routes_budget.router)
app.include_router(routes_tax.router)
app.include_router(routes_dashboard_mobile.router)
app.include_router(routes_expenses.router)
app.include_router(routes_crm.router)
app.include_router(routes_bank_accounts.router)
app.include_router(routes_financial_statements.router)
app.include_router(routes_audit_log.router)
app.include_router(routes_contracts.router)
app.include_router(routes_currency.router)
app.include_router(routes_reports_dashboard.router)
app.include_router(routes_tenants_v2.router)
app.include_router(routes_reconciliation_v2.router)

from app.api import routes_reconciliation
app.include_router(routes_reconciliation.router)

from app.api import routes_finance_engine
app.include_router(routes_finance_engine.router)

from app.api import routes_strategy
app.include_router(routes_strategy.router)

from app.api import routes_dashboard_full
app.include_router(routes_dashboard_full.router)

from app.api import routes_learning
app.include_router(routes_learning.router)

from app.api import routes_fpa
app.include_router(routes_fpa.router)

from app.api import routes_reports
app.include_router(routes_reports.router)

from app.api import routes_notifications
from app.api import routes_rbac
app.include_router(routes_notifications.router)
app.include_router(routes_rbac.router)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers[k] = v
    return response

from app.api import routes_tenants
app.include_router(routes_tenants.router)

from app.api import routes_chat
app.include_router(routes_chat.router)

from app.api import routes_search
app.include_router(routes_search.router)

from app.api import routes_export
app.include_router(routes_export.router)

from app.api import routes_gates
app.include_router(routes_gates.router)

from app.api import routes_security
app.include_router(routes_security.router)

from app.api import routes_health
app.include_router(routes_health.router)

from app.api import routes_firestore
app.include_router(routes_firestore.router)

from app.api import routes_launch
app.include_router(routes_launch.router)

from app.api import routes_transaction_ai
app.include_router(routes_transaction_ai.router)




