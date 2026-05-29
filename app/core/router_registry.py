"""app/core/router_registry.py

Centralises all app.include_router() calls so main.py stays readable.
Import order matches original main.py to preserve router precedence.
"""
from fastapi import FastAPI


def register_routers(app: FastAPI) -> None:
    """Include every router into *app*. Called once at startup from main.py."""

    from app.api import routes_health
    from app.api import routes_version
    from app.api import routes_debug
    from app.api import routes_bank_csv
    from app.api import routes_bank_process
    from app.api import routes_approval
    from app.api import routes_posting
    from app.api import routes_system
    from app.api import routes_coa
    from app.api import routes_learning
    from app.api import routes_transaction_ai
    from app.api import routes_export_journal
    from app.api import routes_audit_log
    from app.api import routes_invoice
    from app.api import routes_erp_memory
    from app.api import routes_erp_import
    from app.api import routes_erp_connectors
    from app.api import routes_auth
    from app.api import routes_balance_ge
    from app.api import routes_1c
    from app.api import routes_notifications
    from app.api import routes_tax
    from app.api import routes_search
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
    from app.api.routes_financial_statements import router as financial_statements_router
    from app.api.routes_financial_statements import financial_statements_alias_router
    from app.api.routes_fixed_assets import router as fixed_assets_router
    from app.api import routes_security
    from app.api import routes_webhooks_v2
    from app.api import routes_api_docs
    from app.api import routes_dashboard
    from app.api import routes_docs
    from app.api import routes_transaction_memory
    from app.api import routes_qa
    from app.api import routes_tenants
    from app.api import routes_export_v2
    from app.api.routes_patterns import router as patterns_router
    from app.api.routes_expense_articles import router as expense_articles_router
    from app.api.routes_learning_explain import router as learning_explain_router
    from app.api import routes_ocr
    from app.api.routes_documents import router as routes_documents_router
    from app.api.routes_outgoing import router as routes_outgoing_router
    from app.api import routes_notifications_ws
    from app.api import routes_collaboration
    from app.api import routes_dashboard_live
    from app.api import routes_client_portal
    from app.api.routes_dashboard_insights import router as dashboard_insights_router
    from app.api import routes_payroll
    from app.api import routes_email_invoice
    from app.api.routes_email_collector import router as routes_email_collector
    from app.api.routes_balance_credentials import router as routes_balance_credentials
    from app.api import routes_bank_sync
    from app.api import routes_ai_chat
    from app.api.routes_claude_chat import router as routes_claude_chat
    from app.api.routes_ai_recommend import router as routes_ai_recommend
    from app.api import routes_audit
    from app.api.routes_decision_engine import router as decision_engine_router
    from app.api.routes_inventory import router as inventory_router
    from app.api.routes_audit_trail import router as audit_trail_router
    from app.api.routes_2fa import router as totp_router
    from app.api.routes_fx import router as fx_router
    from app.api.routes_webhooks import router as webhooks_router
    from app.api.routes_oauth import router as oauth_router
    from app.api.routes_employee_portal import router as employee_portal_router
    from app.api.routes_employee_portal import pension_router as pension_transfer_router
    from app.api.routes_integrations import router as integrations_router
    from app.api.routes_aging import router as aging_router
    from app.api.routes_recurring import router as recurring_router
    from app.api.routes_period_lock import router as period_lock_router
    from app.api.routes_closing import router as closing_router
    from app.api.routes_cost_center import router as cost_center_router
    from app.api.routes_worker import router as worker_router
    from app.api.routes_email_inbound import router as email_inbound_router
    from app.api.routes_trade import router as trade_router
    from app.api.routes_credential_vault import router as credential_vault_router

    # ── new-style routers (registered first to match original order) ────────
    app.include_router(routes_health.router)
    app.include_router(routes_version.router)
    app.include_router(inventory_router)
    app.include_router(audit_trail_router)
    app.include_router(totp_router)
    app.include_router(fx_router)
    app.include_router(webhooks_router)
    app.include_router(oauth_router)
    app.include_router(employee_portal_router)
    app.include_router(pension_transfer_router)
    app.include_router(integrations_router)
    app.include_router(aging_router)
    app.include_router(recurring_router)
    app.include_router(period_lock_router)
    app.include_router(worker_router)
    app.include_router(email_inbound_router)
    app.include_router(closing_router)
    app.include_router(cost_center_router)
    app.include_router(trade_router)
    app.include_router(credential_vault_router)

    # ── original routers ────────────────────────────────────────────────────
    app.include_router(routes_debug.router)
    app.include_router(routes_bank_csv.router)
    app.include_router(routes_bank_process.router)
    app.include_router(routes_approval.router)
    app.include_router(routes_posting.router)
    app.include_router(routes_system.router)
    app.include_router(routes_coa.router)
    app.include_router(routes_learning.router)
    app.include_router(routes_transaction_ai.router)
    app.include_router(routes_export_journal.router)
    app.include_router(routes_audit_log.router)
    app.include_router(routes_audit.router)
    app.include_router(patterns_router)
    app.include_router(routes_invoice.router)
    app.include_router(expense_articles_router)
    app.include_router(routes_erp_memory.router)
    app.include_router(routes_erp_import.router)
    app.include_router(routes_erp_connectors.router)
    app.include_router(routes_auth.router)
    app.include_router(routes_balance_ge.router)
    app.include_router(routes_1c.router)
    app.include_router(routes_notifications.router)
    app.include_router(routes_tax.router)
    app.include_router(routes_search.router)
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
    app.include_router(financial_statements_router)
    app.include_router(financial_statements_alias_router)
    app.include_router(routes_reports.router)
    app.include_router(routes_reports.journal_router)
    app.include_router(fixed_assets_router)
    app.include_router(routes_security.router)
    app.include_router(routes_webhooks_v2.router)
    app.include_router(routes_api_docs.router)
    app.include_router(routes_dashboard.router)
    app.include_router(routes_docs.router)
    app.include_router(routes_transaction_memory.router)
    app.include_router(learning_explain_router)
    app.include_router(routes_qa.router)
    app.include_router(routes_tenants.router)
    app.include_router(routes_export_v2.router)
    app.include_router(routes_ocr.router)
    app.include_router(routes_documents_router)
    app.include_router(routes_outgoing_router)
    app.include_router(routes_notifications_ws.router)
    app.include_router(routes_collaboration.router)
    app.include_router(routes_dashboard_live.router)
    app.include_router(dashboard_insights_router)
    app.include_router(routes_client_portal.router)
    app.include_router(routes_payroll.router)
    app.include_router(routes_email_invoice.router)
    app.include_router(routes_email_collector)
    app.include_router(routes_balance_credentials)
    app.include_router(routes_bank_sync.router)
    app.include_router(routes_ai_chat.router)
    app.include_router(routes_ai_recommend)
    app.include_router(routes_claude_chat)
    app.include_router(decision_engine_router)

    from app.api.routes_opening_balances import router as opening_balances_router
    app.include_router(opening_balances_router)
