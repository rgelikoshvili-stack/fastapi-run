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


async def auth_middleware(request: Request, call_next):
    path = request.url.path

    if any(path == p or path.startswith(p + "/") for p in PUBLIC_PATH_PREFIXES):
        return await call_next(request)

    authorization = request.headers.get("Authorization", "")
    token = None

    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()

    if token:
        payload = verify_token(token, expected_type="access")
        if payload:
            request.state.user_id = payload.get("sub")
            request.state.role = payload.get("role")
            request.state.tenant_id = payload.get("tenant_id")
            request.state.authenticated = True
        else:
            request.state.authenticated = False
    else:
        request.state.authenticated = False

    return await call_next(request)