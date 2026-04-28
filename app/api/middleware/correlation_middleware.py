"""app/api/middleware/correlation_middleware.py
Injects X-Correlation-ID into every request/response for distributed tracing.
"""
import uuid
import logging
from fastapi import Request

log = logging.getLogger(__name__)


async def correlation_middleware(request: Request, call_next):
    correlation_id = (
        request.headers.get("X-Correlation-ID")
        or request.headers.get("X-Request-ID")
        or str(uuid.uuid4())
    )
    request.state.correlation_id = correlation_id

    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response
