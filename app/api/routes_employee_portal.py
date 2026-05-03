"""app/api/routes_employee_portal.py — Employee management + pension fund transfer."""
import logging
import secrets
from typing import Optional

from fastapi import APIRouter, Request, Query
from pydantic import BaseModel

from app.api.db import get_conn, _q
from app.api.authz import require_permission
from app.api.tenant_context import resolve_tenant_id
from app.api.response_utils import ok_response, error_response, http_error

log = logging.getLogger(__name__)
router = APIRouter(prefix="/employees", tags=["employees"])
pension_router = APIRouter(prefix="/payroll", tags=["payroll"])


_CREATE_EMPLOYEES = """
    CREATE TABLE IF NOT EXISTS employees (
        id SERIAL PRIMARY KEY,
        tenant_id VARCHAR(100) NOT NULL,
        employee_id VARCHAR(50),
        name VARCHAR(255) NOT NULL,
        personal_number VARCHAR(20),
        email VARCHAR(255),
        position VARCHAR(255),
        department VARCHAR(255),
        gross_salary NUMERIC(12,2) DEFAULT 0,
        hire_date DATE,
        status VARCHAR(20) DEFAULT 'active',
        portal_token VARCHAR(64),
        portal_token_expires TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(tenant_id, personal_number)
    )
"""

_CREATE_PENSION_TRANSFERS = """
    CREATE TABLE IF NOT EXISTS pension_transfers (
        id SERIAL PRIMARY KEY,
        tenant_id VARCHAR(100) NOT NULL,
        period VARCHAR(7) NOT NULL,
        employee_count INT DEFAULT 0,
        total_employee_pension NUMERIC(12,2) DEFAULT 0,
        total_employer_pension NUMERIC(12,2) DEFAULT 0,
        total_amount NUMERIC(12,2) DEFAULT 0,
        status VARCHAR(20) DEFAULT 'pending',
        transfer_reference VARCHAR(100),
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
"""


async def _ensure_tables(conn):
    await conn.execute(_CREATE_EMPLOYEES)
    await conn.execute(_CREATE_PENSION_TRANSFERS)


class EmployeeCreate(BaseModel):
    name: str
    employee_id: Optional[str] = None
    personal_number: Optional[str] = None
    email: Optional[str] = None
    position: Optional[str] = None
    department: Optional[str] = None
    gross_salary: float = 0.0
    hire_date: Optional[str] = None


class PensionTransferRequest(BaseModel):
    period: str  # YYYY-MM
    employees: Optional[list] = None  # None = all active


# ── Employee CRUD ─────────────────────────────────────────────────────────────

