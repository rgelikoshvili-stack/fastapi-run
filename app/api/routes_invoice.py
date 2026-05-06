from fastapi import APIRouter, Request, UploadFile, File

from app.api.response_utils import error_response
from app.services.route_bridge_service import bridge_invoice_payload
from app.api.authz import require_permission

router = APIRouter(prefix="/invoice", tags=["invoice"])


@router.post("/parse")
async def parse_invoice(request: Request, file: UploadFile = File(...)):
    require_permission(request, "approval:write")
    try:
        content = await file.read()

        payload = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(content),
            "content": content,
        }

        return bridge_invoice_payload(payload)

    except Exception as e:
        return error_response(
            "Invoice parse failed",
            "INVOICE_PARSE_ERROR",
            str(e),
        )