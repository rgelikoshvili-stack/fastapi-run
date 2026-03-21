from typing import Any, Dict, List, Optional
from app.api.connectors.erp_connector_base import ERPConnectorBase


class OrisRealConnector(ERPConnectorBase):
    source_system = "oris"

    def fetch_posted_history(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        # TODO: real ORIS integration
        return []