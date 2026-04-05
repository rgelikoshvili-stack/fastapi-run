"""
app/api/services/payroll_service.py
Bridge Hub — Payroll Service
PAYG (2%) + საშემოსავლო გადასახადი + RS.ge ფორმატი
georgia_pack.py-ს გამოიყენებს.
"""
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from typing import Optional
import psycopg2.extras
from app.api.db import get_db
from app.policy.localization.georgia_pack import (
    calculate_payg, get_account, VAT_RATE, PAYG_RATE, PIT_RATE
)


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
    net = gross - Decimal(str(payg["payg"])) - pit

    return {
        "employee_name": employee_name,
        "employee_id": employee_id,
        "period": period,
        "gross_salary": float(gross),
        "payg_2pct": float(payg["payg"]),
        "pit_20pct": float(pit),
        "total_deductions": float(payg["payg"]) + float(pit),
        "net_salary": float(net),
        "accounts": {
            "salary_expense": get_account("salary"),
            "payg_payable": "3120",
            "pit_payable": "3160",
            "bank": get_account("bank"),
        }
    }


def calculate_payroll(employees: list, period: Optional[str] = None) -> dict:
    """
    მრავალი თანამშრომლის payroll გამოთვლა.
    """
    period = period or datetime.now().strftime("%Y-%m")
    results = []
    total_gross = Decimal("0")
    total_payg = Decimal("0")
    total_pit = Decimal("0")
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
            "net": float(total_net),
            "total_deductions": float(total_payg + total_pit),
        }
    }


# ========== Draft Generation ==========

def generate_payroll_drafts(
    payroll: dict,
    tenant_id: str = "default",
) -> dict:
    """
    Payroll-იდან journal drafts-ის შექმნა.
    ყოველი თანამშრომლისთვის 3 entry:
    1. ხელფასის ხარჯი
    2. PAYG გადახდა
    3. საშემოსავლო გადახდა
    """
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    period = payroll.get("period", datetime.now().strftime("%Y-%m"))
    date = f"{period}-01"
    created_ids = []

    try:
        for emp in payroll.get("employees", []):
            name = emp["employee_name"]

            # 1. ხელფასის ხარჯი
            cur.execute("""
                INSERT INTO journal_drafts (
                    date, description, partner, amount,
                    debit_account, credit_account, account_code,
                    reason, confidence, status, source_type, tenant_id, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING id
            """, (
                date,
                f"ხელფასი — {name} ({period})",
                name,
                emp["gross_salary"],
                get_account("salary"),
                get_account("bank"),
                get_account("salary"),
                "payroll_salary",
                0.95,
                "pending_approval",
                "payroll",
                tenant_id,
            ))
            created_ids.append(cur.fetchone()["id"])

            # 2. PAYG გადახდა (2%)
            cur.execute("""
                INSERT INTO journal_drafts (
                    date, description, partner, amount,
                    debit_account, credit_account, account_code,
                    reason, confidence, status, source_type, tenant_id, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING id
            """, (
                date,
                f"PAYG 2% — {name} ({period})",
                name,
                emp["payg_2pct"],
                "3120",
                get_account("bank"),
                "3120",
                "payroll_payg",
                0.95,
                "pending_approval",
                "payroll",
                tenant_id,
            ))
            created_ids.append(cur.fetchone()["id"])

            # 3. საშემოსავლო გადახდა (20%)
            cur.execute("""
                INSERT INTO journal_drafts (
                    date, description, partner, amount,
                    debit_account, credit_account, account_code,
                    reason, confidence, status, source_type, tenant_id, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING id
            """, (
                date,
                f"საშემოსავლო 20% — {name} ({period})",
                name,
                emp["pit_20pct"],
                "3160",
                get_account("bank"),
                "3160",
                "payroll_pit",
                0.95,
                "pending_approval",
                "payroll",
                tenant_id,
            ))
            created_ids.append(cur.fetchone()["id"])

        conn.commit()
        return {
            "ok": True,
            "period": period,
            "drafts_created": len(created_ids),
            "draft_ids": created_ids,
            "tenant_id": tenant_id,
        }
    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        cur.close()
        conn.close()


# ========== RS.ge XML Format ==========

def generate_rsge_xml(payroll: dict) -> str:
    """
    RS.ge-ისთვის XML ფორმატის გენერაცია.
    """
    period = payroll.get("period", datetime.now().strftime("%Y-%m"))
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<Declaration Period="{period}" Type="PAYG">',
        '  <Employees>',
    ]

    for emp in payroll.get("employees", []):
        lines.append('    <Employee>')
        lines.append(f'      <Name>{emp["employee_name"]}</Name>')
        if emp.get("employee_id"):
            lines.append(f'      <PersonalID>{emp["employee_id"]}</PersonalID>')
        lines.append(f'      <GrossSalary>{emp["gross_salary"]:.2f}</GrossSalary>')
        lines.append(f'      <PAYG>{emp["payg_2pct"]:.2f}</PAYG>')
        lines.append(f'      <PIT>{emp["pit_20pct"]:.2f}</PIT>')
        lines.append(f'      <NetSalary>{emp["net_salary"]:.2f}</NetSalary>')
        lines.append('    </Employee>')

    totals = payroll.get("totals", {})
    lines.extend([
        '  </Employees>',
        '  <Totals>',
        f'    <TotalGross>{totals.get("gross", 0):.2f}</TotalGross>',
        f'    <TotalPAYG>{totals.get("payg", 0):.2f}</TotalPAYG>',
        f'    <TotalPIT>{totals.get("pit", 0):.2f}</TotalPIT>',
        f'    <TotalNet>{totals.get("net", 0):.2f}</TotalNet>',
        '  </Totals>',
        '</Declaration>',
    ])

    return "\n".join(lines)