from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List
from app.api.response_utils import ok_response, error_response
from app.api.db import get_db
import psycopg2.extras

router = APIRouter(prefix="/tax", tags=["tax"])

# საქართველოს საგადასახადო კოდექსი 2026
GEO_TAX_RATES = {
    "vat": 18.0,              # დღგ
    "income_tax": 20.0,        # საშემოსავლო გადასახადი
    "corporate_tax": 15.0,     # მოგების გადასახადი (განაწილებული)
    "pension": 4.0,            # საპენსიო (თანამშრომელი)
    "pension_employer": 2.0,   # საპენსიო (დამსაქმებელი)
    "property_tax": 1.0,       # ქონების გადასახადი (max)
    "dividend_tax": 5.0,       # დივიდენდის გადასახადი
    "turnover_tax": 1.0,       # ბრუნვის გადასახადი (micro)
}

class VATRequest(BaseModel):
    amount: float
    direction: Optional[str] = "add"  # add (+ VAT) or extract (from total)
    vat_rate: Optional[float] = 18.0

class SalaryRequest(BaseModel):
    gross_salary: float
    include_pension: Optional[bool] = True

class CorporateRequest(BaseModel):
    profit: float
    distributed: Optional[bool] = True  # განაწილებული

class InvoiceTaxRequest(BaseModel):
    subtotal: float
    vat_rate: Optional[float] = 18.0
    include_withholding: Optional[bool] = False
    withholding_rate: Optional[float] = 0.0

class AnnualTaxRequest(BaseModel):
    annual_revenue: float
    annual_expenses: float
    employee_count: Optional[int] = 0
    avg_salary: Optional[float] = 0

@router.get("/rates")
def get_tax_rates():
    return ok_response("Georgian tax rates 2026", GEO_TAX_RATES)

@router.post("/vat")
def calculate_vat(req: VATRequest):
    if req.direction == "add":
        vat_amount = round(req.amount * req.vat_rate / 100, 2)
        total = round(req.amount + vat_amount, 2)
        return ok_response("VAT calculated", {
            "subtotal": req.amount,
            "vat_rate": req.vat_rate,
            "vat_amount": vat_amount,
            "total_with_vat": total,
            "direction": "added"
        })
    else:
        subtotal = round(req.amount / (1 + req.vat_rate / 100), 2)
        vat_amount = round(req.amount - subtotal, 2)
        return ok_response("VAT extracted", {
            "total": req.amount,
            "vat_rate": req.vat_rate,
            "vat_amount": vat_amount,
            "subtotal_excl_vat": subtotal,
            "direction": "extracted"
        })

@router.post("/salary")
def calculate_salary(req: SalaryRequest):
    income_tax = round(req.gross_salary * GEO_TAX_RATES["income_tax"] / 100, 2)
    pension_employee = round(req.gross_salary * GEO_TAX_RATES["pension"] / 100, 2) if req.include_pension else 0
    pension_employer = round(req.gross_salary * GEO_TAX_RATES["pension_employer"] / 100, 2) if req.include_pension else 0
    net_salary = round(req.gross_salary - income_tax - pension_employee, 2)
    total_employer_cost = round(req.gross_salary + pension_employer, 2)

    return ok_response("Salary tax breakdown", {
        "gross_salary": req.gross_salary,
        "income_tax_20pct": income_tax,
        "pension_employee_4pct": pension_employee,
        "pension_employer_2pct": pension_employer,
        "net_salary": net_salary,
        "total_employer_cost": total_employer_cost,
        "effective_tax_rate": round((income_tax + pension_employee) / req.gross_salary * 100, 1)
    })

@router.post("/corporate")
def calculate_corporate(req: CorporateRequest):
    if req.distributed:
        tax = round(req.profit * GEO_TAX_RATES["corporate_tax"] / 100, 2)
        net = round(req.profit - tax, 2)
        return ok_response("Corporate tax (distributed profit)", {
            "profit": req.profit,
            "tax_rate": "15%",
            "corporate_tax": tax,
            "net_after_tax": net,
            "note": "საქართველო: გადასახადი მხოლოდ განაწილებულ მოგებაზე"
        })
    else:
        return ok_response("Corporate tax (retained profit)", {
            "profit": req.profit,
            "tax_rate": "0%",
            "corporate_tax": 0,
            "net_after_tax": req.profit,
            "note": "განაწილებული არ არის — გადასახადი 0"
        })

@router.post("/invoice")
def calculate_invoice_tax(req: InvoiceTaxRequest):
    vat = round(req.subtotal * req.vat_rate / 100, 2)
    total = round(req.subtotal + vat, 2)
    withholding = round(total * req.withholding_rate / 100, 2) if req.include_withholding else 0
    payable = round(total - withholding, 2)
    return ok_response("Invoice tax", {
        "subtotal": req.subtotal,
        "vat_amount": vat,
        "total_with_vat": total,
        "withholding_tax": withholding,
        "amount_payable": payable,
    })

@router.post("/annual-summary")
def annual_tax_summary(req: AnnualTaxRequest):
    profit = req.annual_revenue - req.annual_expenses
    corporate_tax = round(profit * GEO_TAX_RATES["corporate_tax"] / 100, 2) if profit > 0 else 0
    vat_payable = round(req.annual_revenue * GEO_TAX_RATES["vat"] / 100, 2)
    salary_total = req.employee_count * req.avg_salary * 12
    income_tax_total = round(salary_total * GEO_TAX_RATES["income_tax"] / 100, 2)
    pension_total = round(salary_total * (GEO_TAX_RATES["pension"] + GEO_TAX_RATES["pension_employer"]) / 100, 2)
    total_tax_burden = round(corporate_tax + income_tax_total + pension_total, 2)

    return ok_response("Annual tax summary", {
        "revenue": req.annual_revenue,
        "expenses": req.annual_expenses,
        "profit": round(profit, 2),
        "corporate_tax_15pct": corporate_tax,
        "vat_payable_18pct": vat_payable,
        "income_tax_20pct": income_tax_total,
        "pension_6pct": pension_total,
        "total_tax_burden": total_tax_burden,
        "effective_rate": round(total_tax_burden / req.annual_revenue * 100, 1) if req.annual_revenue else 0
    })

@router.get("/from-journal/{year}")
def tax_from_journal(year: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT COALESCE(SUM(amount),0) as total FROM journal_drafts WHERE account_code LIKE '6%%' AND date LIKE %s", (f"{year}%",))
        r = cur.fetchone(); revenue = float(r["total"]) if r else 0.0

        cur.execute("SELECT COALESCE(SUM(amount),0) as total FROM journal_drafts WHERE account_code LIKE '7%%' AND date LIKE %s", (f"{year}%",))
        r = cur.fetchone(); expenses = float(r["total"]) if r else 0.0

        cur.execute("SELECT COALESCE(SUM(amount),0) as total FROM journal_drafts WHERE account_code='3100' AND date LIKE %s", (f"{year}%",))
        r = cur.fetchone(); tax_paid = float(r["total"]) if r else 0.0
    finally:
        cur.close(); conn.close()

    profit = round(revenue - expenses, 2)
    estimated_vat = round(revenue * 0.18, 2)
    estimated_corporate = round(profit * 0.15, 2) if profit > 0 else 0

    return ok_response("Tax from journal", {
        "year": year,
        "revenue": revenue,
        "expenses": expenses,
        "profit": profit,
        "tax_already_posted": tax_paid,
        "estimated_vat_18pct": estimated_vat,
        "estimated_corporate_tax_15pct": estimated_corporate,
        "total_estimated": round(estimated_vat + estimated_corporate, 2)
    })
