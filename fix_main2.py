with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

imports = """
from app.api import routes_audit_engine
from app.api import routes_ai_journal
from app.api import routes_bank_accounts
from app.api import routes_budget
from app.api import routes_contracts
from app.api import routes_crm
from app.api import routes_currency
from app.api import routes_expenses
from app.api import routes_invoices
from app.api import routes_pdf_report
from app.api import routes_rbac
from app.api import routes_reconciliation
from app.api import routes_reports
from app.api import routes_security
from app.api import routes_webhooks_v2
from app.api import routes_api_docs
from app.api import routes_dashboard
from app.api import routes_docs"""

routers = """
app.include_router(routes_audit_engine.router)
app.include_router(routes_ai_journal.router)
app.include_router(routes_bank_accounts.router)
app.include_router(routes_budget.router)
app.include_router(routes_contracts.router)
app.include_router(routes_crm.router)
app.include_router(routes_currency.router)
app.include_router(routes_expenses.router)
app.include_router(routes_invoices.router)
app.include_router(routes_pdf_report.router)
app.include_router(routes_rbac.router)
app.include_router(routes_reconciliation.router)
app.include_router(routes_reports.router)
app.include_router(routes_security.router)
app.include_router(routes_webhooks_v2.router)
app.include_router(routes_api_docs.router)
app.include_router(routes_dashboard.router)
app.include_router(routes_docs.router)"""

content = content.replace("from app.api import routes_search", "from app.api import routes_search" + imports, 1)
content = content.replace("app.include_router(routes_search.router)", "app.include_router(routes_search.router)" + routers, 1)

with open("main.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Done!")
