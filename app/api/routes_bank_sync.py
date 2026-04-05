"""
app/api/routes_bank_sync.py
Bridge Hub — Bank Direct Sync Routes
TBC + BOG ბანკების პირდაპირი sync
"""
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
from app.api.tenant_context import resolve_tenant_id
from app.api.connectors.bank_sync_connector import (
    TBCConnector, BOGConnector, sync_all_banks
)

router = APIRouter(prefix="/bank-sync", tags=["bank-sync"])


# ========== Models ==========

class SyncRequest(BaseModel):
    days: Optional[int] = 7
    account_id: Optional[str] = "default"


# ========== Status ==========

@router.get("/status")
def bank_sync_status(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    tbc = TBCConnector(tenant_id)
    bog = BOGConnector(tenant_id)
    return {
        "ok": True,
        "tenant_id": tenant_id,
        "banks": {
            "tbc": tbc.status(),
            "bog": bog.status(),
        }
    }


# ========== TBC ==========

@router.post("/tbc/sync")
def sync_tbc(req: SyncRequest, request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    connector = TBCConnector(tenant_id)
    result = connector.sync_transactions(
        account_id=req.account_id,
        days=req.days,
    )
    return result


# ========== BOG ==========

@router.post("/bog/sync")
def sync_bog(req: SyncRequest, request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    connector = BOGConnector(tenant_id)
    result = connector.sync_transactions(
        account_id=req.account_id,
        days=req.days,
    )
    return result


# ========== All Banks ==========

@router.post("/sync-all")
def sync_all(req: SyncRequest, request: Request):
    """
    ყველა ბანკიდან sync + queue-ში დამატება.
    """
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = sync_all_banks(tenant_id=tenant_id, days=req.days)
    return result


@router.get("/sync-all")
def sync_all_get(request: Request, days: int = 7):
    """
    GET ვერსია — browser-იდან ტესტისთვის.
    """
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = sync_all_banks(tenant_id=tenant_id, days=days)
    return result