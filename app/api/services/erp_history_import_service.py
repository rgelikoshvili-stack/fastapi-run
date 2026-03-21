from typing import Any, Dict, Optional

from app.api.connectors.connector_factory import get_connector
from app.api.services.erp_import_service import import_erp_history


def import_posted_history_from_connector(
    source_system: str,
    mode: str = "demo",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    connector = get_connector(source_system=source_system, mode=mode)

    items = connector.fetch_posted_history(
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )

    result = import_erp_history(
        items=items,
        default_source_system=source_system,
    )

    return {
        "ok": True,
        "source_system": source_system,
        "mode": mode,
        "processed": result.get("processed", 0),
        "inserted_or_updated": result.get("inserted_or_updated", 0),
        "errors": result.get("errors", []),
    }