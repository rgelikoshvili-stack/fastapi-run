from typing import List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.response_utils import ok_response, error_response
from app.api.services.erp_import_service import import_erp_history
from app.api.authz import require_permission

router = APIRouter(prefix="/erp-memory/import", tags=["erp-memory-import"])


class ErpHistoryItem(BaseModel):
    source_system: Optional[str] = "balance"
    external_entry_id: Optional[str] = None
    external_doc_id: Optional[str] = None
    doc_type: Optional[str] = None
    description: Optional[str] = None
    partner: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = "GEL"
    debit_account: Optional[str] = None
    credit_account: Optional[str] = None
    account_code: Optional[str] = None
    direction: Optional[str] = None
    posting_date: Optional[str] = None


class ErpImportRequest(BaseModel):
    source_system: Optional[str] = "balance"
    items: List[ErpHistoryItem]


@router.post("/json")
def import_erp_history_json(data: ErpImportRequest, request: Request):
    require_permission(request, "posting:write")
    try:
        result = import_erp_history(
            items=[item.model_dump() for item in data.items],
            default_source_system=data.source_system or "balance",
        )
        return ok_response("ERP history imported", result)
    except Exception as e:
        return error_response("ERP history import failed", "ERP_HISTORY_IMPORT_ERROR", str(e))