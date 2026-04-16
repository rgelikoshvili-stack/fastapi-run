"""
app/api/routes_payroll.py
Bridge Hub — Payroll Routes
PAYG + PIT + RS.ge XML
"""
from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import io
import psycopg2.extras

from app.api.db import get_db
from app.api.tenant_context import resolve_tenant_id
from app.api.services.payroll_service import (
    calculate_employee_payroll,
    calculate_payroll,
    generate_payroll_drafts,
    generate_rsge_xml,
)

router = APIRouter(prefix="/payroll", tags=["payroll"])


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


# ========== Endpoints ==========

@router.post("/calculate")
def payroll_calculate(req: PayrollRequest, request: Request):
    """
    Payroll-ის გამოთვლა — draft-ები არ იქმნება.
    """
    employees = [e.dict() for e in req.employees]
    result = calculate_payroll(employees, req.period)
    return result


@router.post("/calculate/single")
def payroll_calculate_single(req: SingleEmployeeRequest):
    """
    ერთი თანამშრომლის გამოთვლა.
    """
    result = calculate_employee_payroll(
        gross_salary=req.gross_salary,
        employee_name=req.name,
        employee_id=req.employee_id,
        period=req.period,
    )
    return {"ok": True, "employee": result}


@router.post("/generate-drafts")
def payroll_generate_drafts(req: PayrollRequest, request: Request):
    """
    Payroll გამოთვლა + journal drafts-ის შექმნა.
    """
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    employees = [e.dict() for e in req.employees]
    payroll = calculate_payroll(employees, req.period)

    if not payroll.get("ok"):
        return {"ok": False, "error": "გამოთვლის შეცდომა"}

    drafts = generate_payroll_drafts(payroll, tenant_id=tenant_id)

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "payroll": payroll,
        "drafts": drafts,
    }


@router.post("/rs-ge-xml")
def payroll_rsge_xml(req: PayrollRequest, request: Request):
    """
    RS.ge XML ფორმატის გენერაცია.
    """
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


@router.get("/history")
def payroll_history(
    request: Request,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    Payroll-generated drafts history.
    """
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            """
            SELECT
                id,
                date,
                description,
                amount,
                status,
                created_at
            FROM journal_drafts
            WHERE tenant_id = %s
              AND (
                    description ILIKE '%salary%'
                 OR description ILIKE '%payroll%'
                 OR description ILIKE '%ხელფას%'
                 OR description ILIKE '%შრომის ანაზღაურ%'
              )
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (tenant_id, limit, offset),
        )
        items = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT COUNT(*) AS total
            FROM journal_drafts
            WHERE tenant_id = %s
              AND (
                    description ILIKE '%salary%'
                 OR description ILIKE '%payroll%'
                 OR description ILIKE '%ხელფას%'
                 OR description ILIKE '%შრომის ანაზღაურ%'
              )
            """,
            (tenant_id,),
        )
        total = cur.fetchone()["total"]

        return {
            "ok": True,
            "tenant_id": tenant_id,
            "count": len(items),
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": items,
        }

    finally:
        cur.close()
        conn.close()


@router.get("/status")
def payroll_status():
    return {
        "ok": True,
        "status": "active",
        "features": [
            "calculate — PAYG 2% + PIT 20% გამოთვლა",
            "calculate/single — ერთი თანამშრომელი",
            "generate-drafts — drafts ავტომატურად",
            "rs-ge-xml — RS.ge XML ფორმატი",
            "history — payroll draft history",
        ],
        "rates": {
            "payg": "2%",
            "pit": "20%",
            "currency": "GEL",
        }
    }