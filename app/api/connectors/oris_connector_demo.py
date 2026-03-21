from typing import Any, Dict, List, Optional
from app.api.connectors.erp_connector_base import ERPConnectorBase


class OrisDemoConnector(ERPConnectorBase):
    source_system = "oris"

    def fetch_posted_history(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        rows = [
            {
                "source_system": "oris",
                "external_entry_id": "ORIS-2001",
                "external_doc_id": "ORIS-DOC-7001",
                "doc_type": "bank_transaction",
                "description": "Google Workspace subscription",
                "partner": "Google",
                "amount": 120,
                "currency": "GEL",
                "debit_account": "7140",
                "credit_account": "1210",
                "account_code": "7140",
                "direction": "expense",
                "posting_date": "2026-03-21",
            },
            {
                "source_system": "oris",
                "external_entry_id": "ORIS-2002",
                "external_doc_id": "ORIS-DOC-7002",
                "doc_type": "bank_transaction",
                "description": "Stationery purchase",
                "partner": "Gorgia",
                "amount": 65,
                "currency": "GEL",
                "debit_account": "7130",
                "credit_account": "1210",
                "account_code": "7130",
                "direction": "expense",
                "posting_date": "2026-03-21",
            },
        ]
        return rows[:limit]