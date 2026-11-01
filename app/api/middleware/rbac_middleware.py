import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from app.api.authz import ROLE_PERMISSIONS
from app.api.policy.permission_map import match_permission
from app.api.observability import structured_log
log = logging.getLogger(__name__)




async def rbac_middleware(request: Request, call_next):
    path = request.url.path
    method = request.method

    # The exact worker callback has no user JWT. Its handler authenticates
    # both the worker HMAC and a Bridge Hub-signed job token before DB access.
    if method == "POST" and path == "/worker/result":
        return await call_next(request)

    public_prefixes = (
        "/auth/",
        "/docs",
        "/openapi.json",
        "/health",
        "/static",
        "/app",
        "/favicon",
        "/api/claude/",
        "/dashboard/",
        "/coa/",
        "/hub-map",
    )

    if method == "GET" and path == "/version":
        return await call_next(request)

    # public endpoints
    if path == "/" or path.startswith(public_prefixes):
        return await call_next(request)

    # Token-in-URL is only allowed on the carefully scoped download paths
    # declared by auth_middleware._DOWNLOAD_PREFIXES.  Auth middleware runs
    # before RBAC and is the ONLY verifier of query-string access tokens.
    # Do not re-verify a token here: doing so would bypass the live membership
    # check and could let a revoked user's download token regain access.

    if not getattr(request.state, "authenticated", False):
        structured_log(
            log,
            logging.INFO,
            "auth_denied",
            method=method,
            path=path,
            tenant_id=getattr(request.state, "tenant_id", None),
            result="denied",
            error_code="UNAUTHORIZED",
        )
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
        structured_log(
            log,
            logging.INFO,
            "permission_denied",
            method=method,
            path=path,
            tenant_id=getattr(request.state, "tenant_id", None),
            role=role,
            required_permission=required_permission,
            result="denied",
            error_code="FORBIDDEN",
        )
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
