from typing import Any, Dict, List, Optional
from app.api.connectors.erp_connector_base import ERPConnectorBase


class BalanceDemoConnector(ERPConnectorBase):
    source_system = "balance"

    def fetch_posted_history(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        rows = [
            {
                "source_system": "balance",
                "external_entry_id": "BAL-1001",
                "external_doc_id": "DOC-5001",
                "doc_type": "bank_transaction",
                "description": "OpenAI subscription",
                "partner": "OpenAI",
                "amount": 800,
                "currency": "GEL",
                "debit_account": "7140",
                "credit_account": "1210",
                "account_code": "7140",
                "direction": "expense",
                "posting_date": "2026-03-21",
            },
            {
                "source_system": "balance",
                "external_entry_id": "BAL-1002",
                "external_doc_id": "DOC-5002",
                "doc_type": "bank_transaction",
                "description": "Bank transfer fee",
                "partner": "TBC Bank",
                "amount": 25,
                "currency": "GEL",
                "debit_account": "7150",
                "credit_account": "1210",
                "account_code": "7150",
                "direction": "expense",
                "posting_date": "2026-03-21",
            },
        ]
        return rows[:limit]