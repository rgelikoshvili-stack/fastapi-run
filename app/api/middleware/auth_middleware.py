from fastapi import Request
from app.api.response_utils import http_error
from app.api.services.auth_service import verify_token
from app.api.observability import structured_log
import logging

log = logging.getLogger(__name__)

PUBLIC_PATH_PREFIXES = (
    "/",
    "/docs",
    "/openapi.json",
    "/health",
    "/auth/login",
    "/auth/register",
    "/auth/refresh",
    "/static",
    "/app",
)

PUBLIC_GET_PATHS = (
    "/version",
)

# This callback is not public: it is authenticated in-handler by both the
# worker HMAC and a Bridge Hub-signed job token. It cannot use a user JWT.
INTERNAL_JOB_CALLBACK_PATHS = {("POST", "/worker/result")}

_DOWNLOAD_PREFIXES = (
    "/api/documents/download/",
    "/api/reports/export/",
    "/api/payroll/slip/",
)


async def auth_middleware(request: Request, call_next):
    path = request.url.path
    method = request.method

    if (method, path) in INTERNAL_JOB_CALLBACK_PATHS:
        request.state.authenticated = False
        from app.api.db import authenticated_tenant_context
        with authenticated_tenant_context(None):
            return await call_next(request)

    if method == "GET" and path in PUBLIC_GET_PATHS:
        request.state.authenticated = False
        from app.api.db import authenticated_tenant_context
        with authenticated_tenant_context(None):
            return await call_next(request)
    if any(path == p or path.startswith(p + "/") for p in PUBLIC_PATH_PREFIXES):
        request.state.authenticated = False
        from app.api.db import authenticated_tenant_context
        with authenticated_tenant_context(None):
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
    request.state.auth_tenant_id = None
    # NOTE: tenant_id intentionally NOT reset here.
    # tenant_middleware (outermost, runs first) sets it from X-Tenant-ID header.
    # We only override it if JWT carries a tenant_id (JWT takes priority).

    if token:
        payload = verify_token(token, expected_type="access")
        if payload:
            request.state.authenticated = True
            request.state.user_id = payload.get("sub")
            request.state.role = payload.get("role")
            tenant_claim = payload.get("tenant_id")
            request.state.auth_tenant_id = tenant_claim
            if (
                isinstance(tenant_claim, str)
                and tenant_claim
                and tenant_claim == tenant_claim.strip()
                and tenant_claim.casefold() != "default"
            ):
                request.state.tenant_id = tenant_claim
                from app.api.db import authenticated_tenant_context
                with authenticated_tenant_context(tenant_claim):
                    return await call_next(request)
            if tenant_claim is not None:
                return http_error(403, "Invalid authenticated tenant context", "FORBIDDEN")
            # Invalid or absent signed tenant claims never inherit the raw
            # tenant header as DB context. Tenant-scoped routes reject the
            # missing claim; global routes continue without tenant RLS scope.
            request.state.tenant_id = None
        else:
            structured_log(
                log,
                logging.INFO,
                "auth_token_invalid",
                path=path,
                tenant_id=getattr(request.state, "tenant_id", None),
                result="denied",
                error_code="INVALID_TOKEN",
            )
    elif path not in PUBLIC_PATH_PREFIXES and not any(path.startswith(p) for p in _DOWNLOAD_PREFIXES):
        structured_log(
            log,
            logging.INFO,
            "auth_token_missing",
            path=path,
            tenant_id=getattr(request.state, "tenant_id", None),
            result="denied",
            error_code="UNAUTHORIZED",
        )

    from app.api.db import authenticated_tenant_context
    with authenticated_tenant_context(None):
        return await call_next(request)
