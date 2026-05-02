from fastapi import Request
from fastapi.responses import JSONResponse
from app.api.authz import ROLE_PERMISSIONS
from app.api.policy.permission_map import PERMISSION_MAP


def match_permission(method: str, path: str):
    for allowed_method, prefix, permission in PERMISSION_MAP:
        if (allowed_method == "*" or method == allowed_method) and path.startswith(prefix):
            return permission
    return None


async def rbac_middleware(request: Request, call_next):
    path = request.url.path
    method = request.method

    public_prefixes = (
        "/auth/",
        "/docs",
        "/openapi.json",
        "/health",
        "/metrics",
        "/static",
        "/favicon",
        "/api/ai/",
        "/api/claude/",
        "/dashboard/",
        "/coa/",
        "/debug/ai-routing",
        "/hub-map",
    )

    # public endpoints
    if path == "/" or path.startswith(public_prefixes):
        return await call_next(request)

    # ❗ აქ იყო შენი მთავარი bug
    if not getattr(request.state, "authenticated", False):
        return JSONResponse(
            status_code=401,
            content={
                "ok": False,
                "message": "Unauthorized",
                "data": None,
                "error": {
                    "code": "UNAUTHORIZED",
                    "details": "ავთენტიკაცია აუცილებელია",
                },
            },
        )

    required_permission = match_permission(method, path)

    if not required_permission:
        return await call_next(request)

    role = getattr(request.state, "role", None)

    if not role:
        return JSONResponse(
            status_code=403,
            content={
                "ok": False,
                "message": "Forbidden",
                "data": None,
                "error": {
                    "code": "FORBIDDEN",
                    "details": "როლი ვერ განისაზღვრა",
                },
            },
        )

    allowed_permissions = ROLE_PERMISSIONS.get(role, set())

    if required_permission not in allowed_permissions:
        return JSONResponse(
            status_code=403,
            content={
                "ok": False,
                "message": "Forbidden",
                "data": None,
                "error": {
                    "code": "FORBIDDEN",
                    "details": f"წვდომა აკრძალულია ({required_permission})",
                },
            },
        )

    return await call_next(request)