"""Domain: Documents — upload, OCR, invoices, outgoing, email, bank."""
from fastapi import APIRouter
from app.api import (
    routes_documents,
    routes_ocr,
    routes_invoice,
    routes_invoices,
    routes_outgoing,
    routes_email_invoice,
    routes_email_collector,
    routes_bank_csv,
    routes_bank_accounts,
    routes_bank_sync,
    routes_bank_process,
    routes_expenses,
    routes_expense_articles,
    routes_fixed_assets,
    routes_inventory,
)

router = APIRouter(tags=["documents"])
router.include_router(routes_documents.router)
router.include_router(routes_ocr.router)
router.include_router(routes_invoice.router)
router.include_router(routes_invoices.router)
router.include_router(routes_outgoing.router)
router.include_router(routes_email_invoice.router)
router.include_router(routes_email_collector.router)
router.include_router(routes_bank_csv.router)
router.include_router(routes_bank_accounts.router)
router.include_router(routes_bank_sync.router)
router.include_router(routes_bank_process.router)
router.include_router(routes_expenses.router)
router.include_router(routes_expense_articles.router)
router.include_router(routes_fixed_assets.router)
router.include_router(routes_inventory.router)
