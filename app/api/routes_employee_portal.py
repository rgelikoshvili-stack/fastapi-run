"""app/api/routes_employee_portal.py — Employee management + pension fund transfer."""
import logging
import secrets
from typing import Optional

import psycopg2.extras
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel

from app.api.db import get_db
from app.api.authz import require_permission
from app.api.tenant_context import resolve_tenant_id
from app.api.response_utils import ok_response, error_response, http_error

log = logging.getLogger(__name__)
router = APIRouter(prefix="/employees", tags=["employees"])
pension_router = APIRouter(prefix="/payroll", tags=["payroll"])


def _ensure_tables(conn):
    cur = conn.cursor()
    cur.execute("""
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
    """)
    cur.execute("""
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
    """)
    conn.commit()
    cur.close()


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
def list_employees(
    request: Request,
    status: str = Query("active"),
    q: str = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    require_permission(request, "payroll:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        _ensure_tables(conn)
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
        cur.execute(f"""
            SELECT id, employee_id, name, personal_number, email, position,
                   department, gross_salary, hire_date, status, created_at
            FROM employees {where}
            ORDER BY name
            LIMIT %s OFFSET %s
        """, params + [limit, offset])
        items = [dict(r) for r in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) AS total FROM employees {where}", params)
        total = cur.fetchone()["total"]
    finally:
        cur.close()
        conn.close()
    return ok_response("Employees", {"total": total, "items": items})


@router.post("")
def create_employee(body: EmployeeCreate, request: Request):
    require_permission(request, "payroll:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        _ensure_tables(conn)
        if body.personal_number:
            cur.execute("""
                INSERT INTO employees
                    (tenant_id, employee_id, name, personal_number, email,
                     position, department, gross_salary, hire_date)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (tenant_id, personal_number) DO UPDATE SET
                    name = EXCLUDED.name, email = EXCLUDED.email,
                    position = EXCLUDED.position, department = EXCLUDED.department,
                    gross_salary = EXCLUDED.gross_salary
                RETURNING id
            """, (tenant_id, body.employee_id, body.name, body.personal_number,
                  body.email, body.position, body.department, body.gross_salary, body.hire_date))
        else:
            cur.execute("""
                INSERT INTO employees
                    (tenant_id, employee_id, name, email, position, department, gross_salary, hire_date)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """, (tenant_id, body.employee_id, body.name, body.email,
                  body.position, body.department, body.gross_salary, body.hire_date))
        emp_id = cur.fetchone()["id"]
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return error_response("Failed to save employee", "DB_ERROR", str(e))
    finally:
        cur.close()
        conn.close()
    return ok_response("Employee saved", {"id": emp_id})


@router.get("/{emp_id}")
def get_employee(emp_id: int, request: Request):
    require_permission(request, "payroll:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        _ensure_tables(conn)
        cur.execute("""
            SELECT id, employee_id, name, personal_number, email, position,
                   department, gross_salary, hire_date, status, created_at
            FROM employees WHERE id=%s AND tenant_id=%s
        """, (emp_id, tenant_id))
        emp = cur.fetchone()
        if not emp:
            return http_error(404, "Employee not found", "NOT_FOUND")
        emp = dict(emp)
        cur.execute("""
            SELECT id, date, description, amount, status, created_at
            FROM journal_drafts
            WHERE tenant_id=%s AND (partner=%s OR description ILIKE %s)
              AND description ILIKE '%%salary%%'
            ORDER BY created_at DESC LIMIT 12
        """, (tenant_id, emp.get("name", ""), f"%{emp.get('name', '')}%"))
        emp["recent_payslips"] = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()
    return ok_response("Employee", emp)


@router.delete("/{emp_id}")
def deactivate_employee(emp_id: int, request: Request):
    require_permission(request, "payroll:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE employees SET status='inactive' WHERE id=%s AND tenant_id=%s",
                    (emp_id, tenant_id))
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return ok_response("Employee deactivated", {"id": emp_id})


@router.post("/{emp_id}/portal-token")
def generate_portal_token(emp_id: int, request: Request):
    """Generate a 30-day access token for employee self-service portal."""
    require_permission(request, "payroll:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_tables(conn)
        token = secrets.token_urlsafe(32)
        cur.execute("""
            UPDATE employees
            SET portal_token = %s, portal_token_expires = NOW() + INTERVAL '30 days'
            WHERE id=%s AND tenant_id=%s
            RETURNING name, email
        """, (token, emp_id, tenant_id))
        row = cur.fetchone()
        if not row:
            return http_error(404, "Employee not found", "NOT_FOUND")
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return error_response("Token generation failed", "DB_ERROR", str(e))
    finally:
        cur.close()
        conn.close()
    return ok_response("Portal token generated", {
        "token": token,
        "portal_url": f"/employees/portal/{token}",
        "employee_name": row[0],
        "expires_in_days": 30,
    })


@router.get("/portal/{token}")
def employee_portal(token: str):
    """Employee self-service — token-based, no auth header required."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT id, tenant_id, name, personal_number, email, position,
                   department, gross_salary
            FROM employees
            WHERE portal_token=%s AND portal_token_expires > NOW()
        """, (token,))
        emp = cur.fetchone()
        if not emp:
            return http_error(404, "Invalid or expired portal link", "TOKEN_INVALID")
        emp = dict(emp)
        tenant_id = emp["tenant_id"]
        cur.execute("""
            SELECT id, date, description, amount, status, created_at
            FROM journal_drafts
            WHERE tenant_id=%s
              AND (partner=%s OR description ILIKE %s)
              AND description ILIKE '%%salary%%'
            ORDER BY created_at DESC LIMIT 24
        """, (tenant_id, emp["name"], f"%{emp.get('personal_number', '_NONE_')}%"))
        emp["payslips"] = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()
    return ok_response("Employee portal", emp)


# ── Pension fund transfer ─────────────────────────────────────────────────────

@pension_router.post("/pension-transfer")
def pension_fund_transfer(body: PensionTransferRequest, request: Request):
    """
    Generate pension fund transfer record for a payroll period.
    Journal: Dr 6120 Pension Employer Contribution / Cr 3345 Pension Payable
    Georgian rates: employee 2%, employer 2% (of gross salary).
    """
    require_permission(request, "payroll:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        _ensure_tables(conn)
        params: list = [tenant_id]
        extra = ""
        if body.employees:
            placeholders = ",".join(["%s"] * len(body.employees))
            extra = f" AND name = ANY(ARRAY[{placeholders}])"
            params += body.employees
        cur.execute(f"""
            SELECT name, personal_number, gross_salary
            FROM employees
            WHERE tenant_id=%s AND status='active' {extra}
        """, params)
        employees = [dict(r) for r in cur.fetchall()]

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

        cur.execute("""
            INSERT INTO pension_transfers
                (tenant_id, period, employee_count,
                 total_employee_pension, total_employer_pension, total_amount)
            VALUES (%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (tenant_id, body.period, len(employees), total_emp, total_empr, total))
        transfer_id = cur.fetchone()["id"]

        cur.execute("""
            INSERT INTO journal_drafts
                (tenant_id, date, description, amount,
                 debit_account, credit_account, account_code,
                 reason, confidence, status, source_type)
            VALUES (%s, NOW()::date, %s, %s,
                    '6120', '3345', '6120',
                    'pension_fund', 0.95, 'pending_approval', 'payroll')
        """, (tenant_id, f"Pension employer contribution {body.period}", total_empr))

        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return error_response("Pension transfer failed", "DB_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

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
def list_pension_transfers(
    request: Request,
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    require_permission(request, "payroll:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        _ensure_tables(conn)
        cur.execute("""
            SELECT id, period, employee_count, total_employee_pension,
                   total_employer_pension, total_amount, status, created_at
            FROM pension_transfers
            WHERE tenant_id=%s
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (tenant_id, limit, offset))
        items = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()
    return ok_response("Pension transfers", {"items": items})
