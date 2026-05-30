"""app/api/connectors/fina_connector.py — FINA Consulting ERP connector (Phase 7).

FINA is a Georgian accounting service platform.

Configuration (env vars):
  FINA_ENDPOINT  — base URL
  FINA_API_KEY   — API key
  FINA_ORG_ID    — organisation identifier
"""
import logging
import os
from datetime import datetime, timezone

import requests

from app.api.connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)


class FinaConnector(BaseConnector):
    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id
        self.endpoint  = os.environ.get("FINA_ENDPOINT", "").strip()
        self.api_key   = os.environ.get("FINA_API_KEY",  "").strip()
        self.org_id    = os.environ.get("FINA_ORG_ID",   "").strip()
        self.mode      = "live" if self.endpoint else "demo"

    def _headers(self) -> dict:
        return {
            "Accept":        "application/json",
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "X-Org-ID":      self.org_id,
        }

    def status(self) -> dict:
        if self.mode == "demo":
            return {"connected": True, "mode": "demo",
                    "message": "FINA demo mode — set FINA_ENDPOINT to go live",
                    "tenant_id": self.tenant_id}
        try:
            r = requests.get(f"{self.endpoint}/ping",
                             headers=self._headers(), timeout=10)
            ok = r.status_code == 200
            return {"connected": ok, "mode": "live",
                    "message": "OK" if ok else r.text[:100],
                    "tenant_id": self.tenant_id}
        except Exception as exc:
            return {"connected": False, "mode": "live",
                    "message": str(exc)[:100], "tenant_id": self.tenant_id}

    def validate_config(self) -> bool:
        if self.mode == "demo":
            return True
        return bool(self.endpoint and self.api_key) and self.status().get("connected", False)

    def preview(self, draft: dict) -> dict:
        errors = []
        if not draft.get("lines"):
            errors.append("journal lines are missing")
        if float(draft.get("amount") or 0) <= 0:
            errors.append("amount must be > 0")
        if not draft.get("description"):
            errors.append("description is required")
        return {"valid": len(errors) == 0, "mode": self.mode,
                "errors": errors, "warnings": []}

    def post(self, draft: dict) -> dict:
        if self.mode == "demo":
            eid = f"FINA-DEMO-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            logger.info("[FINA] DEMO post: %s", eid)
            return self._build_success(eid)
        try:
            payload = {
                "transactionDate": draft.get("date") or datetime.now(timezone.utc).date().isoformat(),
                "description":     draft.get("description", ""),
                "amount":          float(draft.get("amount") or 0),
                "currencyCode":    draft.get("currency", "GEL"),
                "entries":         draft.get("lines", []),
                "externalRef":     str(draft.get("id", "")),
                "orgId":           self.org_id,
            }
            r = requests.post(f"{self.endpoint}/transactions",
                              json=payload, headers=self._headers(), timeout=30)
            if r.status_code in (200, 201):
                data = r.json()
                return self._build_success(str(data.get("transactionId", "")))
            return self._build_error(f"FINA error {r.status_code}: {r.text[:200]}", r.text)
        except Exception as exc:
            return self._build_error(str(exc))

    def history(self, tenant_id: str, limit: int = 50) -> list:
        if self.mode == "demo":
            return []
        try:
            r = requests.get(f"{self.endpoint}/transactions",
                             params={"limit": limit, "orgId": self.org_id},
                             headers=self._headers(), timeout=15)
            if r.status_code == 200:
                return r.json().get("items", [])
        except Exception as exc:
            logger.warning("[FINA] history failed: %s", exc)
        return []
