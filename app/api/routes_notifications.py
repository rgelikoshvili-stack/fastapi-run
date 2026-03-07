from fastapi import APIRouter
import psycopg2, psycopg2.extras, json, httpx
from datetime import datetime
from app.api.db import get_db

router = APIRouter(prefix="/notifications", tags=["notifications"])



def ensure_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            type VARCHAR(50),
            title VARCHAR(200),
            message TEXT,
            severity VARCHAR(20) DEFAULT 'INFO',
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS webhook_configs (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100),
            url TEXT,
            events TEXT[],
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS webhook_logs (
            id SERIAL PRIMARY KEY,
            webhook_id INT,
            event VARCHAR(100),
            payload JSONB,
            status_code INT,
            success BOOLEAN,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

@router.get("/list")
def list_notifications():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    conn.commit()
    cur.execute("SELECT * FROM notifications ORDER BY created_at DESC LIMIT 50")
    rows = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) as unread FROM notifications WHERE is_read=FALSE")
    unread = cur.fetchone()["unread"]
    cur.close(); conn.close()
    return {"ok": True, "notifications": rows, "unread_count": unread}

@router.post("/create")
def create_notification(payload: dict):
    conn = get_db()
    cur = conn.cursor()
    ensure_tables(cur)
    cur.execute("""
        INSERT INTO notifications (type, title, message, severity)
        VALUES (%s,%s,%s,%s)
    """, (
        payload.get("type", "SYSTEM"),
        payload.get("title", "Notification"),
        payload.get("message", ""),
        payload.get("severity", "INFO")
    ))
    conn.commit()
    cur.close(); conn.close()
    return {"ok": True, "message": "Notification created"}

@router.post("/mark-read/{notification_id}")
def mark_read(notification_id: int):
    conn = get_db()
    cur = conn.cursor()
    ensure_tables(cur)
    cur.execute("UPDATE notifications SET is_read=TRUE WHERE id=%s", (notification_id,))
    conn.commit()
    cur.close(); conn.close()
    return {"ok": True, "message": f"Notification {notification_id} marked as read"}

@router.post("/mark-all-read")
def mark_all_read():
    conn = get_db()
    cur = conn.cursor()
    ensure_tables(cur)
    cur.execute("UPDATE notifications SET is_read=TRUE WHERE is_read=FALSE")
    conn.commit()
    cur.close(); conn.close()
    return {"ok": True, "message": "All notifications marked as read"}

@router.post("/webhook/register")
def register_webhook(payload: dict):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    cur.execute("""
        INSERT INTO webhook_configs (name, url, events)
        VALUES (%s,%s,%s) RETURNING id
    """, (
        payload.get("name", "Webhook"),
        payload.get("url"),
        payload.get("events", ["document.approved", "document.rejected"])
    ))
    wid = cur.fetchone()["id"]
    conn.commit()
    cur.close(); conn.close()
    return {"ok": True, "webhook_id": wid, "message": "Webhook registered"}

@router.get("/webhook/list")
def list_webhooks():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    conn.commit()
    cur.execute("SELECT * FROM webhook_configs ORDER BY created_at DESC")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"ok": True, "webhooks": rows}

@router.post("/webhook/trigger")
def trigger_webhook(payload: dict):
    event = payload.get("event", "test.event")
    data = payload.get("data", {})
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    conn.commit()
    cur.execute("SELECT * FROM webhook_configs WHERE is_active=TRUE")
    webhooks = [dict(r) for r in cur.fetchall()]
    results = []
    for wh in webhooks:
        if event in (wh.get("events") or []) or "all" in (wh.get("events") or []):
            try:
                r = httpx.post(wh["url"], json={"event": event, "data": data, "timestamp": datetime.utcnow().isoformat()}, timeout=5)
                cur.execute("INSERT INTO webhook_logs (webhook_id,event,payload,status_code,success) VALUES (%s,%s,%s,%s,%s)",
                    (wh["id"], event, json.dumps(data), r.status_code, r.status_code < 400))
                results.append({"webhook": wh["name"], "status": r.status_code, "success": True})
            except Exception as e:
                cur.execute("INSERT INTO webhook_logs (webhook_id,event,payload,status_code,success) VALUES (%s,%s,%s,%s,%s)",
                    (wh["id"], event, json.dumps(data), 0, False))
                results.append({"webhook": wh["name"], "error": str(e), "success": False})
    conn.commit()
    cur.close(); conn.close()
    return {"ok": True, "event": event, "triggered": len(results), "results": results}

@router.get("/webhook/logs")
def webhook_logs():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    conn.commit()
    cur.execute("SELECT * FROM webhook_logs ORDER BY created_at DESC LIMIT 50")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"ok": True, "logs": rows}