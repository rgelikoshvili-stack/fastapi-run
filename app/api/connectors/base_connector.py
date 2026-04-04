"""app/api/connectors/base_connector.py"""
from abc import ABC, abstractmethod

class BaseConnector(ABC):
    @abstractmethod
    def status(self) -> dict: pass

    @abstractmethod
    def validate_config(self) -> bool: pass

    @abstractmethod
    def preview(self, draft: dict) -> dict: pass

    @abstractmethod
    def post(self, draft: dict) -> dict: pass

    @abstractmethod
    def history(self, tenant_id: str, limit: int = 50) -> list: pass

    def _safe_post(self, draft):
        check = self.preview(draft)
        if not check.get("valid"):
            return {"success": False, "erp_id": None,
                    "error": "; ".join(check.get("errors", []))}
        return self.post(draft)

    def _build_error(self, message, raw=None):
        return {"success": False, "erp_id": None, "error": message, "raw": raw}

    def _build_success(self, erp_id):
        return {"success": True, "erp_id": erp_id, "error": None}
