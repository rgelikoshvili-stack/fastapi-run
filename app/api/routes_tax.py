"""
Bridge Hub — Tax Routes V2
→ app/api/routes_tax.py
+ accounting_rules integration (GEL format, VAT posting, Dividend 2-step)
"""
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional, List
from app.api.response_utils import ok_response, error_response
from app.api.db import get_conn, _q
 
# ── Accounting Rules ──────────────────────────────────────────────────────────
try:
    from app.api.services.accounting_rules import (
        build_vat_posting, build_dividend_posting, format_gel
    )
    ACCT_RULES_LOADED = True
except ImportError:
    ACCT_RULES_LOADED = False
    def format_gel(a: float) -> str:
        return f"{a:,.2f}₾"
 
router = APIRouter(prefix="/tax", tags=["tax"])
 
# საქართველოს საგადასახადო კოდექსი 2026
GEO_TAX_RATES = {
    "vat": 18.0,
    "income_tax": 20.0,
    "corporate_tax": 15.0,
    "pension": 4.0,
    "pension_employer": 2.0,
    "property_tax": 1.0,
    "dividend_tax": 5.0,
    "turnover_tax": 1.0,
}
 
 
class VATRequest(BaseModel):
    amount: float
    direction: Optional[str] = "add"           # "add" | "extract"
    vat_rate: Optional[float] = 18.0
    payment_status: Optional[str] = "paid"      # "paid" | "unpaid" — NEW
 
 
class VATPostingRequest(BaseModel):             # NEW — structured posting
    gross_amount: float
    payment_status: Optional[str] = "paid"      # "paid" | "unpaid"
    vat_rate: Optional[float] = 0.18
 
 
class SalaryRequest(BaseModel):
    gross_salary: float
    include_pension: Optional[bool] = True
 
 
class CorporateRequest(BaseModel):
    profit: float
    distributed: Optional[bool] = True
 
 
class DividendRequest(BaseModel):               # NEW — 2-step posting
    gross_amount: float
    cit_rate: Optional[float] = 0.15
 
 
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
 
 
# ── ENDPOINTS ─────────────────────────────────────────────────────────────────
 
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
            "subtotal_formatted": format_gel(req.amount),
            "vat_rate": req.vat_rate,
            "vat_amount": vat_amount,
            "vat_amount_formatted": format_gel(vat_amount),
            "total_with_vat": total,
            "total_formatted": format_gel(total),
            "direction": "added",
            "payment_status": req.payment_status,
        })
    else:
        subtotal = round(req.amount / (1 + req.vat_rate / 100), 2)
        vat_amount = round(req.amount - subtotal, 2)
        return ok_response("VAT extracted", {
            "total": req.amount,
            "total_formatted": format_gel(req.amount),
            "vat_rate": req.vat_rate,
            "vat_amount": vat_amount,
            "vat_amount_formatted": format_gel(vat_amount),
            "subtotal_excl_vat": subtotal,
            "subtotal_formatted": format_gel(subtotal),
            "direction": "extracted",
            "payment_status": req.payment_status,
        })
 
 
@router.post("/vat-posting")                    # NEW — structured Balance.ge payload
def vat_posting(req: VATPostingRequest):
    """
    VAT posting rule:
    - paid   → Dr 1120 Bank | Cr 6110 | Cr 3310
    - unpaid → Dr 1410 Receivable | Cr 6110 | Cr 3310
    """
    if not ACCT_RULES_LOADED:
        return error_response("accounting_rules module not found", 503)
    result = build_vat_posting(req.gross_amount, req.vat_rate, req.payment_status)
    return ok_response("VAT posting", result)
 
 
@router.post("/dividend")                       # NEW — 2-step dividend posting
def dividend_posting(req: DividendRequest):
    """
    Dividend 2-step posting rule:
    Step 1: Dr 4210 Retained Earnings | Cr 3320 Dividends Payable
    Step 2: Dr 3320 | Cr 3340 CIT (15%) | Cr 1120 Bank
    """
    if not ACCT_RULES_LOADED:
        # fallback — simple calculation
        cit = round(req.gross_amount * req.cit_rate, 2)
        net = round(req.gross_amount - cit, 2)
        return ok_response("Dividend (simple)", {
            "gross": req.gross_amount,
            "gross_formatted": format_gel(req.gross_amount),
            "cit": cit,
            "cit_formatted": format_gel(cit),
            "net_to_shareholder": net,
            "net_formatted": format_gel(net),
        })
    result = build_dividend_posting(req.gross_amount, req.cit_rate)
    return ok_response("Dividend 2-step posting", result)
 
 
