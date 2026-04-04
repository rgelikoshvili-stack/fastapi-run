from fastapi import Request
from fastapi.responses import JSONResponse
from app.api.services.auth_service import verify_token

PUBLIC_PATHS = {
    "/health", "/docs", "/openapi.json", "/redoc",
    "/auth/login", "/auth/register", "/static",
}

AUTH_ENABLED = False  # True-ზე გადართვა როცა UI-ში login დაემატება


async def auth_middleware(request: Request, call_next):
    if not AUTH_ENABLED:
        return await call_next(request)

    path = request.url.path
    if any(path.startswith(p) for p in PUBLIC_PATHS):
        return await call_next(request)

    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]

    if not token:
        token = request.query_params.get("token")

    if not token:
        return JSONResponse(
            status_code=401,
            content={"ok": False, "error": "Authorization required"}
        )

    payload = verify_token(token)
    if not payload:
        return JSONResponse(
            status_code=401,
            content={"ok": False, "error": "Invalid or expired token"}
        )

    request.state.user_id   = payload.get("user_id")
    request.state.email      = payload.get("email")
    request.state.role       = payload.get("role")
    request.state.tenant_id  = payload.get("tenant_id", "default")

    return await call_next(request)
