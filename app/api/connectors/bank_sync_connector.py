"""
app/api/connectors/bank_sync_connector.py
Bridge Hub — Bank Direct Sync
TBC + BOG Open Banking API
DEMO mode — credentials-ის გარეშე.
"""
import os
import json
import urllib.request
from datetime import datetime, timedelta
from typing import Optional
import psycopg2.extras
from app.api.db import get_db


# ========== Config ==========

TBC_API_BASE = os.getenv("TBC_API_BASE", "https://api.tbcbank.ge/v1")
TBC_CLIENT_ID = os.getenv("TBC_CLIENT_ID", "")
TBC_CLIENT_SECRET = os.getenv("TBC_CLIENT_SECRET", "")

BOG_API_BASE = os.getenv("BOG_API_BASE", "https://api.bog.ge/v1")
BOG_CLIENT_ID = os.getenv("BOG_CLIENT_ID", "")
BOG_CLIENT_SECRET = os.getenv("BOG_CLIENT_SECRET", "")


# ========== TBC Connector ==========

class TBCConnector:
    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id
        self.mode = "live" if TBC_CLIENT_ID and TBC_CLIENT_SECRET else "demo"

    def status(self) -> dict:
        connected = self.mode == "demo" or self._check_connection()
        return {
            "bank": "TBC",
            "mode": self.mode,
            "status": "LIVE" if (self.mode == "live" and connected) else ("DEMO" if self.mode == "demo" else "ERROR"),
            "connected": connected,
            "api_base": TBC_API_BASE,
            "config_present": bool(TBC_CLIENT_ID and TBC_CLIENT_SECRET),
        }

    def _check_connection(self) -> bool:
        try:
            req = urllib.request.Request(
                f"{TBC_API_BASE}/health",
                headers={"Authorization": f"Bearer {self._get_token()}"},
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status == 200
        except Exception:
            return False

    def _get_token(self) -> str:
        if self.mode == "demo":
            return "demo_token"
        try:
            data = f"client_id={TBC_CLIENT_ID}&client_secret={TBC_CLIENT_SECRET}&grant_type=client_credentials".encode()
            req = urllib.request.Request(
                f"{TBC_API_BASE}/oauth/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())["access_token"]
        except Exception:
            return ""

    def sync_transactions(
        self,
        account_id: str = "default",
        days: int = 7,
    ) -> dict:
        if self.mode == "demo":
            return self._demo_transactions()

        try:
            date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            date_to = datetime.now().strftime("%Y-%m-%d")
            token = self._get_token()

            req = urllib.request.Request(
                f"{TBC_API_BASE}/accounts/{account_id}/transactions?from={date_from}&to={date_to}",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())

            transactions = []
            for tx in data.get("transactions", []):
                transactions.append({
                    "bank": "TBC",
                    "date": tx.get("date", ""),
                    "amount": float(tx.get("amount", 0)),
                    "description": tx.get("description", ""),
                    "reference": tx.get("reference", ""),
                    "type": tx.get("type", ""),
                })

            return {
                "ok": True,
                "bank": "TBC",
                "mode": "live",
                "count": len(transactions),
                "transactions": transactions,
            }
        except Exception as e:
            return {"ok": False, "bank": "TBC", "error": str(e)}

    def _demo_transactions(self) -> dict:
        return {
            "ok": True,
            "bank": "TBC",
            "mode": "demo",
            "count": 3,
            "transactions": [
                {"bank": "TBC", "date": datetime.now().strftime("%Y-%m-%d"),
                 "amount": -1500.0, "description": "Office rent payment",
                 "reference": "TBC-001", "type": "debit"},
                {"bank": "TBC", "date": datetime.now().strftime("%Y-%m-%d"),
                 "amount": 5000.0, "description": "Client payment received",
                 "reference": "TBC-002", "type": "credit"},
                {"bank": "TBC", "date": datetime.now().strftime("%Y-%m-%d"),
                 "amount": -45.0, "description": "Bank commission",
                 "reference": "TBC-003", "type": "debit"},
            ]
        }


# ========== BOG Connector ==========

class BOGConnector:
    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id
        self.mode = "live" if BOG_CLIENT_ID and BOG_CLIENT_SECRET else "demo"

    def status(self) -> dict:
        return {
            "bank": "BOG",
            "mode": self.mode,
            "status": "LIVE" if self.mode == "live" else "DEMO",
            "connected": True,
            "api_base": BOG_API_BASE,
            "config_present": bool(BOG_CLIENT_ID and BOG_CLIENT_SECRET),
        }

    def sync_transactions(
        self,
        account_id: str = "default",
        days: int = 7,
    ) -> dict:
        if self.mode == "demo":
            return self._demo_transactions()

        try:
            date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            token = self._get_token()

            req = urllib.request.Request(
                f"{BOG_API_BASE}/accounts/{account_id}/statement?from={date_from}",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())

            transactions = []
            for tx in data.get("items", []):
                transactions.append({
                    "bank": "BOG",
                    "date": tx.get("date", ""),
                    "amount": float(tx.get("amount", 0)),
                    "description": tx.get("details", ""),
                    "reference": tx.get("id", ""),
                    "type": "credit" if float(tx.get("amount", 0)) > 0 else "debit",
                })

            return {
                "ok": True,
                "bank": "BOG",
                "mode": "live",
                "count": len(transactions),
                "transactions": transactions,
            }
        except Exception as e:
            return {"ok": False, "bank": "BOG", "error": str(e)}

    def _get_token(self) -> str:
        try:
            data = f"client_id={BOG_CLIENT_ID}&client_secret={BOG_CLIENT_SECRET}&grant_type=client_credentials".encode()
            req = urllib.request.Request(
                f"{BOG_API_BASE}/oauth/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())["access_token"]
        except Exception:
            return ""

    def _demo_transactions(self) -> dict:
        return {
            "ok": True,
            "bank": "BOG",
            "mode": "demo",
            "count": 3,
            "transactions": [
                {"bank": "BOG", "date": datetime.now().strftime("%Y-%m-%d"),
                 "amount": -590.0, "description": "Internet service payment",
                 "reference": "BOG-001", "type": "debit"},
                {"bank": "BOG", "date": datetime.now().strftime("%Y-%m-%d"),
                 "amount": 12000.0, "description": "Invoice payment from client",
                 "reference": "BOG-002", "type": "credit"},
                {"bank": "BOG", "date": datetime.now().strftime("%Y-%m-%d"),
                 "amount": -40.0, "description": "Bank fee",
                 "reference": "BOG-003", "type": "debit"},
            ]
        }


# ========== Unified Sync ==========

def sync_all_banks(tenant_id: str = "default", days: int = 7) -> dict:
    """
    ყველა ბანკიდან ტრანზაქციების sync.
    """
    tbc = TBCConnector(tenant_id)
    bog = BOGConnector(tenant_id)

    tbc_result = tbc.sync_transactions(days=days)
    bog_result = bog.sync_transactions(days=days)

    all_transactions = []
    if tbc_result.get("ok"):
        all_transactions.extend(tbc_result.get("transactions", []))
    if bog_result.get("ok"):
        all_transactions.extend(bog_result.get("transactions", []))

    saved = _save_to_queue(all_transactions, tenant_id)

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "days": days,
        "tbc": {"ok": tbc_result.get("ok"), "count": tbc_result.get("count", 0), "mode": tbc_result.get("mode")},
        "bog": {"ok": bog_result.get("ok"), "count": bog_result.get("count", 0), "mode": bog_result.get("mode")},
        "total_synced": len(all_transactions),
        "saved_to_queue": saved,
    }


def _save_to_queue(transactions: list, tenant_id: str) -> int:
    """
    ტრანზაქციები DB-ში queue-ში ინახება classification-ისთვის.
    """
    if not transactions:
        return 0

    conn = get_db()
    cur = conn.cursor()
    saved = 0

    try:
        for tx in transactions:
            try:
                # classify transaction
                try:
                    from bridge_hub_knowledge import classify_transaction
                    desc = tx.get("description", "")
                    cls = classify_transaction(desc, tenant_id)
                    acc_code = cls.get("account", "7910")
                    conf = float(cls.get("confidence", 0.5))
                    tx_type = tx.get("type", "debit")
                    if tx_type == "debit":
                        dr_acc = acc_code
                        cr_acc = "1120"
                    else:
                        dr_acc = "1120"
                        cr_acc = acc_code
                except Exception:
                    acc_code = "7910"
                    conf = 0.5
                    dr_acc = "1210"
                    cr_acc = "1120"

                cur.execute("""
                    INSERT INTO journal_drafts (
                        date, description, partner, amount,
                        debit_account, credit_account, account_code,
                        reason, confidence, status, source_type, tenant_id, created_at
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        'bank_sync', %s, 'pending_approval',
                        %s, %s, NOW()
                    )
                """, (
                    tx.get("date") or datetime.now().strftime("%Y-%m-%d"),
                    tx.get("description", ""),
                    tx.get("bank", ""),
                    abs(float(tx.get("amount", 0))),
                    dr_acc, cr_acc, acc_code,
                    conf,
                    f"bank_sync_{tx.get('bank', '').lower()}",
                    tenant_id,
                ))
                saved += 1
            except Exception:
                continue

        conn.commit()
        return saved
    except Exception:
        conn.rollback()
        return 0
    finally:
        cur.close()
        conn.close()