@router.post("/salary")
def calculate_salary(req: SalaryRequest):
    income_tax = round(req.gross_salary * GEO_TAX_RATES["income_tax"] / 100, 2)
    pension_employee = round(req.gross_salary * GEO_TAX_RATES["pension"] / 100, 2) if req.include_pension else 0
    pension_employer = round(req.gross_salary * GEO_TAX_RATES["pension_employer"] / 100, 2) if req.include_pension else 0
    net_salary = round(req.gross_salary - income_tax - pension_employee, 2)
    total_employer_cost = round(req.gross_salary + pension_employer, 2)
 
    return ok_response("Salary tax breakdown", {
        "gross_salary": req.gross_salary,
        "gross_formatted": format_gel(req.gross_salary),
        "income_tax_20pct": income_tax,
        "income_tax_formatted": format_gel(income_tax),
        "pension_employee_4pct": pension_employee,
        "pension_employee_formatted": format_gel(pension_employee),
        "pension_employer_2pct": pension_employer,
        "net_salary": net_salary,
        "net_salary_formatted": format_gel(net_salary),
        "total_employer_cost": total_employer_cost,
        "total_employer_formatted": format_gel(total_employer_cost),
        "effective_tax_rate": round((income_tax + pension_employee) / req.gross_salary * 100, 1),
    })
 
 
@router.post("/corporate")
def calculate_corporate(req: CorporateRequest):
    if req.distributed:
        tax = round(req.profit * GEO_TAX_RATES["corporate_tax"] / 100, 2)
        net = round(req.profit - tax, 2)
        return ok_response("Corporate tax (distributed profit)", {
            "profit": req.profit,
            "profit_formatted": format_gel(req.profit),
            "tax_rate": "15%",
            "corporate_tax": tax,
            "corporate_tax_formatted": format_gel(tax),
            "net_after_tax": net,
            "net_formatted": format_gel(net),
            "note": "საქართველო: გადასახადი მხოლოდ განაწილებულ მოგებაზე",
        })
    else:
        return ok_response("Corporate tax (retained profit)", {
            "profit": req.profit,
            "profit_formatted": format_gel(req.profit),
            "tax_rate": "0%",
            "corporate_tax": 0,
            "net_after_tax": req.profit,
            "note": "განაწილებული არ არის — გადასახადი 0",
        })
 
 
@router.post("/invoice")
def calculate_invoice_tax(req: InvoiceTaxRequest):
    vat = round(req.subtotal * req.vat_rate / 100, 2)
    total = round(req.subtotal + vat, 2)
    withholding = round(total * req.withholding_rate / 100, 2) if req.include_withholding else 0
    payable = round(total - withholding, 2)
    return ok_response("Invoice tax", {
        "subtotal": req.subtotal,
        "subtotal_formatted": format_gel(req.subtotal),
        "vat_amount": vat,
        "vat_formatted": format_gel(vat),
        "total_with_vat": total,
        "total_formatted": format_gel(total),
        "withholding_tax": withholding,
        "withholding_formatted": format_gel(withholding),
        "amount_payable": payable,
        "payable_formatted": format_gel(payable),
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
        "revenue_formatted": format_gel(req.annual_revenue),
        "expenses": req.annual_expenses,
        "expenses_formatted": format_gel(req.annual_expenses),
        "profit": round(profit, 2),
        "profit_formatted": format_gel(profit),
        "corporate_tax_15pct": corporate_tax,
        "corporate_tax_formatted": format_gel(corporate_tax),
        "vat_payable_18pct": vat_payable,
        "vat_formatted": format_gel(vat_payable),
        "income_tax_20pct": income_tax_total,
        "income_tax_formatted": format_gel(income_tax_total),
        "pension_6pct": pension_total,
        "pension_formatted": format_gel(pension_total),
        "total_tax_burden": total_tax_burden,
        "total_formatted": format_gel(total_tax_burden),
        "effective_rate": round(total_tax_burden / req.annual_revenue * 100, 1) if req.annual_revenue else 0,
    })
 
 
