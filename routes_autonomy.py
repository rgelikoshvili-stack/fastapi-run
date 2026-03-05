from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import sqlite3, json, os, uuid
from datetime import datetime, timezone, timedelta

router = APIRouter(prefix="/autonomy", tags=["autonomy"])

DB_PATH = os.getenv("AUTONOMY_DB", "/tmp/autonomy.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS autonomy_config (
            id INTEGER PRIMARY KEY,
            mode TEXT DEFAULT 'OBSERVER',
            enabled INTEGER DEFAULT 0,
            max_amount REAL DEFAULT 500.0,
            max_transactions INTEGER DEFAULT 10,
            ttl_minutes INTEGER DEFAULT 60,
            expires_at TEXT,
            updated_at TEXT
        );
        INSERT OR IGNORE INTO autonomy_config (id, mode, enabled, updated_at)
        VALUES (1, 'OBSERVER', 0, datetime('now'));
    """)
    conn.commit()
    conn.close()

init_db()

class EnablePayload(BaseModel):
    mode: Optional[str] = "ASSISTED"
    max_amount: Optional[float] = 500.0
    max_transactions: Optional[int] = 10
    ttl_minutes: Optional[int] = 60

class ModePayload(BaseModel):
    mode: str

@router.get("/status")
def status():
    conn = get_db()
    row = conn.execute("SELECT * FROM autonomy_config WHERE id=1").fetchone()
    conn.close()
    cfg = dict(row)
    # TTL check
    if cfg["enabled"] and cfg["expires_at"]:
        expires = datetime.fromisoformat(cfg["expires_at"])
        if datetime.now(timezone.utc) > expires:
            _kill_switch()
            cfg["enabled"] = 0
            cfg["mode"] = "OBSERVER"
            cfg["note"] = "TTL expired — auto disabled"
    return {"ok": True, "autonomy": cfg}

@router.post("/enable")
def enable(payload: EnablePayload):
    if payload.mode not in ("ASSISTED", "AUTONOMOUS"):
        raise HTTPException(400, "mode must be ASSISTED or AUTONOMOUS")
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(minutes=payload.ttl_minutes)).isoformat()
    conn = get_db()
    conn.execute("""
        UPDATE autonomy_config SET
            mode=?, enabled=1,
            max_amount=?, max_transactions=?,
            ttl_minutes=?, expires_at=?, updated_at=?
        WHERE id=1
    """, (payload.mode, payload.max_amount, payload.max_transactions,
          payload.ttl_minutes, expires_at, now.isoformat()))
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "mode": payload.mode,
        "enabled": True,
        "expires_at": expires_at,
        "limits": {
            "max_amount": payload.max_amount,
            "max_transactions": payload.max_transactions,
            "ttl_minutes": payload.ttl_minutes
        }
    }

@router.post("/disable")
def disable():
    _kill_switch()
    return {"ok": True, "mode": "OBSERVER", "enabled": False, "reason": "manual kill-switch"}

def _kill_switch():
    conn = get_db()
    conn.execute("""
        UPDATE autonomy_config SET
            mode='OBSERVER', enabled=0, expires_at=NULL, updated_at=?
        WHERE id=1
    """, (datetime.now(timezone.utc).isoformat(),))
    conn.commit()
    conn.close()

@router.post("/check")
def check_allowed(amount: float = 0, transactions: int = 1):
    conn = get_db()
    row = conn.execute("SELECT * FROM autonomy_config WHERE id=1").fetchone()
    conn.close()
    cfg = dict(row)
    if not cfg["enabled"]:
        return {"ok": True, "allowed": False, "reason": "Autonomy disabled"}
    if cfg["expires_at"]:
        expires = datetime.fromisoformat(cfg["expires_at"])
        if datetime.now(timezone.utc) > expires:
            _kill_switch()
            return {"ok": True, "allowed": False, "reason": "TTL expired"}
    if amount > cfg["max_amount"]:
        return {"ok": True, "allowed": False, "reason": f"Amount {amount} exceeds limit {cfg['max_amount']}"}
    if transactions > cfg["max_transactions"]:
        return {"ok": True, "allowed": False, "reason": f"Transactions {transactions} exceeds limit {cfg['max_transactions']}"}
    return {"ok": True, "allowed": True, "mode": cfg["mode"]}

@router.get("/health")
def health():
    return {"ok": True, "service": "autonomy"}