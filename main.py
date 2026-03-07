from fastapi import FastAPI, UploadFile, File
from fastapi.staticfiles import StaticFiles
import os, json
from datetime import datetime, timezone

app = FastAPI(title="Bridge Hub v1.0.0", version="1.0.0")

from fastapi.responses import FileResponse, HTMLResponse

@app.get("/")
def root():
    try:
        return FileResponse("static/index.html")
    except:
        return HTMLResponse("<h1>Bridge Hub v1.0.0</h1><p><a href='/docs'>API Docs</a></p>")
        
from app.api import routes_pipeline
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(status_code=422, content={"ok": False, "error": str(exc)})


from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"ok": False, "error": str(exc.detail)})


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
app.include_router(routes_bank_csv.router)
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
app.include_router(routes_notifications.router)
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
