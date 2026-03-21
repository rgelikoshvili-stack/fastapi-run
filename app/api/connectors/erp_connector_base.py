from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ERPConnectorBase(ABC):
    source_system: str = "unknown"

    @abstractmethod
    def fetch_posted_history(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def fetch_bank_transactions(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return []

    def fetch_invoices(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return []

    def fetch_chart_of_accounts(self) -> List[Dict[str, Any]]:
        return []

    def fetch_partners(self) -> List[Dict[str, Any]]:
        return []