from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from app.api.db import get_db
from app.api.response_utils import error_response
import psycopg2.extras

router = APIRouter(prefix="/reports", tags=["reports"])

class ReportRequest(BaseModel):
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    status: Optional[str] = None
    report_type: Optional[str] = "journal"  # journal or reconcile

def build_pdf(drafts: list, recon: dict, req: ReportRequest) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        rightMargin=1.5*cm, leftMargin=1.5*cm,
        topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Title"],
        fontSize=18, textColor=colors.HexColor("#1e40af"), spaceAfter=6)
    sub_style = ParagraphStyle("sub", parent=styles["Normal"],
        fontSize=10, textColor=colors.HexColor("#64748b"), spaceAfter=16)
    heading_style = ParagraphStyle("heading", parent=styles["Heading2"],
        fontSize=13, textColor=colors.HexColor("#1e293b"), spaceAfter=8)

    story = []

    # Header
    story.append(Paragraph("🌉 Bridge Hub", title_style))
    story.append(Paragraph(f"Financial Report — {req.report_type.upper()}", sub_style))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", sub_style))
    story.append(Spacer(1, 0.4*cm))

    # KPI Summary
    story.append(Paragraph("Summary", heading_style))
    kpi_data = [
        ["Metric", "Value"],
        ["Total Transactions", str(recon.get("total_transactions", len(drafts)))],
        ["Total Income", f"₾ {recon.get('total_income', 0):,.2f}"],
        ["Total Expense", f"₾ {recon.get('total_expense', 0):,.2f}"],
        ["Balance", f"₾ {recon.get('balance', 0):,.2f}"],
        ["Status", recon.get("status", "N/A").upper()],
        ["Duplicates", str(recon.get("duplicate_count", 0))],
        ["Unmatched", str(recon.get("unmatched_count", 0))],
    ]
    kpi_table = Table(kpi_data, colWidths=[7*cm, 7*cm])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1e40af")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#f8fafc"), colors.white]),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ("PADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 0.6*cm))

    # Journal Drafts table
    story.append(Paragraph("Journal Entries", heading_style))
    headers = ["ID", "Date", "Description", "Partner", "Dr", "Cr", "Amount", "Status"]
    rows = [headers]
    for d in drafts[:100]:
        rows.append([
            str(d.get("id",""))[:8],
            str(d.get("date",""))[:10],
            str(d.get("description",""))[:30],
            str(d.get("partner",""))[:20],
            str(d.get("debit_account","")),
            str(d.get("credit_account","")),
            f"{float(d.get('amount') or 0):,.2f}",
            str(d.get("status",""))[:12],
        ])
    col_widths = [1.2*cm, 2*cm, 5*cm, 3*cm, 1.5*cm, 1.5*cm, 2.2*cm, 2.2*cm]
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1e40af")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#f8fafc"), colors.white]),
        ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#e2e8f0")),
        ("PADDING", (0,0), (-1,-1), 4),
        ("ALIGN", (6,0), (6,-1), "RIGHT"),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph(f"Total entries shown: {min(len(drafts),100)} of {len(drafts)}", sub_style))

    doc.build(story)
    buf.seek(0)
    return buf.read()

@router.post("/pdf")
def generate_pdf_report(req: ReportRequest):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        query = "SELECT * FROM journal_drafts WHERE 1=1"
        params = []
        if req.date_from:
            query += " AND date >= %s"; params.append(req.date_from)
        if req.date_to:
            query += " AND date <= %s"; params.append(req.date_to)
        if req.status:
            query += " AND status = %s"; params.append(req.status)
        query += " ORDER BY created_at DESC"
        cur.execute(query, params)
        drafts = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        return error_response("DB error", "DB_ERROR", str(e))
    finally:
        cur.close(); conn.close()

    total_income = sum(float(d.get("amount") or 0) for d in drafts if str(d.get("account_code","")).startswith("6"))
    total_expense = sum(float(d.get("amount") or 0) for d in drafts if str(d.get("account_code","")).startswith("7"))
    recon = {
        "total_transactions": len(drafts),
        "total_income": round(total_income, 2),
        "total_expense": round(total_expense, 2),
        "balance": round(total_income - total_expense, 2),
        "status": "balanced" if abs(total_income - total_expense) < 0.01 else "unbalanced",
        "duplicate_count": 0,
        "unmatched_count": sum(1 for d in drafts if d.get("status") == "pending_approval"),
    }

    pdf_bytes = build_pdf(drafts, recon, req)
    filename = f"bridgehub_report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
