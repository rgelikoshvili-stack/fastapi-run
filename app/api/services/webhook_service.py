"""app/api/services/webhook_service.py — Zapier-compatible outbound webhooks.

Supported events:
  invoice.created     invoice.paid       invoice.overdue
  expense.created     expense.approved
  draft.approved      draft.rejected
  payment.received
  customer.created
"""
import hashlib
import hmac
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

_SUPPORTED_EVENTS = {
    "invoice.created", "invoice.paid", "invoice.overdue",
    "expense.created", "expense.approved",
    "draft.approved", "draft.rejected",
    "payment.received",
    "customer.created",
}


def _ensure_table(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS webhooks (
            id          SERIAL PRIMARY KEY,
            tenant_id   TEXT NOT NULL,
            url         TEXT NOT NULL,
            events      TEXT[] NOT NULL DEFAULT '{}',
            secret      TEXT,
            is_active   BOOLEAN DEFAULT TRUE,
            description TEXT,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            last_fired  TIMESTAMPTZ,
            failure_count INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_webhooks_tenant_active
            ON webhooks(tenant_id, is_active);
        CREATE TABLE IF NOT EXISTS webhook_deliveries (
            id          SERIAL PRIMARY KEY,
            webhook_id  INTEGER REFERENCES webhooks(id) ON DELETE CASCADE,
            tenant_id   TEXT NOT NULL,
            event       TEXT NOT NULL,
            payload     JSONB,
            status_code INTEGER,
            success     BOOLEAN DEFAULT FALSE,
            response    TEXT,
            delivered_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    cur.close()


def _sign_payload(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def fire_event(conn, tenant_id: str, event: str, data: dict):
    """Fire an event to all matching active webhooks for this tenant."""
    if event not in _SUPPORTED_EVENTS:
        return

    try:
        _ensure_table(conn)
    except Exception:
        pass

    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, url, secret FROM webhooks
            WHERE tenant_id = %s AND is_active = TRUE
              AND (events = '{}' OR %s = ANY(events))
        """, (tenant_id, event))
        hooks = cur.fetchall()
    except Exception as e:
        log.debug("webhook lookup failed: %s", e)
        cur.close()
        return
    finally:
        cur.close()

    if not hooks:
        return

    payload = {
        "event": event,
        "tenant_id": tenant_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    body = json.dumps(payload, default=str, ensure_ascii=False).encode()

    for hook_id, url, secret in hooks:
        _deliver(conn, hook_id, url, secret, event, body, payload)


def _deliver(conn, hook_id: int, url: str, secret: Optional[str],
             event: str, body: bytes, payload: dict):
    """HTTP POST with retry (2 attempts). Logs to webhook_deliveries."""
    headers = {
        "Content-Type": "application/json",
        "X-BridgeHub-Event": event,
        "User-Agent": "BridgeHub-Webhook/1.0",
    }
    if secret:
        headers["X-BridgeHub-Signature"] = _sign_payload(secret, body)

    status_code, response_text, success = None, "", False

    for attempt in range(2):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                status_code = resp.status
                response_text = resp.read(512).decode(errors="replace")
                success = 200 <= status_code < 300
                break
        except urllib.error.HTTPError as e:
            status_code = e.code
            response_text = str(e)
        except Exception as e:
            response_text = str(e)
            if attempt == 0:
                import time; time.sleep(1)

    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO webhook_deliveries
                (webhook_id, tenant_id, event, payload, status_code, success, response)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (hook_id, payload["tenant_id"], event,
              json.dumps(payload, default=str), status_code, success,
              response_text[:1000]))
        if success:
            cur.execute("UPDATE webhooks SET last_fired = NOW(), failure_count = 0 WHERE id = %s", (hook_id,))
        else:
            cur.execute("UPDATE webhooks SET failure_count = failure_count + 1 WHERE id = %s", (hook_id,))
        cur.close()
    except Exception as e:
        log.debug("webhook delivery log failed: %s", e)

    if not success:
        log.warning("webhook id=%d url=%s event=%s status=%s", hook_id, url, event, status_code)
