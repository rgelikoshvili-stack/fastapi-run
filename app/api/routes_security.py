from fastapi import APIRouter, HTTPException, Request
import psycopg2, psycopg2.extras, hashlib, secrets
from datetime import datetime, timedelta
from app.api.db import get_db

router = APIRouter(prefix="/security", tags=["security"])



def ensure_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rate_limits (
            id SERIAL PRIMARY KEY,
            ip_address VARCHAR(50),
            endpoint VARCHAR(200),
            request_count INT DEFAULT 1,
            window_start TIMESTAMP DEFAULT NOW(),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS security_events (
            id SERIAL PRIMARY KEY,
            event_type VARCHAR(50),
            ip_address VARCHAR(50),
            endpoint VARCHAR(200),
            details TEXT,
            severity VARCHAR(20) DEFAULT 'LOW',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS api_tokens (
            id SERIAL PRIMARY KEY,
            token_hash VARCHAR(200) UNIQUE,
            name VARCHAR(100),
            permissions TEXT[],
            is_active BOOLEAN DEFAULT TRUE,
            last_used TIMESTAMP,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS blocked_ips (
            id SERIAL PRIMARY KEY,
            ip_address VARCHAR(50) UNIQUE,
            reason TEXT,
            blocked_at TIMESTAMP DEFAULT NOW(),
            blocked_until TIMESTAMP
        )
    """)

@router.post("/token/generate")
def generate_token(payload: dict):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    token = secrets.token_hex(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_days = payload.get("expires_days", 30)
    expires_at = datetime.utcnow() + timedelta(days=expires_days)
    cur.execute("""INSERT INTO api_tokens (token_hash, name, permissions, expires_at)
        VALUES (%s,%s,%s,%s) RETURNING id""",
        (token_hash, payload.get("name","API Token"),
         payload.get("permissions",["read"]), expires_at))
    tid = cur.fetchone()["id"]
    conn.commit()
    cur.close(); conn.close()
    return {"ok": True, "token": token, "token_id": tid,
            "expires_at": expires_at.isoformat(), "note": "Save this token — it won't be shown again"}

@router.post("/token/validate")
def validate_token(payload: dict):
    token = payload.get("token","")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    conn.commit()
    cur.execute("""SELECT * FROM api_tokens WHERE token_hash=%s AND is_active=TRUE
        AND (expires_at IS NULL OR expires_at > NOW())""", (token_hash,))
    tok = cur.fetchone()
    if tok:
        cur.execute("UPDATE api_tokens SET last_used=NOW() WHERE token_hash=%s", (token_hash,))
        conn.commit()
    cur.close(); conn.close()
    if not tok:
        return {"ok": False, "valid": False, "message": "Invalid or expired token"}
    return {"ok": True, "valid": True, "name": tok["name"],
            "permissions": tok["permissions"], "expires_at": str(tok["expires_at"])}

@router.get("/tokens")
def list_tokens():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    conn.commit()
    cur.execute("SELECT id, name, permissions, is_active, last_used, expires_at, created_at FROM api_tokens ORDER BY created_at DESC")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"ok": True, "tokens": rows}

@router.post("/ip/block")
def block_ip(payload: dict):
    conn = get_db()
    cur = conn.cursor()
    ensure_tables(cur)
    hours = payload.get("hours", 24)
    blocked_until = datetime.utcnow() + timedelta(hours=hours)
    cur.execute("""INSERT INTO blocked_ips (ip_address, reason, blocked_until)
        VALUES (%s,%s,%s) ON CONFLICT (ip_address) DO UPDATE
        SET reason=%s, blocked_until=%s""",
        (payload.get("ip"), payload.get("reason","Manual block"),
         blocked_until, payload.get("reason","Manual block"), blocked_until))
    conn.commit()
    cur.close(); conn.close()
    return {"ok": True, "ip": payload.get("ip"), "blocked_until": blocked_until.isoformat()}

@router.get("/ip/blocked")
def list_blocked():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    conn.commit()
    cur.execute("SELECT * FROM blocked_ips WHERE blocked_until > NOW() ORDER BY blocked_at DESC")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"ok": True, "blocked_ips": rows}

@router.post("/event/log")
def log_event(payload: dict):
    conn = get_db()
    cur = conn.cursor()
    ensure_tables(cur)
    cur.execute("""INSERT INTO security_events (event_type, ip_address, endpoint, details, severity)
        VALUES (%s,%s,%s,%s,%s)""",
        (payload.get("event_type","UNKNOWN"), payload.get("ip","0.0.0.0"),
         payload.get("endpoint","/"), payload.get("details",""),
         payload.get("severity","LOW")))
    conn.commit()
    cur.close(); conn.close()
    return {"ok": True, "message": "Security event logged"}

@router.get("/events")
def security_events():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    conn.commit()
    cur.execute("SELECT * FROM security_events ORDER BY created_at DESC LIMIT 50")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"ok": True, "events": rows}

@router.get("/summary")
def security_summary():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    conn.commit()
    cur.execute("SELECT COUNT(*) as c FROM api_tokens WHERE is_active=TRUE")
    active_tokens = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM blocked_ips WHERE blocked_until > NOW()")
    blocked_ips = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM security_events WHERE created_at > NOW() - INTERVAL '24 hours'")
    events_24h = cur.fetchone()["c"]
    cur.execute("SELECT severity, COUNT(*) as c FROM security_events GROUP BY severity")
    by_severity = {r["severity"]: r["c"] for r in cur.fetchall()}
    cur.close(); conn.close()
    return {
        "ok": True,
        "active_tokens": active_tokens,
        "blocked_ips": blocked_ips,
        "events_last_24h": events_24h,
        "events_by_severity": by_severity,
        "security_status": "ALERT" if events_24h > 100 else "NORMAL"
    }