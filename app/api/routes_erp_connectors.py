from typing import Optional

from fastapi import APIRouter, Query

from app.api.services.erp_history_import_service import import_posted_history_from_connector

router = APIRouter(prefix="/erp-connectors", tags=["ERP Connectors"])


@router.post("/import-history")
def import_history(
    source_system: str = Query(..., description="balance | oris | 1c"),
    mode: str = Query("demo", description="demo | real"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=5000),
):
    result = import_posted_history_from_connector(
        source_system=source_system,
        mode=mode,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )
    return {
        "ok": True,
        "message": "ERP connector history imported",
        "data": result,
        "error": None,
    }