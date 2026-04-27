"""Domain: CRM & Operations — customers, contracts, collaboration, search, export."""
from fastapi import APIRouter
from app.api import (
    routes_crm,
    routes_contracts,
    routes_collaboration,
    routes_search,
    routes_client_portal,
    routes_webhooks_v,
    routes_export_v,
)

router = APIRouter(tags=["crm"])
router.include_router(routes_crm.router)
router.include_router(routes_contracts.router)
router.include_router(routes_collaboration.router)
router.include_router(routes_search.router)
router.include_router(routes_client_portal.router)
router.include_router(routes_webhooks_v.router)
router.include_router(routes_export_v.router)
