from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import psycopg2, psycopg2.extras
import openpyxl, io
from app.api.db import get_db
from app.api.response_utils import error_response

router = APIRouter(prefix="/export", tags=["export"])

@router.get("/journal/excel")
def export_journal_excel(status: str = "approved"):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM journal_drafts WHERE status=%s ORDER BY created_at DESC", (status,))
        rows = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        return error_response("Export failed", "EXPORT_ERROR", str(e))
    finally:
        cur.close(); conn.close()

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
