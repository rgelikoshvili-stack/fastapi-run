with open("app/api/services/posting_service.py", "r", encoding="utf-8") as f:
    content = f.read()

old = """from app.api.balance_connector import (
    balance_config_status,
    balance_ping,
    build_balance_payload,
    post_to_balance,
)
from app.api.onec_connector import (
    onec_config_status,
    onec_ping,
    build_onec_payload,
    post_to_onec,
)
from app.api.oris_connector import (
    oris_config_status,
    oris_ping,
    build_oris_payload,
    post_to_oris,
)"""

new = """from app.api.connectors.balance_connector import BalanceConnector
from app.api.connectors.onec_connector import OneCConnector

def balance_config_status():
    return BalanceConnector().status()

def balance_ping():
    s = BalanceConnector().status()
    return {"ok": s.get("connected", False), "status": s.get("mode"), "details": s}

def build_balance_payload(draft):
    return {"account_dr": draft.get("account_code"), "account_cr": "1010",
            "amount": float(draft.get("amount") or 0),
            "description": draft.get("description"), "date": str(draft.get("date") or ""),
            "partner_id": draft.get("partner"), "draft_id": draft.get("id"),
            "currency": "GEL"}

def post_to_balance(payload):
    r = BalanceConnector().post(payload)
    return {"ok": r.get("success", False), "status": "posted" if r.get("success") else "failed",
            "erp_id": r.get("erp_id"), "error": r.get("error")}

def onec_config_status():
    return OneCConnector().status()

def onec_ping():
    s = OneCConnector().status()
    return {"ok": s.get("connected", False), "status": s.get("mode"), "details": s}

def build_onec_payload(draft):
    return {"account_dr": draft.get("account_code"), "account_cr": "1010",
            "amount": float(draft.get("amount") or 0),
            "description": draft.get("description"), "date": str(draft.get("date") or ""),
            "currency": "GEL"}

def post_to_onec(payload):
    r = OneCConnector().post(payload)
    return {"ok": r.get("success", False), "status": "posted" if r.get("success") else "failed",
            "erp_id": r.get("erp_id"), "error": r.get("error")}

def oris_config_status():
    return {"connected": False, "mode": "demo", "message": "ORIS not configured"}

def oris_ping():
    return {"ok": False, "status": "demo", "details": {}}

def build_oris_payload(draft):
    return build_balance_payload(draft)

def post_to_oris(payload):
    return {"ok": False, "status": "not_configured", "error": "ORIS not implemented"}"""

content = content.replace(old, new, 1)

with open("app/api/services/posting_service.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Done!")
