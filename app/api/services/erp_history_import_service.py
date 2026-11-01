"""History previews must never load global ERP credentials or train on demo data.

Live history needs a reviewed tenant-bound adapter and source-row contract.
The old Balance history projection drops external identity/account fields;
1C uses global credentials and ORIS has no history adapter. None is authorized
as a live learning importer by this generic route.
"""
from typing import Any, Dict, Optional

from app.api.db import require_current_tenant_id


class _DemoHistory:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def history(self, tenant_id: str, limit: int = 100):
        if require_current_tenant_id(tenant_id) != self.tenant_id:
            raise ValueError("ERP_HISTORY_TENANT_MISMATCH")
        return []


def get_connector(source_system: str, mode: str = "demo", tenant_id: Optional[str] = None):
    tenant_id = require_current_tenant_id(tenant_id)
    if source_system not in {"balance", "oris", "1c"}:
        raise ValueError("ERP_HISTORY_SOURCE_UNSUPPORTED")
    if mode not in {"demo", "real"}:
        raise ValueError("ERP_HISTORY_MODE_UNSUPPORTED")
    if mode != "demo":
        raise ValueError("ERP_HISTORY_LIVE_ADAPTER_UNVERIFIED")
    return _DemoHistory(tenant_id)


def import_posted_history_from_connector(
    source_system: str,
    mode: str = "demo",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 100,
    tenant_id: Optional[str] = None,
) -> Dict[str, Any]:
    tenant_id = require_current_tenant_id(tenant_id)
    connector = get_connector(source_system=source_system, mode=mode, tenant_id=tenant_id)
    # Demo is an explicitly empty preview, not persisted learning evidence.
    connector.history(tenant_id=tenant_id, limit=limit)
    return {
        "ok": True,
        "tenant_id": tenant_id,
        "source_system": source_system,
        "mode": "demo",
        "simulated": True,
        "authoritative": False,
        "purpose": "erp_learning_memory_preview",
        "processed": 0,
        "inserted_or_updated": 0,
        "errors": [],
    }
