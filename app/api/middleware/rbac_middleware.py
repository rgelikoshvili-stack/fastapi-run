import os
from fastapi import Request, HTTPException


PUBLIC_PATHS = {
    "/",
    "/health",
    "/health/",
    "/docs",
    "/openapi.json",
    "/tenants",
    "/tenants/create",
    "/learning/decay",
    "/bank-csv/process",
    "/bank-csv/upload",
    "/transaction-ai/analyze",
    "/approval/autopilot",
    "/approval/queue",
    "/learning/health",
    "/learning/patterns",
    "/learning/patterns/top",
    "/learning/stats",
    "/patterns/learning-health",
    "/patterns/decay/run",
    "/system/summary",
    "/system/overview",
}


def check_permission(role: str, action: str) -> bool:
    if role == "admin":
        return True
    if role == "operator" and action == "write":
        return True
    if role == "viewer" and action == "read":
        return True
    return False


async def rbac_middleware(request: Request, call_next):
    if os.getenv("TEST_MODE") == "1":
        return await call_next(request)

    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    # path prefix check — dynamic routes
    public_prefixes = (
        "/bank-csv/",
        "/transaction-ai/",
        "/approval/",
        "/learning/",
        "/patterns/",
        "/system/",
        "/posting/",
        "/coa/",
        "/export/",
        "/audit/",
        "/erp-memory/",
        "/transaction-memory/",
        "/expense-articles/",
        "/tenants/",
        "/auth/",
        "/balance-ge/",
        "/erp-connectors/",
        "/search/",
        "/reports/",
        "/dashboard/",
        "/ui/",
    )
    if request.url.path.startswith(public_prefixes):
        return await call_next(request)

    role = request.headers.get("X-Role", "viewer")
    request.state.role = role

    if request.method == "POST":
        if not check_permission(role, "write"):
            raise HTTPException(status_code=403, detail="Forbidden")

    return await call_next(request)