"""app/api/connectors/apex_connector.py — APEX ERP connector (Phase 7).

APEX is a Georgian enterprise resource planning system.

Configuration (env vars):
  APEX_ENDPOINT   — base URL
  APEX_CLIENT_ID  — OAuth2 client ID
  APEX_SECRET     — OAuth2 client secret
  APEX_DATABASE   — target database name
"""
import logging
import os
from datetime import datetime, timezone

import requests

from app.api.connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)


class ApexConnector(BaseConnector):
    def __init__(self, tenant_id: str = "default"):
        self.tenant_id  = tenant_id
        self.endpoint   = os.environ.get("APEX_ENDPOINT",   "").strip()
        self.client_id  = os.environ.get("APEX_CLIENT_ID",  "").strip()
        self.secret     = os.environ.get("APEX_SECRET",     "").strip()
        self.database   = os.environ.get("APEX_DATABASE",   "").strip()
        self.mode       = "live" if self.endpoint else "demo"
        self._token: str = ""

    def _headers(self) -> dict:
        return {
            "Accept":        "application/json",
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {self._token}",
            "X-Database":    self.database,
        }

    def _refresh_token(self) -> bool:
        """Obtain an OAuth2 access token."""
        try:
            r = requests.post(
                f"{self.endpoint}/oauth/token",
                json={"client_id": self.client_id, "client_secret": self.secret,
                      "grant_type": "client_credentials"},
                timeout=10,
            )
            if r.status_code == 200:
                self._token = r.json().get("access_token", "")
                return bool(self._token)
        except Exception as exc:
            logger.warning("[APEX] token refresh failed: %s", exc)
        return False

    def status(self) -> dict:
        if self.mode == "demo":
            return {"connected": True, "mode": "demo",
                    "message": "APEX demo mode — set APEX_ENDPOINT to go live",
                    "tenant_id": self.tenant_id}
        ok = self._refresh_token()
        return {"connected": ok, "mode": "live",
                "message": "Auth OK" if ok else "Token refresh failed",
                "tenant_id": self.tenant_id}

    def validate_config(self) -> bool:
        if self.mode == "demo":
            return True
        return bool(self.endpoint and self.client_id and self.secret) and \
               self.status().get("connected", False)

    def preview(self, draft: dict) -> dict:
        errors = []
        if not draft.get("lines"):
            errors.append("journal lines are missing")
        if float(draft.get("amount") or 0) <= 0:
            errors.append("amount must be > 0")
        return {"valid": len(errors) == 0, "mode": self.mode,
                "errors": errors, "warnings": []}

    def post(self, draft: dict) -> dict:
        if self.mode == "demo":
            eid = f"APEX-DEMO-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            logger.info("[APEX] DEMO post: %s", eid)
            return self._build_success(eid)
        if not self._token:
            self._refresh_token()
        try:
            payload = {
                "DocumentDate": draft.get("date") or datetime.now(timezone.utc).date().isoformat(),
                "Description":  draft.get("description", ""),
                "Amount":       float(draft.get("amount") or 0),
                "Currency":     draft.get("currency", "GEL"),
                "Lines":        draft.get("lines", []),
                "Reference":    str(draft.get("id", "")),
                "Database":     self.database,
            }
            r = requests.post(f"{self.endpoint}/accounting/journals",
                              json=payload, headers=self._headers(), timeout=30)
            if r.status_code in (200, 201):
                data = r.json()
                return self._build_success(str(data.get("DocumentNo", "")))
            return self._build_error(f"APEX error {r.status_code}: {r.text[:200]}", r.text)
        except Exception as exc:
            return self._build_error(str(exc))

    def history(self, tenant_id: str, limit: int = 50) -> list:
        if self.mode == "demo":
            return []
        if not self._token:
            self._refresh_token()
        try:
            r = requests.get(f"{self.endpoint}/accounting/journals",
                             params={"limit": limit, "database": self.database},
                             headers=self._headers(), timeout=15)
            if r.status_code == 200:
                return r.json().get("Documents", [])
        except Exception as exc:
            logger.warning("[APEX] history failed: %s", exc)
        return []
