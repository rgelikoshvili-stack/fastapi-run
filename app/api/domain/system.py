"""Domain: System — auth, RBAC, health, audit, notifications, ERP, security, tenants."""
from fastapi import APIRouter
from app.api import (
    routes_auth,
    routes_rbac,
    routes_health,
    routes_audit,
    routes_audit_engine,
    routes_audit_log,
    routes_notifications,
    routes_notifications_ws,
    routes_erp_connectors,
    routes_erp_import,
    routes_erp_memory,
    routes_balance_credentials,
    routes_balance_ge,
    routes_currency,
    routes_tenants,
    routes_security,
    routes_system,
    routes_dashboard,
    routes_dashboard_insights,
    routes_dashboard_live,
)

router = APIRouter(tags=["system"])
router.include_router(routes_auth.router)
router.include_router(routes_rbac.router)
router.include_router(routes_health.router)
router.include_router(routes_audit.router)
router.include_router(routes_audit_engine.router)
router.include_router(routes_audit_log.router)
router.include_router(routes_notifications.router)
router.include_router(routes_notifications_ws.router)
router.include_router(routes_erp_connectors.router)
router.include_router(routes_erp_import.router)
router.include_router(routes_erp_memory.router)
router.include_router(routes_balance_credentials.router)
router.include_router(routes_balance_ge.router)
router.include_router(routes_currency.router)
router.include_router(routes_tenants.router)
router.include_router(routes_security.router)
router.include_router(routes_system.router)
router.include_router(routes_dashboard.router)
router.include_router(routes_dashboard_insights.router)
router.include_router(routes_dashboard_live.router)
