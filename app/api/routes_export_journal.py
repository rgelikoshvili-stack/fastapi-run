from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
import openpyxl, io
from app.api.db import get_conn, _q
from app.api.response_utils import error_response
from app.api.authz import require_permission

router = APIRouter(prefix="/export", tags=["export"])

@router.get("/journal/excel")
async def export_journal_excel(request: Request, status: str = "approved"):
    require_permission(request, "export:any")
    tenant_id = getattr(request.state, "tenant_id", "default")
    try:
        async with get_conn() as conn:
            rows = [dict(r) for r in await conn.fetch(_q(
                "SELECT * FROM journal_drafts WHERE status=%s AND tenant_id=%s ORDER BY created_at DESC"
            ), status, tenant_id)]
    except Exception as e:
        return error_response("Export failed", "EXPORT_ERROR", str(e))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Journal"

    headers = ["ID","Date","Description","Partner","Amount","Debit","Credit","Reason","Confidence","Status"]
    ws.append(headers)

    for r in rows:
        ws.append([
            r.get("id"), r.get("date"), r.get("description"), r.get("partner"),
            r.get("amount"), r.get("debit_account"), r.get("credit_account"),
            r.get("reason"), r.get("confidence"), r.get("status")
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=journal_{status}.xlsx"}
    )
