"""
app/api/services/payroll_service.py
Bridge Hub — Payroll Service
PAYG (2%) + საშემოსავლო გადასახადი + RS.ge ფორმატი
georgia_pack.py-ს გამოიყენებს.
"""
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from typing import Optional
import logging
import re
import json
from xml.etree import ElementTree as ET
from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, error_response
from app.policy.localization.georgia_pack import (
    calculate_payg, get_account, VAT_RATE, PAYG_RATE, PIT_RATE
)

log = logging.getLogger(__name__)
EMPLOYER_PENSION_RATE = PAYG_RATE
EMPLOYER_PENSION_EXPENSE_ACCOUNT = "7220"
EMPLOYER_PENSION_PAYABLE_ACCOUNT = "3335"
PAYROLL_FINALIZABLE_STATUSES = {"draft"}
PAYROLL_FINALIZED_STATUSES = {"pending_approval"}
PAYROLL_FINALIZING_STATUS = "finalizing"


_CREATE_PAYROLL_RUNS = """
    CREATE TABLE IF NOT EXISTS payroll_runs (
        id SERIAL PRIMARY KEY,
        tenant_id VARCHAR(100) NOT NULL,
        period VARCHAR(7) NOT NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'draft',
        employee_count INT DEFAULT 0,
        total_gross NUMERIC(12,2) DEFAULT 0,
        total_pit NUMERIC(12,2) DEFAULT 0,
        total_employee_pension NUMERIC(12,2) DEFAULT 0,
        total_employer_pension NUMERIC(12,2) DEFAULT 0,
        total_net NUMERIC(12,2) DEFAULT 0,
        total_employer_cost NUMERIC(12,2) DEFAULT 0,
        draft_ids JSONB DEFAULT '[]'::jsonb,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    )
"""


_CREATE_PAYROLL_RUN_LINES = """
    CREATE TABLE IF NOT EXISTS payroll_run_lines (
        id SERIAL PRIMARY KEY,
        tenant_id VARCHAR(100) NOT NULL,
        run_id INT NOT NULL REFERENCES payroll_runs(id) ON DELETE CASCADE,
        employee_db_id INT,
        employee_id VARCHAR(50),
        employee_name VARCHAR(255) NOT NULL,
        personal_number VARCHAR(20),
        gross_salary NUMERIC(12,2) NOT NULL,
        pit_20pct NUMERIC(12,2) NOT NULL,
        employee_pension_2pct NUMERIC(12,2) NOT NULL,
        employer_pension_2pct NUMERIC(12,2) NOT NULL,
        net_salary NUMERIC(12,2) NOT NULL,
        total_employer_cost NUMERIC(12,2) NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
"""


def normalize_payroll_report_filters(
    employee_id: Optional[str] = None,
    year: Optional[int] = None,
) -> tuple[Optional[str], Optional[int]]:
    """Normalize payroll ledger filters shared by report and payroll routes."""
    normalized_employee_id = employee_id.strip() if employee_id is not None else None
    if normalized_employee_id == "":
        normalized_employee_id = None
    if normalized_employee_id is not None:
        if not normalized_employee_id.isdigit():
            raise ValueError("Employee ID must contain digits only")
        if len(normalized_employee_id) > 32:
            raise ValueError("Employee ID is too long")
    if year is not None and (year < 1900 or year > 2100):
        raise ValueError("Year must be between 1900 and 2100")
    return normalized_employee_id, year


def validate_payroll_period(period: Optional[str]) -> str:
    normalized = (period or datetime.now().strftime("%Y-%m")).strip()
    if not re.fullmatch(r"\d{4}-\d{2}", normalized):
        raise ValueError("Period must use YYYY-MM format")
    month = int(normalized[5:7])
    if month < 1 or month > 12:
        raise ValueError("Period month must be between 01 and 12")
    return normalized


async def ensure_payroll_erp_tables(conn) -> None:
    await conn.execute(_q(_CREATE_PAYROLL_RUNS))
    await conn.execute(_q(_CREATE_PAYROLL_RUN_LINES))


# ========== Payroll Calculation ==========

