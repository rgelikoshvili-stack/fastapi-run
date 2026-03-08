from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import io, xml.etree.ElementTree as ET
from datetime import datetime
from app.api.response_utils import ok_response, error_response
from app.api.db import get_db
import psycopg2.extras

router = APIRouter(prefix="/1c", tags=["1c"])

class ExportRequest(BaseModel):
    draft_ids: Optional[List[int]] = None
    status: Optional[str] = "approved"
    format: Optional[str] = "xml"  # xml or csv

def drafts_to_1c_xml(drafts: list) -> str:
    root = ET.Element("V8Exch", attrib={"version": "2.0"})
    doc = ET.SubElement(root, "Document", attrib={
        "type": "JournalEntry",
        "date": datetime.now().strftime("%Y%m%d"),
        "source": "BridgeHub"
    })
    for d in drafts:
        entry = ET.SubElement(doc, "Entry")
        ET.SubElement(entry, "Date").text = str(d.get("date") or "")
        ET.SubElement(entry, "Description").text = str(d.get("description") or "")
        ET.SubElement(entry, "Partner").text = str(d.get("partner") or "")
        ET.SubElement(entry, "DebitAccount").text = str(d.get("debit_account") or "")
        ET.SubElement(entry, "CreditAccount").text = str(d.get("credit_account") or "")
        ET.SubElement(entry, "Amount").text = str(d.get("amount") or 0)
        ET.SubElement(entry, "Currency").text = "GEL"
        ET.SubElement(entry, "Reason").text = str(d.get("reason") or "")
        ET.SubElement(entry, "SourceID").text = str(d.get("id") or "")

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=False)

def drafts_to_1c_csv(drafts: list) -> str:
    lines = ["Date;Description;Partner;DebitAccount;CreditAccount;Amount;Currency;Reason;SourceID"]
    for d in drafts:
        lines.append(";".join([
            str(d.get("date") or ""),
            str(d.get("description") or "").replace(";", ","),
            str(d.get("partner") or "").replace(";", ","),
            str(d.get("debit_account") or ""),
            str(d.get("credit_account") or ""),
            str(d.get("amount") or 0),
            "GEL",
            str(d.get("reason") or ""),
            str(d.get("id") or ""),
        ]))
    return "\n".join(lines)

@router.post("/export")
async def export_1c(req: ExportRequest):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if req.draft_ids:
            cur.execute("SELECT * FROM journal_drafts WHERE id = ANY(%s)", (req.draft_ids,))
        else:
            cur.execute("SELECT * FROM journal_drafts WHERE status=%s ORDER BY created_at", (req.status,))
        drafts = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        return error_response("DB error", "DB_ERROR", str(e))
    finally:
        cur.close(); conn.close()

    if not drafts:
        return error_response("No drafts found", "NOT_FOUND", "")

    if req.format == "csv":
        content = drafts_to_1c_csv(drafts)
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8-sig")),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=1c_export.csv"}
        )
    else:
        content = drafts_to_1c_xml(drafts)
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="application/xml",
            headers={"Content-Disposition": "attachment; filename=1c_export.xml"}
        )

@router.get("/preview/{status}")
async def preview_1c(status: str = "approved"):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM journal_drafts WHERE status=%s ORDER BY created_at LIMIT 20", (status,))
        drafts = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        return error_response("DB error", "DB_ERROR", str(e))
    finally:
        cur.close(); conn.close()

    preview = [{
        "id": d["id"],
        "date": d["date"],
        "description": d["description"],
        "debit": d["debit_account"],
        "credit": d["credit_account"],
        "amount": d["amount"],
        "partner": d["partner"],
    } for d in drafts]

    return ok_response("1C export preview", {
        "count": len(preview),
        "format": "V8Exch XML / CSV",
        "entries": preview
    })
