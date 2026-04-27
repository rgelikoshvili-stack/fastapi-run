"""Domain: Finance — approval, posting, journal, statements, reports, budget, tax."""
from fastapi import APIRouter
from app.api import (
    routes_approval,
    routes_posting,
    routes_financial_statements,
    routes_reports,
    routes_budget,
    routes_tax,
    routes_export_journal,
    routes_coa,
    routes_reconciliation,
    routes_pdf_report,
    routes_payroll,
)

router = APIRouter(tags=["finance"])
router.include_router(routes_approval.router)
router.include_router(routes_posting.router)
router.include_router(routes_financial_statements.router)
router.include_router(routes_reports.router)
router.include_router(routes_budget.router)
router.include_router(routes_tax.router)
router.include_router(routes_export_journal.router)
router.include_router(routes_coa.router)
router.include_router(routes_reconciliation.router)
router.include_router(routes_pdf_report.router)
router.include_router(routes_payroll.router)