def calculate_employee_payroll(
    gross_salary: float,
    employee_name: str,
    employee_id: Optional[str] = None,
    period: Optional[str] = None,
) -> dict:
    """
    ერთი თანამშრომლის ხელფასის გამოთვლა.
    PAYG 2% + საშემოსავლო 20%
    """
    gross = Decimal(str(gross_salary))
    period = period or datetime.now().strftime("%Y-%m")

    payg = calculate_payg(gross)
    pit = (gross * PIT_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    employer_pension = (gross * EMPLOYER_PENSION_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    net = gross - Decimal(str(payg["payg"])) - pit

    return {
        "employee_name": employee_name,
        "employee_id": employee_id,
        "period": period,
        "gross_salary": float(gross),
        "payg_2pct": float(payg["payg"]),
        "pit_20pct": float(pit),
        "employer_pension_2pct": float(employer_pension),
        "total_deductions": float(payg["payg"]) + float(pit),
        "net_salary": float(net),
        "total_employer_cost": float(gross + employer_pension),
        "accounts": {
            "salary_expense": get_account("salary"),
            "payg_payable": "3120",
            "pit_payable": "3320",
            "employer_pension_expense": EMPLOYER_PENSION_EXPENSE_ACCOUNT,
            "employer_pension_payable": EMPLOYER_PENSION_PAYABLE_ACCOUNT,
            "bank": get_account("bank"),
        }
    }


def calculate_payroll(employees: list, period: Optional[str] = None) -> dict:
    """
    მრავალი თანამშრომლის payroll გამოთვლა.
    """
    period = validate_payroll_period(period)
    results = []
    total_gross = Decimal("0")
    total_payg = Decimal("0")
    total_pit = Decimal("0")
    total_employer_pension = Decimal("0")
    total_net = Decimal("0")

    for emp in employees:
        result = calculate_employee_payroll(
            gross_salary=emp.get("gross_salary", 0),
            employee_name=emp.get("name", ""),
            employee_id=emp.get("id"),
            period=period,
        )
        results.append(result)
        total_gross += Decimal(str(result["gross_salary"]))
        total_payg += Decimal(str(result["payg_2pct"]))
        total_pit += Decimal(str(result["pit_20pct"]))
        total_employer_pension += Decimal(str(result["employer_pension_2pct"]))
        total_net += Decimal(str(result["net_salary"]))

    return {
        "ok": True,
        "period": period,
        "employee_count": len(results),
        "employees": results,
        "totals": {
            "gross": float(total_gross),
            "payg": float(total_payg),
            "pit": float(total_pit),
            "employer_pension": float(total_employer_pension),
            "net": float(total_net),
            "total_deductions": float(total_payg + total_pit),
            "total_employer_cost": float(total_gross + total_employer_pension),
        }
    }


async def create_payroll_run(
    tenant_id: str,
    period: Optional[str] = None,
    employee_ids: Optional[list[int]] = None,
) -> dict:
    """Create a tenant-scoped payroll run from active employees without posting."""
    period = validate_payroll_period(period)
    employee_ids = employee_ids or []
    async with get_conn() as conn:
        await ensure_payroll_erp_tables(conn)
        params: list = [tenant_id]
        employee_filter = ""
        if employee_ids:
            placeholders = ",".join(["%s"] * len(employee_ids))
            employee_filter = f" AND id IN ({placeholders})"
            params.extend(employee_ids)
        rows = [dict(r) for r in await conn.fetch(_q(f"""
            SELECT id, employee_id, name, personal_number, gross_salary
            FROM employees
            WHERE tenant_id = %s AND status = 'active'{employee_filter}
            ORDER BY name
        """), *params)]

        if not rows:
            raise ValueError("NO_ACTIVE_EMPLOYEES")

        payroll = calculate_payroll([
            {
                "id": row.get("employee_id") or row.get("personal_number"),
                "name": row["name"],
                "gross_salary": float(row.get("gross_salary") or 0),
            }
            for row in rows
        ], period)
        totals = payroll["totals"]

        async with conn.transaction():
            run_id = await conn.fetchval(_q("""
                INSERT INTO payroll_runs (
                    tenant_id, period, status, employee_count,
                    total_gross, total_pit, total_employee_pension,
                    total_employer_pension, total_net, total_employer_cost
                ) VALUES (%s,%s,'draft',%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """), tenant_id, period, payroll["employee_count"], totals["gross"], totals["pit"],
                totals["payg"], totals["employer_pension"], totals["net"],
                totals["total_employer_cost"])

            for row, emp in zip(rows, payroll["employees"]):
                await conn.execute(_q("""
                    INSERT INTO payroll_run_lines (
                        tenant_id, run_id, employee_db_id, employee_id,
                        employee_name, personal_number, gross_salary,
                        pit_20pct, employee_pension_2pct, employer_pension_2pct,
                        net_salary, total_employer_cost
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """), tenant_id, run_id, row["id"], row.get("employee_id"), row["name"],
                    row.get("personal_number"), emp["gross_salary"], emp["pit_20pct"],
                    emp["payg_2pct"], emp["employer_pension_2pct"], emp["net_salary"],
                    emp["total_employer_cost"])

    return await get_payroll_run(tenant_id, run_id)


async def list_payroll_runs(tenant_id: str, limit: int = 50, offset: int = 0) -> dict:
    async with get_conn() as conn:
        await ensure_payroll_erp_tables(conn)
        items = [dict(r) for r in await conn.fetch(_q("""
            SELECT id, period, status, employee_count, total_gross, total_pit,
                   total_employee_pension, total_employer_pension, total_net,
                   total_employer_cost, draft_ids, created_at, updated_at
            FROM payroll_runs
            WHERE tenant_id = %s
            ORDER BY period DESC, created_at DESC
            LIMIT %s OFFSET %s
        """), tenant_id, limit, offset)]
        total = await conn.fetchval(_q("""
            SELECT COUNT(*) FROM payroll_runs WHERE tenant_id = %s
        """), tenant_id) or 0
    return {"total": total, "items": items, "limit": limit, "offset": offset}


async def get_payroll_run(tenant_id: str, run_id: int) -> dict:
    async with get_conn() as conn:
        await ensure_payroll_erp_tables(conn)
        run = await conn.fetchrow(_q("""
            SELECT id, period, status, employee_count, total_gross, total_pit,
                   total_employee_pension, total_employer_pension, total_net,
                   total_employer_cost, draft_ids, created_at, updated_at
            FROM payroll_runs
            WHERE id = %s AND tenant_id = %s
        """), run_id, tenant_id)
        if not run:
            raise ValueError("PAYROLL_RUN_NOT_FOUND")
        lines = [dict(r) for r in await conn.fetch(_q("""
            SELECT id, employee_db_id, employee_id, employee_name, personal_number,
                   gross_salary, pit_20pct, employee_pension_2pct,
                   employer_pension_2pct, net_salary, total_employer_cost
            FROM payroll_run_lines
            WHERE run_id = %s AND tenant_id = %s
            ORDER BY employee_name
        """), run_id, tenant_id)]
    data = dict(run)
    data["lines"] = lines
    return data


async def finalize_payroll_run(tenant_id: str, run_id: int) -> dict:
    """Finalize payroll into journal drafts only; approval/posting remains separate."""
    run = await get_payroll_run(tenant_id, run_id)
    if run["status"] in PAYROLL_FINALIZED_STATUSES:
        draft_ids = run.get("draft_ids") or []
        run["drafts"] = {
            "ok": True,
            "drafts_created": 0,
            "draft_ids": draft_ids,
            "tenant_id": tenant_id,
            "already_finalized": True,
        }
        run["already_finalized"] = True
        return run
    if run["status"] == PAYROLL_FINALIZING_STATUS:
        raise ValueError("PAYROLL_RUN_FINALIZATION_IN_PROGRESS")
    if run["status"] not in PAYROLL_FINALIZABLE_STATUSES:
        raise ValueError("PAYROLL_RUN_ALREADY_FINALIZED")

    async with get_conn() as conn:
        await ensure_payroll_erp_tables(conn)
        claimed = await conn.fetchval(_q("""
            UPDATE payroll_runs
            SET status = 'finalizing',
                updated_at = NOW()
            WHERE id = %s AND tenant_id = %s AND status = 'draft'
            RETURNING id
        """), run_id, tenant_id)
    if not claimed:
        latest = await get_payroll_run(tenant_id, run_id)
        if latest["status"] in PAYROLL_FINALIZED_STATUSES:
            draft_ids = latest.get("draft_ids") or []
            latest["drafts"] = {
                "ok": True,
                "drafts_created": 0,
                "draft_ids": draft_ids,
                "tenant_id": tenant_id,
                "already_finalized": True,
            }
            latest["already_finalized"] = True
            return latest
        raise ValueError("PAYROLL_RUN_FINALIZATION_IN_PROGRESS")

    employees = [
        {
            "employee_name": line["employee_name"],
            "employee_id": line.get("employee_id") or line.get("personal_number"),
            "period": run["period"],
            "gross_salary": float(line["gross_salary"]),
            "payg_2pct": float(line["employee_pension_2pct"]),
            "pit_20pct": float(line["pit_20pct"]),
            "employer_pension_2pct": float(line["employer_pension_2pct"]),
            "net_salary": float(line["net_salary"]),
            "total_employer_cost": float(line["total_employer_cost"]),
        }
        for line in run["lines"]
    ]
    payroll = calculate_payroll([
        {"name": line["employee_name"], "id": line.get("employee_id"), "gross_salary": float(line["gross_salary"])}
        for line in run["lines"]
    ], run["period"])
    payroll["employees"] = employees

    try:
        drafts = await generate_payroll_drafts(payroll, tenant_id=tenant_id)
    except Exception:
        async with get_conn() as conn:
            await ensure_payroll_erp_tables(conn)
            await conn.execute(_q("""
                UPDATE payroll_runs
                SET status = 'draft',
                    updated_at = NOW()
                WHERE id = %s AND tenant_id = %s AND status = 'finalizing'
            """), run_id, tenant_id)
        raise
    if not drafts.get("ok"):
        async with get_conn() as conn:
            await ensure_payroll_erp_tables(conn)
            await conn.execute(_q("""
                UPDATE payroll_runs
                SET status = 'draft',
                    updated_at = NOW()
                WHERE id = %s AND tenant_id = %s AND status = 'finalizing'
            """), run_id, tenant_id)
        raise ValueError("PAYROLL_DRAFT_GENERATION_FAILED")

    async with get_conn() as conn:
        await ensure_payroll_erp_tables(conn)
        await conn.execute(_q("""
            UPDATE payroll_runs
            SET status = 'pending_approval',
                draft_ids = %s::jsonb,
                updated_at = NOW()
            WHERE id = %s AND tenant_id = %s AND status = 'finalizing'
        """), json.dumps(drafts.get("draft_ids", [])), run_id, tenant_id)

    updated = await get_payroll_run(tenant_id, run_id)
    updated["drafts"] = drafts
    return updated


async def get_payroll_period_report(tenant_id: str, period: str) -> dict:
    period = validate_payroll_period(period)
    async with get_conn() as conn:
        await ensure_payroll_erp_tables(conn)
        lines = [dict(r) for r in await conn.fetch(_q("""
            SELECT pr.id AS run_id, pr.status, pr.period,
                   line.employee_name, line.employee_id, line.personal_number,
                   line.gross_salary, line.pit_20pct, line.employee_pension_2pct,
                   line.employer_pension_2pct, line.net_salary,
                   line.total_employer_cost
            FROM payroll_run_lines line
            JOIN payroll_runs pr
              ON pr.id = line.run_id AND pr.tenant_id = line.tenant_id
            WHERE line.tenant_id = %s AND pr.period = %s
            ORDER BY line.employee_name
        """), tenant_id, period)]

    total_gross = sum(float(line["gross_salary"] or 0) for line in lines)
    total_pit = sum(float(line["pit_20pct"] or 0) for line in lines)
    total_employee_pension = sum(float(line["employee_pension_2pct"] or 0) for line in lines)
    total_employer_pension = sum(float(line["employer_pension_2pct"] or 0) for line in lines)
    total_net = sum(float(line["net_salary"] or 0) for line in lines)
    return {
        "period": period,
        "count": len(lines),
        "totals": {
            "gross": round(total_gross, 2),
            "pit": round(total_pit, 2),
            "employee_pension": round(total_employee_pension, 2),
            "employer_pension": round(total_employer_pension, 2),
            "net": round(total_net, 2),
        },
        "lines": lines,
    }


# ========== Draft Generation ==========

async def generate_payroll_drafts(
    payroll: dict,
    tenant_id: str = "default",
) -> dict:
    """Payroll-იდან journal drafts-ის შექმნა. ყოველი თანამშრომლისთვის 4 entry."""
    _INSERT = _q("""
        INSERT INTO journal_drafts (
            date, description, partner, amount,
            debit_account, credit_account, account_code,
            reason, confidence, status, source_type, tenant_id, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        RETURNING id
    """)
    period = payroll.get("period", datetime.now().strftime("%Y-%m"))
    date = f"{period}-01"
    created_ids = []

    try:
        async with get_conn() as conn:
            async with conn.transaction():
                for emp in payroll.get("employees", []):
                    name = emp["employee_name"]
                    employer_pension = emp.get("employer_pension_2pct")
                    if employer_pension is None:
                        employer_pension = round(float(emp.get("gross_salary", 0)) * float(EMPLOYER_PENSION_RATE), 2)

                    entries = [
                        (date, f"ხელფასი — {name} ({period})", name, emp["gross_salary"],
                         get_account("salary"), get_account("bank"), get_account("salary"),
                         "payroll_salary", 0.95, "pending_approval", "payroll", tenant_id),
                        (date, f"PAYG 2% — {name} ({period})", name, emp["payg_2pct"],
                         "3330", get_account("bank"), "3330",
                         "payroll_payg", 0.95, "pending_approval", "payroll", tenant_id),
                        (date, f"საშემოსავლო 20% — {name} ({period})", name, emp["pit_20pct"],
                         "3320", get_account("bank"), "3320",
                         "payroll_pit", 0.95, "pending_approval", "payroll", tenant_id),
                        (date, f"დამსაქმებლის საპენსიო 2% — {name} ({period})", name, employer_pension,
                         EMPLOYER_PENSION_EXPENSE_ACCOUNT, EMPLOYER_PENSION_PAYABLE_ACCOUNT,
                         EMPLOYER_PENSION_EXPENSE_ACCOUNT,
                         "payroll_employer_pension", 0.95, "pending_approval", "payroll", tenant_id),
                    ]
                    for args in entries:
                        row = await conn.fetchrow(_INSERT, *args)
                        created_ids.append(row["id"])

        data = {
            "period": period,
            "drafts_created": len(created_ids),
            "draft_ids": created_ids,
            "tenant_id": tenant_id,
        }
        return {**ok_response("Payroll drafts created", data), **data}
    except Exception:
        log.exception("Payroll draft generation failed tenant=%s period=%s", tenant_id, period)
        return error_response("Payroll draft generation failed", "PAYROLL_ERROR")


def generate_rsge_xml(payroll: dict) -> str:
    """
    RS.ge-ისთვის XML ფორმატის გენერაცია.
    """
    period = payroll.get("period", datetime.now().strftime("%Y-%m"))
    root = ET.Element("Declaration", {"Period": period, "Type": "PAYG"})
    employees_el = ET.SubElement(root, "Employees")

    for emp in payroll.get("employees", []):
        employee_el = ET.SubElement(employees_el, "Employee")
        ET.SubElement(employee_el, "Name").text = str(emp["employee_name"])
        if emp.get("employee_id"):
            ET.SubElement(employee_el, "PersonalID").text = str(emp["employee_id"])
        ET.SubElement(employee_el, "GrossSalary").text = f'{float(emp["gross_salary"]):.2f}'
        ET.SubElement(employee_el, "PAYG").text = f'{float(emp["payg_2pct"]):.2f}'
        ET.SubElement(employee_el, "PIT").text = f'{float(emp["pit_20pct"]):.2f}'
        ET.SubElement(employee_el, "NetSalary").text = f'{float(emp["net_salary"]):.2f}'

    totals = payroll.get("totals", {})
    totals_el = ET.SubElement(root, "Totals")
    ET.SubElement(totals_el, "TotalGross").text = f'{float(totals.get("gross", 0)):.2f}'
    ET.SubElement(totals_el, "TotalPAYG").text = f'{float(totals.get("payg", 0)):.2f}'
    ET.SubElement(totals_el, "TotalPIT").text = f'{float(totals.get("pit", 0)):.2f}'
    ET.SubElement(totals_el, "TotalEmployerPension").text = f'{float(totals.get("employer_pension", 0)):.2f}'
    ET.SubElement(totals_el, "TotalNet").text = f'{float(totals.get("net", 0)):.2f}'

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
