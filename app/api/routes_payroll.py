from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import logging
import io
from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, error_response
from app.api.tenant_context import resolve_tenant_id
from app.api.authz import require_permission

from app.api.services.payroll_service import (
    calculate_employee_payroll,
    calculate_payroll,
    generate_payroll_drafts,
    generate_rsge_xml,
)
from app.api.observability import structured_log

router = APIRouter(prefix="/payroll", tags=["payroll"])
log = logging.getLogger(__name__)


# ========== Models ==========
class EmployeeInput(BaseModel):
    name: str
    gross_salary: float
    id: Optional[str] = None


class PayrollRequest(BaseModel):
    employees: List[EmployeeInput]
    period: Optional[str] = None


class SingleEmployeeRequest(BaseModel):
    name: str
    gross_salary: float
    employee_id: Optional[str] = None
    period: Optional[str] = None


# ===============================
# WRITE ENDPOINTS
# ===============================
@router.post("/calculate")
def payroll_calculate(req: PayrollRequest, request: Request):
    require_permission(request, "payroll:write")

    employees = [e.dict() for e in req.employees]
    payroll = calculate_payroll(employees, req.period)
    structured_log(log, logging.INFO, "payroll_calculated",
                   tenant_id=resolve_tenant_id(getattr(request.state, "tenant_id", None)),
                   period=req.period, employee_count=len(employees), result="success")
    return ok_response("Payroll calculated", {"payroll": payroll})


@router.post("/calculate/single")
def payroll_calculate_single(req: SingleEmployeeRequest, request: Request):
    require_permission(request, "payroll:write")

    result = calculate_employee_payroll(
        gross_salary=req.gross_salary,
        employee_name=req.name,
        employee_id=req.employee_id,
        period=req.period,
    )
    structured_log(log, logging.INFO, "payroll_calculated_single",
                   tenant_id=resolve_tenant_id(getattr(request.state, "tenant_id", None)),
                   period=req.period, employee_id=req.employee_id, result="success")
    return ok_response("ok", {"employee": result})


@router.post("/generate-drafts")
async def payroll_generate_drafts(req: PayrollRequest, request: Request):
    require_permission(request, "payroll:write")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    employees = [e.dict() for e in req.employees]

    payroll = calculate_payroll(employees, req.period)

    if not payroll.get("ok"):
        return error_response("გამოთვლის შეცდომა", "ERROR", "")

    drafts = await generate_payroll_drafts(payroll, tenant_id=tenant_id)

    return ok_response("Payroll drafts generated", {
        "tenant_id": tenant_id,
        "payroll": payroll,
        "drafts": drafts,
    })


@router.post("/rs-ge-xml")
def payroll_rsge_xml(req: PayrollRequest, request: Request):
    require_permission(request, "payroll:write")

    employees = [e.dict() for e in req.employees]
    payroll = calculate_payroll(employees, req.period)

    xml = generate_rsge_xml(payroll)
    period = req.period or datetime.now().strftime("%Y-%m")
    filename = f"rsge_payg_{period}.xml"

    return StreamingResponse(
        io.BytesIO(xml.encode("utf-8")),
        media_type="application/xml",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ===============================
# READ ENDPOINTS
# ===============================
@router.get("/history")
async def payroll_history(
    request: Request,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    require_permission(request, "payroll:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    async with get_conn() as conn:
        items = [dict(r) for r in await conn.fetch(_q("""
            SELECT id, date, description, amount, status, created_at
            FROM journal_drafts
            WHERE tenant_id = %s
              AND (
                    description ILIKE %s
                 OR description ILIKE %s
                 OR description ILIKE %s
                 OR description ILIKE %s
              )
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """), tenant_id, "%salary%", "%payroll%", "%ხელფას%", "%შრომის ანაზღაურ%", limit, offset)]
        total = await conn.fetchval(_q("""
            SELECT COUNT(*) FROM journal_drafts
            WHERE tenant_id = %s
              AND (
                    description ILIKE %s
                 OR description ILIKE %s
                 OR description ILIKE %s
                 OR description ILIKE %s
              )
        """), tenant_id, "%salary%", "%payroll%", "%ხელფას%", "%შრომის ანაზღაურ%") or 0

    return ok_response("Payroll history", {
        "tenant_id": tenant_id,
        "count": len(items),
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items,
    })


@router.post("/payslip-pdf")
def payroll_payslip_pdf(req: PayrollRequest, request: Request):
    """Generate PDF pay slips for all employees in the payroll run."""
    require_permission(request, "payroll:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import io as _io

    employees = [e.dict() for e in req.employees]
    period = req.period or datetime.now().strftime("%Y-%m")
    results = calculate_payroll(employees, period)
    payroll_data = results.get("employees", []) if isinstance(results, dict) else []

    buf = _io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             leftMargin=2*cm, rightMargin=2*cm,
                             topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle("Title", parent=styles["Heading1"],
                                  fontSize=16, spaceAfter=6, textColor=colors.HexColor("#1a365d"))
    header_style = ParagraphStyle("Header", parent=styles["Normal"],
                                   fontSize=10, spaceAfter=2, textColor=colors.grey)
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10)

    for emp in payroll_data:
        story.append(Paragraph("Bridge Hub — Pay Slip", title_style))
        story.append(Paragraph(f"Period: {period}  |  Employee: {emp.get('name', 'N/A')}  |  Tenant: {tenant_id}", header_style))
        story.append(Spacer(1, 0.3*cm))

        data = [
            ["Description", "Amount (GEL)"],
            ["Gross Salary", f"{emp.get('gross_salary', 0):,.2f}"],
            ["PIT (20%)", f"-{emp.get('pit', 0):,.2f}"],
            ["Pension (Employee 2%)", f"-{emp.get('pension_employee', 0):,.2f}"],
            ["Net Salary", f"{emp.get('net_salary', 0):,.2f}"],
            ["", ""],
            ["Employer Pension (2%)", f"{emp.get('pension_employer', 0):,.2f}"],
            ["Total Employer Cost", f"{emp.get('total_employer_cost', 0):,.2f}"],
        ]

        tbl = Table(data, colWidths=[10*cm, 5*cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a365d")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, -1), 10),
            ("ALIGN",      (1, 0), (1, -1), "RIGHT"),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
            ("BACKGROUND", (0, 4), (-1, 4), colors.HexColor("#e8f5e9")),
            ("FONTNAME",   (0, 4), (-1, 4), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
            ("LEFTPADDING",  (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING",   (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 1*cm))

        sig_data = [
            ["Employer signature: _______________", "Employee signature: _______________"],
            [f"Date: {period}", "Date: _______________"],
        ]
        sig_tbl = Table(sig_data, colWidths=[8*cm, 8*cm])
        sig_tbl.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.grey),
        ]))
        story.append(sig_tbl)
        story.append(Spacer(1, 2*cm))

    if not payroll_data:
        story.append(Paragraph("No payroll data to display.", body_style))

    doc.build(story)
    buf.seek(0)

    filename = f"payslips_{period}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/status")
def payroll_status(request: Request):
    require_permission(request, "payroll:read")

    return ok_response("Payroll status", {
        "status": "active",
        "features": [
            "calculate",
            "calculate/single",
            "generate-drafts",
            "rs-ge-xml",
            "history",
            "payslip-pdf",
        ],
    })
