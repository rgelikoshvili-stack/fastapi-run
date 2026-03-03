from fastapi import FastAPI
from datetime import datetime, timezone
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

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