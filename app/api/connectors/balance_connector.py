"""app/api/connectors/balance_connector.py"""
import os, logging, requests
from datetime import datetime, timezone
from app.api.connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)
BALANCE_API_BASE = os.environ.get("BALANCE_API_BASE", "https://api.balance.ge")

class BalanceConnector(BaseConnector):
    def __init__(self, tenant_id="default", company_id=None):
        self.tenant_id  = tenant_id
        self.company_id = company_id or os.environ.get("BALANCE_COMPANY_ID", "")
        self.api_key    = os.environ.get("BALANCE_API_KEY", "")
        self.mode       = "live" if self.api_key else "demo"

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-Tenant-ID": self.tenant_id}

    def status(self):
        if self.mode == "demo":
            return {"connected": True, "mode": "demo",
                    "message": "DEMO — BALANCE_API_KEY არ არის"}
        try:
            r = requests.get(f"{BALANCE_API_BASE}/health",
                             headers=self._headers(), timeout=10)
            return {"connected": r.status_code == 200, "mode": "live",
                    "message": "OK" if r.status_code == 200 else r.text[:100]}
        except Exception as e:
            return {"connected": False, "mode": "live", "message": str(e)}

    def validate_config(self):
        return True if self.mode == "demo" else self.status().get("connected", False)

    def preview(self, draft):
        errors = []
        if not draft.get("account_dr"): errors.append("account_dr აკლია")
        if not draft.get("account_cr"): errors.append("account_cr აკლია")
        if float(draft.get("amount", 0)) <= 0: errors.append("amount > 0 უნდა იყოს")
        return {"valid": len(errors) == 0, "mode": self.mode,
                "errors": errors, "warnings": []}

    def _safe_headers_log(self):
        h = self._headers()
        if "Authorization" in h:
            h["Authorization"] = "Bearer ***"
        return h

    def post(self, draft):
        if self.mode == "demo":
            fid = f"DEMO-{datetime.now().strftime('%H%M%S')}"
            logger.info("[Balance] DEMO post: %s", fid)
            return self._build_success(fid)
        try:
            payload = {
                "company_id": self.company_id,
                "date": draft.get("date") or datetime.now(timezone.utc).date().isoformat(),
                "entries": [{
                    "account_dr":  str(draft.get("account_dr")),
                    "account_cr":  str(draft.get("account_cr")),
                    "amount":      float(draft.get("amount", 0)),
                    "description": draft.get("description", ""),
                    "currency":    draft.get("currency", "GEL"),
                }]
            }
            url = f"{BALANCE_API_BASE}/api/v1/journal"
            logger.debug("[Balance] POST %s headers=%s payload=%s",
                         url, self._safe_headers_log(), payload)
            r = requests.post(url, headers=self._headers(), json=payload, timeout=15)
            logger.debug("[Balance] response status=%s body=%s",
                         r.status_code, r.text[:500])
            if r.status_code in (200, 201):
                erp_id = str(r.json().get("id", "unknown"))
                logger.info("[Balance] posted OK erp_id=%s tenant=%s", erp_id, self.tenant_id)
                return self._build_success(erp_id)
            logger.warning("[Balance] post failed HTTP %s: %s", r.status_code, r.text[:200])
            return self._build_error(f"HTTP {r.status_code}", r.text[:200])
        except Exception as e:
            logger.error("[Balance] post exception tenant=%s: %s", self.tenant_id, e)
            return self._build_error(str(e))

    def history(self, tenant_id, limit=50):
        if self.mode == "demo":
            return [{"erp_id": "DEMO-001", "date": "2026-04-01",
                     "amount": 1000, "description": "DEMO", "status": "posted"}]
        try:
            r = requests.get(f"{BALANCE_API_BASE}/api/v1/journal",
                             headers=self._headers(),
                             params={"limit": limit}, timeout=15)
            return [{"erp_id": str(i.get("id")), "date": i.get("date"),
                     "amount": float(i.get("amount", 0)),
                     "description": i.get("description", ""),
                     "status": "posted"} for i in r.json().get("items", [])]
        except Exception as e:
            logger.warning("balance_connector fetch_journal failed: %s", e)
            return []
