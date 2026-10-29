from typing import Literal, Optional

from fastapi import APIRouter, Query, Request

from app.api.services.erp_history_import_service import import_posted_history_from_connector
from app.api.authz import require_signed_tenant_permission
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/erp-connectors", tags=["ERP Connectors"])


@router.post("/import-history")
def import_history(
    request: Request,
    source_system: Literal["balance", "oris", "1c"] = Query(..., description="balance | oris | 1c"),
    mode: Literal["demo", "real"] = Query("demo", description="demo | real"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=5000),
):
    tenant_id = require_signed_tenant_permission(request, "posting:write")
    try:
        result = import_posted_history_from_connector(
            source_system=source_system,
            mode=mode,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            tenant_id=tenant_id,
        )
        if not result.get("ok"):
            return error_response("ERP history import incomplete", "ERP_HISTORY_IMPORT_INCOMPLETE", result)
        return ok_response("ERP connector history preview", result)
    except Exception:
        return error_response("ERP history adapter unavailable", "ERP_HISTORY_ADAPTER_UNAVAILABLE")
