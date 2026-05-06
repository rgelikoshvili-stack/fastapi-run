"""app/api/connectors/oris_connector.py — ORIS ERP connector (stub)."""
from .base_connector import BaseConnector


class OrisConnector(BaseConnector):
    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id

    def validate_config(self) -> bool:
        return False

    def status(self) -> dict:
        return {
            "connected": False,
            "mode": "demo",
            "message": "ORIS connector not implemented yet",
            "tenant_id": self.tenant_id,
        }

    def preview(self, draft: dict) -> dict:
        lines = draft.get("lines", [])
        if not lines:
            return {"valid": False, "errors": ["lines აკლია"], "warnings": []}
        return {"valid": True, "errors": [], "warnings": []}

    def post(self, draft: dict) -> dict:
        return {
            "success": False,
            "erp_id": None,
            "error": "ORIS connector not implemented yet",
        }

    def history(self, tenant_id: str, limit: int = 50) -> list:
        return []
