from fastapi import APIRouter, Query, Request
from pydantic import BaseModel
from typing import Optional

from app.api.response_utils import ok_response, error_response
from app.api.authz import require_permission
from app.api.services.transaction_memory_service import (
    list_transaction_memory,
    save_transaction_memory,
)

router = APIRouter(prefix="/transaction-memory", tags=["transaction-memory"])


class TransactionMemoryUpsertRequest(BaseModel):
    description: Optional[str] = None
    partner: Optional[str] = None
    amount: Optional[float] = None
    account_code: str


@router.post("/upsert")
def transaction_memory_upsert(data: TransactionMemoryUpsertRequest, request: Request):
    require_permission(request, "settings:write")
    try:
        result = save_transaction_memory(
            description=data.description,
            partner=data.partner,
            amount=data.amount,
            account_code=data.account_code,
        )
        return ok_response("Transaction memory upserted", result)
    except Exception as e:
        return error_response(
            "Transaction memory upsert failed",
            "TRANSACTION_MEMORY_UPSERT_ERROR",
            str(e),
        )


@router.get("/list")
def transaction_memory_list(limit: int = Query(100, ge=1, le=1000)):
    try:
        items = list_transaction_memory(limit=limit)
        return ok_response("Transaction memory list", {"items": items, "count": len(items)})
    except Exception as e:
        return error_response(
            "Transaction memory list failed",
            "TRANSACTION_MEMORY_LIST_ERROR",
            str(e),
        )