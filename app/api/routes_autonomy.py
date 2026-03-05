from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import psycopg2, psycopg2.extras
from datetime import datetime, timezone, timedelta

router = APIRouter(prefix="/autonomy", tags=["autonomy"])

DB_URL = "postgresql://postgres:BridgeHub2026x@35.192.214.120/bridgehub"

def get_db():
    conn = psycopg2.connect(DB_URL)
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
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
        INSERT INTO autonomy_config (id, mode, enabled, updated_at)
        VALUES (1, 'OBSERVER', 0, NOW()::TEXT)
        ON CONFLICT DO NOTHING;
    """)
    conn.commit()
    cur.close()
    conn.close()

init_db()

class EnablePayload(BaseModel):
    mode: Optional[str] = "ASSISTED"
    max_amount: Optional[float] = 500.0
    max_transactions: Optional[int] = 10
    ttl_minutes: Optional[int] = 60

@router.get("/status")
def status():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM autonomy_config WHERE id=1")
    row = dict(cur.fetchone())
    cur.close(); conn.close()
    if row["enabled"] and row["expires_at"]:
        expires = datetime.fromisoformat(row["expires_at"])
        if datetime.now(timezone.utc) > expires:
            _kill_switch()
            row["enabled"] = 0
            row["mode"] = "OBSERVER"
            row["note"] = "TTL expired — auto disabled"
    return {"ok": True, "autonomy": row}

@router.post("/enable")
def enable(payload: EnablePayload):
    if payload.mode not in ("ASSISTED", "AUTONOMOUS"):
        raise HTTPException(400, "mode must be ASSISTED or AUTONOMOUS")
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(minutes=payload.ttl_minutes)).isoformat()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE autonomy_config SET
            mode=%s, enabled=1, max_amount=%s, max_transactions=%s,
            ttl_minutes=%s, expires_at=%s, updated_at=%s
        WHERE id=1
    """, (payload.mode, payload.max_amount, payload.max_transactions,
          payload.ttl_minutes, expires_at, now.isoformat()))
    conn.commit(); cur.close(); conn.close()
    return {"ok": True, "mode": payload.mode, "enabled": True,
            "expires_at": expires_at,
            "limits": {"max_amount": payload.max_amount,
                       "max_transactions": payload.max_transactions,
                       "ttl_minutes": payload.ttl_minutes}}

@router.post("/disable")
def disable():
    _kill_switch()
    return {"ok": True, "mode": "OBSERVER", "enabled": False, "reason": "manual kill-switch"}

def _kill_switch():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE autonomy_config SET
            mode='OBSERVER', enabled=0, expires_at=NULL, updated_at=%s
        WHERE id=1
    """, (datetime.now(timezone.utc).isoformat(),))
    conn.commit(); cur.close(); conn.close()

@router.post("/check")
def check_allowed(amount: float = 0, transactions: int = 1):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM autonomy_config WHERE id=1")
    cfg = dict(cur.fetchone())
    cur.close(); conn.close()
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
    return {"ok": True, "service": "autonomy", "db": "postgresql"}