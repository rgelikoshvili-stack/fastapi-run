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

    public_prefixes = (
        "/auth/",
        "/docs",
        "/openapi.json",
        "/health",
        "/static",
        "/favicon",
        "/api/ai/",
        "/api/claude/",
        "/dashboard/",
        "/coa/",
        "/debug/ai-routing",
        "/hub-map",
    )

    if method == "GET" and path == "/version":
        return await call_next(request)

    # public endpoints
    if path == "/" or path.startswith(public_prefixes):
        return await call_next(request)

    # ?token= fallback is intentionally restricted to PDF/file download paths only.
    # Using a token in the URL is unsafe for general API calls because Cloud Run
    # access logs record the full URL including query params, which exposes tokens
    # to anyone with log access.  All other API paths must use Authorization header.
    _DOWNLOAD_PREFIXES = ("/api/documents/download/", "/api/reports/export/", "/api/payroll/slip/")
    if not getattr(request.state, "authenticated", False) and path.startswith(_DOWNLOAD_PREFIXES):
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
            except Exception as e:
                log.warning("unexpected error: %s", e)

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
