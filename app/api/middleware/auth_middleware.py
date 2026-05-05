from fastapi import Request
from app.api.services.auth_service import verify_token

PUBLIC_PATH_PREFIXES = (
    "/",
    "/docs",
    "/openapi.json",
    "/health",
    "/auth/login",
    "/auth/register",
    "/auth/refresh",
    "/static",
)

_DOWNLOAD_PREFIXES = (
    "/api/documents/download/",
    "/api/reports/export/",
    "/api/payroll/slip/",
)


async def auth_middleware(request: Request, call_next):
    path = request.url.path

    if any(path == p or path.startswith(p + "/") for p in PUBLIC_PATH_PREFIXES):
        request.state.authenticated = False
        return await call_next(request)

    authorization = request.headers.get("Authorization", "")
    token = None

    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    elif any(path.startswith(p) for p in _DOWNLOAD_PREFIXES):
        token = request.query_params.get("token") or None

    request.state.authenticated = False
    request.state.user_id = None
    request.state.role = None
    # NOTE: tenant_id intentionally NOT reset here.
    # tenant_middleware (outermost, runs first) sets it from X-Tenant-ID header.
    # We only override it if JWT carries a tenant_id (JWT takes priority).

    if token:
        payload = verify_token(token, expected_type="access")
        if payload:
            request.state.authenticated = True
            request.state.user_id = payload.get("sub")
            request.state.role = payload.get("role")
            if payload.get("tenant_id"):
                request.state.tenant_id = payload.get("tenant_id")

    response = await call_next(request)
    return response
