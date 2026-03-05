from fastapi import FastAPI, UploadFile, File
from datetime import datetime, timezone
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import json, os

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Bridge Hub + GAAS v5.2", version="2.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.get("/health")
def health():
    return {"ok": True, "service": "bridge-hub", "version": "2.0",
            "gaas": "v5.2", "architecture": "clean", "sprints_done": 7,
            "timestamp": datetime.now(timezone.utc).isoformat()}

from app.api import routes_bank, routes_accounting, routes_audit, routes_finance
from app.api import routes_strategy, routes_reports, routes_gaas, routes_close
app.include_router(routes_bank.router)
app.include_router(routes_accounting.router)
app.include_router(routes_audit.router)
app.include_router(routes_finance.router)
app.include_router(routes_strategy.router)
app.include_router(routes_reports.router)
app.include_router(routes_gaas.router)
app.include_router(routes_close.router)
from app.api import routes_auth
app.include_router(routes_auth.router)
from app.api import routes_users
app.include_router(routes_users.router)
from app.api import routes_webhooks
app.include_router(routes_webhooks.router)
from app.api import routes_dashboard
app.include_router(routes_dashboard.router)
from app.api import routes_settings
app.include_router(routes_settings.router)
from app.api import routes_observerlog
app.include_router(routes_observerlog.router)
from app.api import routes_validation
app.include_router(routes_validation.router)
from app.api import routes_approval
app.include_router(routes_approval.router)

from app.api.doc_analyzer import analyze, to_dict

DATA_DIR = os.getenv("BRIDGE_DATA_DIR", "./bridge_data")
os.makedirs(DATA_DIR, exist_ok=True)

@app.post("/bridge/doc/analyze")
async def bridge_doc_analyze(file: UploadFile = File(...)):
    data = await file.read()
    res = analyze(file.filename or "uploaded", data)
    result = to_dict(res)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(DATA_DIR, f"analysis_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return {"ok": True, "analysis": result}

@app.post("/bridge/learn/feedback")
async def bridge_learn_feedback(payload: dict):
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(DATA_DIR, f"feedback_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return {"ok": True, "saved": os.path.basename(path)}

@app.get("/bridge/learn/stats")
async def bridge_learn_stats():
    files = os.listdir(DATA_DIR) if os.path.exists(DATA_DIR) else []
    return {
        "ok": True,
        "analysis_count": len([x for x in files if x.startswith("analysis_")]),
        "feedback_count": len([x for x in files if x.startswith("feedback_")])
    }

from app.api import routes_patterns
app.include_router(routes_patterns.router)

from app.api import routes_autonomy
app.include_router(routes_autonomy.router)
