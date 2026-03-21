from typing import Any, Dict, List, Optional
from app.api.connectors.erp_connector_base import ERPConnectorBase


class OneCDemoConnector(ERPConnectorBase):
    source_system = "1c"

    def fetch_posted_history(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        rows = [
            {
                "source_system": "1c",
                "external_entry_id": "1C-3001",
                "external_doc_id": "1C-DOC-9001",
                "doc_type": "bank_transaction",
                "description": "AWS monthly hosting",
                "partner": "Amazon AWS",
                "amount": 950,
                "currency": "GEL",
                "debit_account": "7140",
                "credit_account": "1210",
                "account_code": "7140",
                "direction": "expense",
                "posting_date": "2026-03-21",
            },
            {
                "source_system": "1c",
                "external_entry_id": "1C-3002",
                "external_doc_id": "1C-DOC-9002",
                "doc_type": "bank_transaction",
                "description": "Courier service",
                "partner": "DHL",
                "amount": 40,
                "currency": "GEL",
                "debit_account": "7160",
                "credit_account": "1210",
                "account_code": "7160",
                "direction": "expense",
                "posting_date": "2026-03-21",
            },
        ]
        return rows[:limit]