@router.get("")
async def list_employees(
    request: Request,
    status: str = Query("active"),
    q: str = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    require_permission(request, "payroll:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conditions = ["tenant_id = %s"]
    params: list = [tenant_id]
    if status != "all":
        conditions.append("status = %s")
        params.append(status)
    if q:
        conditions.append("(name ILIKE %s OR email ILIKE %s OR position ILIKE %s)")
        like = f"%{q}%"
        params += [like, like, like]
    where = "WHERE " + " AND ".join(conditions)
    async with get_conn() as conn:
        await _ensure_tables(conn)
        items = [dict(r) for r in await conn.fetch(_q(f"""
            SELECT id, employee_id, name, personal_number, email, position,
                   department, gross_salary, hire_date, status, created_at
            FROM employees {where}
            ORDER BY name
            LIMIT %s OFFSET %s
        """), *params, limit, offset)]
        total = await conn.fetchval(_q(f"SELECT COUNT(*) FROM employees {where}"), *params) or 0
    return ok_response("Employees", {"total": total, "items": items})


@router.post("")
async def create_employee(body: EmployeeCreate, request: Request):
    require_permission(request, "payroll:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            await _ensure_tables(conn)
            if body.personal_number:
                emp_id = await conn.fetchval(_q("""
                    INSERT INTO employees
                        (tenant_id, employee_id, name, personal_number, email,
                         position, department, gross_salary, hire_date)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (tenant_id, personal_number) DO UPDATE SET
                        name = EXCLUDED.name, email = EXCLUDED.email,
                        position = EXCLUDED.position, department = EXCLUDED.department,
                        gross_salary = EXCLUDED.gross_salary
                    RETURNING id
                """), tenant_id, body.employee_id, body.name, body.personal_number,
                    body.email, body.position, body.department, body.gross_salary, body.hire_date)
            else:
                emp_id = await conn.fetchval(_q("""
                    INSERT INTO employees
                        (tenant_id, employee_id, name, email, position, department, gross_salary, hire_date)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                """), tenant_id, body.employee_id, body.name, body.email,
                    body.position, body.department, body.gross_salary, body.hire_date)
    except Exception as e:
        return error_response("Failed to save employee", "DB_ERROR", str(e))
    return ok_response("Employee saved", {"id": emp_id})


@router.get("/{emp_id}")
async def get_employee(emp_id: int, request: Request):
    require_permission(request, "payroll:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        await _ensure_tables(conn)
        emp = await conn.fetchrow(_q("""
            SELECT id, employee_id, name, personal_number, email, position,
                   department, gross_salary, hire_date, status, created_at
            FROM employees WHERE id=%s AND tenant_id=%s
        """), emp_id, tenant_id)
        if not emp:
            return http_error(404, "Employee not found", "NOT_FOUND")
        emp = dict(emp)
        payslips = [dict(r) for r in await conn.fetch(_q("""
            SELECT id, date, description, amount, status, created_at
            FROM journal_drafts
            WHERE tenant_id=%s AND (partner=%s OR description ILIKE %s)
              AND description ILIKE '%salary%'
            ORDER BY created_at DESC LIMIT 12
        """), tenant_id, emp.get("name", ""), f"%{emp.get('name', '')}%")]
        emp["recent_payslips"] = payslips
    return ok_response("Employee", emp)


@router.delete("/{emp_id}")
async def deactivate_employee(emp_id: int, request: Request):
    require_permission(request, "payroll:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        await conn.execute(_q("UPDATE employees SET status='inactive' WHERE id=%s AND tenant_id=%s"),
                           emp_id, tenant_id)
    return ok_response("Employee deactivated", {"id": emp_id})


@router.post("/{emp_id}/portal-token")
async def generate_portal_token(emp_id: int, request: Request):
    """Generate a 30-day access token for employee self-service portal."""
    require_permission(request, "payroll:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        token = secrets.token_urlsafe(32)
        async with get_conn() as conn:
            await _ensure_tables(conn)
            row = await conn.fetchrow(_q("""
                UPDATE employees
                SET portal_token = %s, portal_token_expires = NOW() + INTERVAL '30 days'
                WHERE id=%s AND tenant_id=%s
                RETURNING name, email
            """), token, emp_id, tenant_id)
        if not row:
            return http_error(404, "Employee not found", "NOT_FOUND")
    except Exception as e:
        return error_response("Token generation failed", "DB_ERROR", str(e))
    return ok_response("Portal token generated", {
        "token": token,
        "portal_url": f"/employees/portal/{token}",
        "employee_name": row["name"],
        "expires_in_days": 30,
    })


@router.get("/portal/{token}")
async def employee_portal(token: str):
    """Employee self-service — token-based, no auth header required."""
    async with get_conn() as conn:
        emp = await conn.fetchrow(_q("""
            SELECT id, tenant_id, name, personal_number, email, position,
                   department, gross_salary
            FROM employees
            WHERE portal_token=%s AND portal_token_expires > NOW()
        """), token)
        if not emp:
            return http_error(404, "Invalid or expired portal link", "TOKEN_INVALID")
        emp = dict(emp)
        tenant_id = emp["tenant_id"]
        emp["payslips"] = [dict(r) for r in await conn.fetch(_q("""
            SELECT id, date, description, amount, status, created_at
            FROM journal_drafts
            WHERE tenant_id=%s
              AND (partner=%s OR description ILIKE %s)
              AND description ILIKE '%salary%'
            ORDER BY created_at DESC LIMIT 24
        """), tenant_id, emp["name"], f"%{emp.get('personal_number', '_NONE_')}%")]
    return ok_response("Employee portal", emp)


# ── Pension fund transfer ─────────────────────────────────────────────────────

@pension_router.post("/pension-transfer")
async def pension_fund_transfer(body: PensionTransferRequest, request: Request):
    """
    Generate pension fund transfer record for a payroll period.
    Journal: Dr 6120 Pension Employer Contribution / Cr 3345 Pension Payable
    Georgian rates: employee 2%, employer 2% (of gross salary).
    """
    require_permission(request, "payroll:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            await _ensure_tables(conn)
            params: list = [tenant_id]
            extra = ""
            if body.employees:
                placeholders = ",".join(["%s"] * len(body.employees))
                extra = f" AND name = ANY(ARRAY[{placeholders}])"
                params += body.employees
            employees = [dict(r) for r in await conn.fetch(_q(f"""
                SELECT name, personal_number, gross_salary
                FROM employees
                WHERE tenant_id=%s AND status='active' {extra}
            """), *params)]

            if not employees:
                return http_error(404, "No active employees found", "NO_EMPLOYEES")

            lines = []
            for e in employees:
                gross = float(e["gross_salary"] or 0)
                emp_pen = round(gross * 0.02, 2)
                empr_pen = round(gross * 0.02, 2)
                lines.append({
                    "name": e["name"],
                    "personal_number": e["personal_number"],
                    "gross_salary": gross,
                    "employee_pension": emp_pen,
                    "employer_pension": empr_pen,
                    "total_pension": emp_pen + empr_pen,
                })

            total_emp  = round(sum(l["employee_pension"] for l in lines), 2)
            total_empr = round(sum(l["employer_pension"] for l in lines), 2)
            total      = round(total_emp + total_empr, 2)

            async with conn.transaction():
                transfer_id = await conn.fetchval(_q("""
                    INSERT INTO pension_transfers
                        (tenant_id, period, employee_count,
                         total_employee_pension, total_employer_pension, total_amount)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    RETURNING id
                """), tenant_id, body.period, len(employees), total_emp, total_empr, total)

                await conn.execute(_q("""
                    INSERT INTO journal_drafts
                        (tenant_id, date, description, amount,
                         debit_account, credit_account, account_code,
                         reason, confidence, status, source_type)
                    VALUES (%s, NOW()::date, %s, %s,
                            '6120', '3345', '6120',
                            'pension_fund', 0.95, 'pending_approval', 'payroll')
                """), tenant_id, f"Pension employer contribution {body.period}", total_empr)
    except Exception as e:
        return error_response("Pension transfer failed", "DB_ERROR", str(e))

    return ok_response("Pension transfer created", {
        "transfer_id": transfer_id,
        "period": body.period,
        "employee_count": len(employees),
        "employee_pension_total": total_emp,
        "employer_pension_total": total_empr,
        "total_transfer": total,
        "journal": {"debit": "6120 Pension Employer", "credit": "3345 Pension Payable"},
        "lines": lines,
    })


@pension_router.get("/pension-transfers")
async def list_pension_transfers(
    request: Request,
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    require_permission(request, "payroll:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        await _ensure_tables(conn)
        items = [dict(r) for r in await conn.fetch(_q("""
            SELECT id, period, employee_count, total_employee_pension,
                   total_employer_pension, total_amount, status, created_at
            FROM pension_transfers
            WHERE tenant_id=%s
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """), tenant_id, limit, offset)]
    return ok_response("Pension transfers", {"items": items})
