"""Legacy invoice parse route shim.

Keep this module import-compatible for older domain routers while the
implementation lives in app.api.routes_invoices.
"""
from app.api.routes_invoices import invoice_legacy_router as router
