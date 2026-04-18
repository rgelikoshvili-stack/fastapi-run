"""app/api/connectors/onec_connector.py"""
import os, logging, requests
from datetime import datetime, timezone
from app.api.connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)

class OneCConnector(BaseConnector):
    def __init__(self, tenant_id="default"):
        self.tenant_id = tenant_id
        self.endpoint  = os.environ.get("ONEC_ENDPOINT", "")
        self.username  = os.environ.get("ONEC_USERNAME", "")
        self.password  = os.environ.get("ONEC_PASSWORD", "")
        self.mode      = "live" if self.endpoint else "demo"

    def _auth(self): return (self.username, self.password)
    def _headers(self): return {"Accept": "application/json",
                                "Content-Type": "application/json"}

    def status(self):
        if self.mode == "demo":
            return {"connected": True, "mode": "demo", "message": "DEMO"}
        try:
            r = requests.get(self.endpoint + "/", auth=self._auth(),
                             headers=self._headers(), timeout=15)
            return {"connected": r.status_code == 200, "mode": "live",
                    "message": "OK" if r.status_code == 200 else str(r.status_code)}
        except Exception as e:
            return {"connected": False, "mode": "live", "message": str(e)}

    def validate_config(self):
        return True if self.mode == "demo" else self.status().get("connected", False)

    def preview(self, draft):
        errors = []
        if not draft.get("account_dr"): errors.append("account_dr აკლია")
        if not draft.get("account_cr"): errors.append("account_cr აკლია")
        if float(draft.get("amount", 0)) <= 0: errors.append("amount > 0")
        return {"valid": len(errors) == 0, "mode": self.mode,
                "errors": errors, "warnings": []}

    def post(self, draft):
        if self.mode == "demo":
            fid = f"1C-DEMO-{datetime.now().strftime('%H%M%S')}"
            logger.info(f"[1C] DEMO: {fid}")
            return self._build_success(fid)
        try:
            payload = {
                "Date":      draft.get("date") or datetime.now(timezone.utc).isoformat(),
                "AccountDr": str(draft.get("account_dr", "")),
                "AccountCr": str(draft.get("account_cr", "")),
                "Amount":    float(draft.get("amount", 0)),
                "Currency":  draft.get("currency", "GEL"),
                "Comment":   draft.get("description", ""),
                "Posted":    True,
            }
            r = requests.post(self.endpoint + "/Document_JournalEntry",
                              auth=self._auth(), headers=self._headers(),
                              json=payload, timeout=20)
            if r.status_code in (200, 201):
                return self._build_success(str(r.json().get("Ref_Key", "unknown")))
            return self._build_error(f"HTTP {r.status_code}", r.text[:200])
        except Exception as e:
            return self._build_error(str(e))

    def history(self, tenant_id, limit=50):
        if self.mode == "demo":
            return [{"erp_id": "1C-001", "date": "2026-04-01",
                     "amount": 500, "description": "1C DEMO", "status": "posted"}]
        try:
            r = requests.get(self.endpoint + "/Document_JournalEntry",
                             auth=self._auth(), headers=self._headers(),
                             params={"$top": limit, "$orderby": "Date desc",
                                     "$format": "json"}, timeout=20)
            return [{"erp_id": str(i.get("Ref_Key", "")),
                     "date": i.get("Date", "")[:10],
                     "amount": float(i.get("Amount", 0)),
                     "description": i.get("Comment", ""),
                     "status": "posted"} for i in r.json().get("value", [])]
        except Exception as e:
            logger.warning("onec_connector fetch_journal failed: %s", e)
            return []
