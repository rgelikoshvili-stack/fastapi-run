import logging
from fastapi import Request
from app.api.audit import log_event
log = logging.getLogger(__name__)


SKIP_PREFIXES = (
    "/docs",
    "/openapi.json",
    "/static",
)


async def audit_log_middleware(request: Request, call_next):
    path = request.url.path

    if path.startswith(SKIP_PREFIXES):
        return await call_next(request)

    response = await call_next(request)

    try:
        user_id = getattr(request.state, "user_id", None)
        role = getattr(request.state, "role", None)
        tenant_id = getattr(request.state, "tenant_id", None)
        ip = request.client.host if request.client else None

        log_event(
            action=request.method,
            resource=path,
            resource_id=None,
            actor=str(user_id) if user_id else "anonymous",
            role=role or "anonymous",
            details=f"tenant={tenant_id}; status={response.status_code}",
            status="success" if response.status_code < 400 else "error",
            ip_address=ip,
        )
    except Exception as e:
        log.warning("unexpected error: %s", e)

    return response
