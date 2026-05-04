from typing import Any, Dict, Optional
from app.api.connectors.balance_connector import BalanceConnector
from app.api.connectors.onec_connector import OneCConnector
from app.api.services.erp_import_service import import_erp_history


def get_connector(source_system: str, mode: str = "demo"):
    if source_system == "balance":
        return BalanceConnector()
    elif source_system == "1c":
        return OneCConnector()
    else:
        class _Demo:
            def history(self, **kwargs): return []
        return _Demo()


def import_posted_history_from_connector(
    source_system: str,
    mode: str = "demo",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    connector = get_connector(source_system=source_system, mode=mode)
    items = connector.history(tenant_id="default", limit=limit)
    result = import_erp_history(items=items, default_source_system=source_system)
    return {
        "ok": True,
        "source_system": source_system,
        "mode": mode,
        "processed": result.get("processed", 0),
        "inserted_or_updated": result.get("inserted_or_updated", 0),
        "errors": result.get("errors", []),
    }
