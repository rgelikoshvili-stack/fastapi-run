"""app/api/routes_email_collector.py
Bridge Hub — Email Collector API (STEP 1.6 backend)
Per-tenant Gmail credentials management + manual poll trigger.
"""
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.authz import require_permission
from app.api.tenant_context import resolve_tenant_id
from app.api.response_utils import ok_response, error_response
from app.api.services.email_collector import (
    get_tenant_email_credentials,
    save_tenant_email_credentials,
    test_imap_connection,
    collect_tenant_inbox,
)

router = APIRouter(prefix="/email-collector", tags=["email-collector"])


class EmailCredentials(BaseModel):
    email: str
    app_password: str


@router.get("/status")
def email_collector_status(request: Request):
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    creds = get_tenant_email_credentials(tenant_id)
    if creds:
        return ok_response("ok", {"configured": True, "email": creds["email"]})
    return ok_response("ok", {"configured": False})


@router.post("/test")
def test_connection(body: EmailCredentials, request: Request):
    require_permission(request, "settings:write")
    return test_imap_connection(body.email, body.app_password)


@router.post("/credentials")
def save_credentials(body: EmailCredentials, request: Request):
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    # Validate credentials before saving
    test = test_imap_connection(body.email, body.app_password)
    if not test.get("ok"):
        return error_response(test.get("error", "IMAP connection failed"), "ERROR", "")
    saved = save_tenant_email_credentials(tenant_id, body.email, body.app_password)
    if saved:
        return ok_response("ok", {"message": "Credentials saved and IMAP connection verified"})
    return error_response("DB save failed", "ERROR", "")


@router.post("/poll")
async def manual_poll(request: Request):
    """Manually trigger inbox polling for current tenant."""
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = await collect_tenant_inbox(tenant_id)
    if result.get("status") == "ok":
        return ok_response("Inbox collected", result)
    return error_response("Inbox collection failed", "ERROR", result.get("error", ""))
