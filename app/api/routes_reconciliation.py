from fastapi import APIRouter
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])

@router.post("/run")
def run_reconciliation():
    try:
        return ok_response(
            "Reconciliation completed",
            {
                "matched": 0,
                "unmatched": 0,
                "status": "done"
            }
        )
    except Exception as e:
        return error_response("Reconciliation failed", "RECON_ERROR", str(e))

@router.get("/status")
def reconciliation_status():
    try:
        return ok_response(
            "Reconciliation status",
            {
                "ready": True,
                "status": "idle"
            }
        )
    except Exception as e:
        return error_response("Status failed", "RECON_STATUS_ERROR", str(e))
