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

    # Fallback: ?token= query param (e.g. PDF download in new tab)
    if not getattr(request.state, "authenticated", False):
        _qt = request.query_params.get("token")
        if _qt:
            try:
                from app.api.services.auth_service import verify_token as _vt
                _pl = _vt(_qt, expected_type="access")
                if _pl:
                    request.state.authenticated = True
                    request.state.user_id = _pl.get("sub")
                    request.state.role = _pl.get("role")
                    if _pl.get("tenant_id"):
                        request.state.tenant_id = _pl.get("tenant_id")
            except Exception:
                pass

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