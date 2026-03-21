from fastapi import APIRouter, Query

from app.api.response_utils import ok_response, error_response
from app.api.services.transaction_memory_service import list_transaction_memory

router = APIRouter(prefix="/transaction-memory", tags=["transaction-memory"])


@router.get("/list")
def transaction_memory_list(limit: int = Query(100, ge=1, le=1000)):
    try:
        items = list_transaction_memory(limit=limit)
        return ok_response("Transaction memory list", {"items": items, "count": len(items)})
    except Exception as e:
        return error_response("Transaction memory list failed", "TRANSACTION_MEMORY_LIST_ERROR", str(e))