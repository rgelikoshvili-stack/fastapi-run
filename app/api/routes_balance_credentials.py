"""app/api/routes_balance_credentials.py
Bridge Hub — Per-tenant Balance.ge Credentials API (Task 3)
"""
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional

from app.api.tenant_context import resolve_tenant_id
from app.api.authz import require_permission
from app.api.services.balance_credentials_service import (
    get_credentials_status,
    save_balance_credentials,
)

router = APIRouter(prefix="/balance-credentials", tags=["balance-credentials"])


class BalanceCredsPayload(BaseModel):
    api_key: str
    company_id: Optional[str] = ""
    api_base: Optional[str] = "https://api.balance.ge"


@router.get("/status")
def get_status(request: Request):
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return {"ok": True, **get_credentials_status(tenant_id)}


@router.post("/save")
def save_creds(body: BalanceCredsPayload, request: Request):
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    if not body.api_key:
        return {"ok": False, "error": "api_key required"}
    ok = save_balance_credentials(
        tenant_id=tenant_id,
        api_key=body.api_key,
        company_id=body.company_id or "",
        api_base=body.api_base or "https://api.balance.ge",
    )
    if ok:
        return {"ok": True, "message": "Balance.ge credentials saved"}
    return {"ok": False, "error": "DB save failed"}


@router.post("/test")
def test_connection(request: Request):
    """Test Balance.ge connectivity with current credentials."""
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        from app.api.connectors.balance_connector import BalanceConnector
        conn = BalanceConnector(tenant_id=tenant_id)
        status = conn.status()
        return {"ok": status.get("connected", False), **status}
    except Exception as e:
        return {"ok": False, "error": str(e)}