@router.get("/from-journal/{year}")
async def tax_from_journal(year: int, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    async with get_conn() as conn:
        r = await conn.fetchrow(_q(
            "SELECT COALESCE(SUM(amount),0) as total FROM journal_drafts WHERE account_code LIKE '6%%' AND date LIKE %s AND tenant_id = %s"),
            f"{year}%", tenant_id)
        revenue = float(r["total"]) if r else 0.0

        r = await conn.fetchrow(_q(
            "SELECT COALESCE(SUM(amount),0) as total FROM journal_drafts WHERE account_code LIKE '7%%' AND date LIKE %s AND tenant_id = %s"),
            f"{year}%", tenant_id)
        expenses = float(r["total"]) if r else 0.0

        r = await conn.fetchrow(_q(
            "SELECT COALESCE(SUM(amount),0) as total FROM journal_drafts WHERE account_code='3100' AND date LIKE %s AND tenant_id = %s"),
            f"{year}%", tenant_id)
        tax_paid = float(r["total"]) if r else 0.0
 
    profit = round(revenue - expenses, 2)
    estimated_vat = round(revenue * 0.18, 2)
    estimated_corporate = round(profit * 0.15, 2) if profit > 0 else 0
 
    return ok_response("Tax from journal", {
        "year": year,
        "revenue": revenue,
        "revenue_formatted": format_gel(revenue),
        "expenses": expenses,
        "expenses_formatted": format_gel(expenses),
        "profit": profit,
        "profit_formatted": format_gel(profit),
        "tax_already_posted": tax_paid,
        "tax_posted_formatted": format_gel(tax_paid),
        "estimated_vat_18pct": estimated_vat,
        "vat_formatted": format_gel(estimated_vat),
        "estimated_corporate_tax_15pct": estimated_corporate,
        "corporate_formatted": format_gel(estimated_corporate),
        "total_estimated": round(estimated_vat + estimated_corporate, 2),
        "total_formatted": format_gel(estimated_vat + estimated_corporate),
    })


# ── rs.ge Declaration helpers ─────────────────────────────────────────────────

class VatReturnRequest(BaseModel):
    inn: str
    year: int
    month: int
    taxable_sales: float = 0.0
    vat_collected: float = 0.0
    taxable_purchases: float = 0.0
    vat_paid: float = 0.0


class WithholdingRequest(BaseModel):
    inn: str
    year: int
    month: int
    payments: list = []


@router.post("/rs-ge/vat-return")
def rs_ge_vat_return(body: VatReturnRequest, request: Request):
    """Build RS Form 10 (VAT Return) payload ready for rs.ge portal upload."""
    from decimal import Decimal
    from app.integrations.rs_ge_api import build_vat_return, verify_taxpayer_inn
    v = verify_taxpayer_inn(body.inn)
    if not v["valid"]:
        return error_response("Invalid INN", "VALIDATION_ERROR", v["reason"])
    payload = build_vat_return(
        body.inn, body.year, body.month,
        Decimal(str(body.taxable_sales)), Decimal(str(body.vat_collected)),
        Decimal(str(body.taxable_purchases)), Decimal(str(body.vat_paid)),
    )
    return ok_response("VAT return payload (RS Form 10)", payload)


@router.post("/rs-ge/withholding")
def rs_ge_withholding(body: WithholdingRequest, request: Request):
    """Build RS Form 1 (Withholding Tax) payload."""
    from app.integrations.rs_ge_api import build_withholding_declaration, verify_taxpayer_inn
    v = verify_taxpayer_inn(body.inn)
    if not v["valid"]:
        return error_response("Invalid INN", "VALIDATION_ERROR", v["reason"])
    payload = build_withholding_declaration(body.inn, body.year, body.month, body.payments)
    return ok_response("Withholding declaration payload (RS Form 1)", payload)


@router.get("/rs-ge/verify-inn/{inn}")
def rs_ge_verify_inn(inn: str):
    """Validate Georgian taxpayer INN format."""
    from app.integrations.rs_ge_api import verify_taxpayer_inn
    return ok_response("INN validation", verify_taxpayer_inn(inn))