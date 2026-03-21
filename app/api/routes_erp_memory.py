from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from app.api.response_utils import ok_response, error_response
from app.api.services.erp_memory_service import (
    upsert_erp_posting_memory,
    list_erp_posting_memory,
)

router = APIRouter(prefix="/erp-memory", tags=["erp-memory"])


class ErpMemoryUpsertRequest(BaseModel):
    source_system: str = "balance"
    external_entry_id: Optional[str] = None
    external_doc_id: Optional[str] = None
    doc_type: Optional[str] = None
    description: Optional[str] = None
    partner: Optional[str] = None
    amount: Optional[float] = None
    currency: str = "GEL"
    debit_account: Optional[str] = None
    credit_account: Optional[str] = None
    account_code: Optional[str] = None
    direction: Optional[str] = None
    posting_date: Optional[str] = None


@router.post("/upsert")
def upsert_memory(data: ErpMemoryUpsertRequest):
    try:
        result = upsert_erp_posting_memory(
            source_system=data.source_system,
            external_entry_id=data.external_entry_id,
            external_doc_id=data.external_doc_id,
            doc_type=data.doc_type,
            description=data.description,
            partner=data.partner,
            amount=data.amount,
            currency=data.currency,
            debit_account=data.debit_account,
            credit_account=data.credit_account,
            account_code=data.account_code,
            direction=data.direction,
            posting_date=data.posting_date,
        )
        return ok_response("ERP posting memory upserted", result)
    except Exception as e:
        return error_response("ERP posting memory upsert failed", "ERP_MEMORY_UPSERT_ERROR", str(e))


@router.get("/list")
def list_memory(limit: int = 100):
    try:
        items = list_erp_posting_memory(limit=limit)
        return ok_response("ERP posting memory list", {"items": items, "count": len(items)})
    except Exception as e:
        return error_response("ERP posting memory list failed", "ERP_MEMORY_LIST_ERROR", str(e))