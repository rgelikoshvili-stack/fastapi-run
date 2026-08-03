"""app/api/routes_integrations.py — Shopify, Stripe, WooCommerce webhook receivers."""
import hashlib
import hmac
import json
import logging
import os

from fastapi import APIRouter, Request, Header

from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, http_error

log = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations", tags=["integrations"])


def _verify_shopify(body: bytes, sig: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig or "")


@router.post("/shopify/webhook")
async def shopify_webhook(
    request: Request,
    x_shopify_hmac_sha256: str = Header(None),
    x_shopify_topic: str = Header(None),
):
    """Receive Shopify order.created / order.paid → create journal draft."""
    body_bytes = await request.body()
    secret = os.environ.get("SHOPIFY_WEBHOOK_SECRET", "")
    if secret and not _verify_shopify(body_bytes, x_shopify_hmac_sha256 or "", secret):
        return http_error(401, "Invalid Shopify signature", "INVALID_SIGNATURE")

    topic = x_shopify_topic or ""
    if topic not in ("orders/create", "orders/paid", "orders/fulfilled"):
        return ok_response("Event ignored", {"topic": topic})

    try:
        event = json.loads(body_bytes)
    except Exception:
        return http_error(400, "Invalid JSON", "INVALID_BODY")

    tenant_id = request.headers.get("X-Tenant-ID") or os.environ.get("SHOPIFY_TENANT_ID", "default")
    order_num  = event.get("order_number", event.get("id", "?"))
    total      = float(event.get("total_price", 0) or 0)
    customer   = event.get("customer") or {}
    cname      = f"{customer.get('first_name','')} {customer.get('last_name','')}".strip() or "Shopify Customer"

    try:
        async with get_conn() as conn:
            await conn.execute(_q("""
                INSERT INTO journal_drafts
                    (tenant_id, date, description, partner, amount,
                     debit_account, credit_account, account_code,
                     reason, confidence, status, source_type)
                VALUES (%s, NOW()::date, %s, %s, %s,
                        '1120', '6110', '6110',
                        'shopify_order', 0.90, 'pending_approval', 'shopify')
            """), tenant_id, f"Shopify Order #{order_num} — {cname}", cname, total)
    except Exception as e:
        log.warning("shopify_webhook_db_error: %s", e)

    log.info("action=shopify_order tenant=%s order=%s amount=%.2f", tenant_id, order_num, total)
    return ok_response("Shopify order received", {"order": order_num, "amount": total})


def _verify_stripe(body: bytes, sig_header: str, secret: str) -> bool:
    try:
        parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
        timestamp = parts.get("t", "0")
        sig = parts.get("v1", "")
        payload = f"{timestamp}.".encode() + body
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig)
    except Exception:
        return False


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    """Receive Stripe payment.succeeded / invoice.paid → create journal draft."""
    body_bytes = await request.body()
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if secret and not _verify_stripe(body_bytes, stripe_signature or "", secret):
        return http_error(401, "Invalid Stripe signature", "INVALID_SIGNATURE")

    try:
        event = json.loads(body_bytes)
    except Exception:
        return http_error(400, "Invalid JSON", "INVALID_BODY")

    event_type = event.get("type", "")
    if event_type not in ("payment_intent.succeeded", "invoice.paid", "charge.succeeded"):
        return ok_response("Event ignored", {"type": event_type})

    tenant_id  = request.headers.get("X-Tenant-ID") or os.environ.get("STRIPE_TENANT_ID", "default")
    obj        = event.get("data", {}).get("object", {})
    cents      = int(obj.get("amount") or obj.get("amount_paid") or 0)
    amount     = cents / 100
    currency   = (obj.get("currency") or "usd").upper()
    customer   = obj.get("customer_email") or obj.get("receipt_email") or "Stripe Customer"
    payment_id = obj.get("id", "")

    try:
        async with get_conn() as conn:
            await conn.execute(_q("""
                INSERT INTO journal_drafts
                    (tenant_id, date, description, partner, amount,
                     debit_account, credit_account, account_code,
                     reason, confidence, status, source_type)
                VALUES (%s, NOW()::date, %s, %s, %s,
                        '1120', '6110', '6110',
                        'stripe_payment', 0.95, 'pending_approval', 'stripe')
            """), tenant_id, f"Stripe {event_type} {payment_id[:12]} ({currency})", customer, amount)
    except Exception as e:
        log.warning("stripe_webhook_db_error: %s", e)

    log.info("action=stripe_payment tenant=%s id=%s amount=%.2f", tenant_id, payment_id, amount)
    return ok_response("Stripe payment received", {"payment_id": payment_id, "amount": amount})


def _verify_woocommerce(body: bytes, sig: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig or "")


@router.post("/woocommerce/webhook")
async def woocommerce_webhook(
    request: Request,
    x_wc_webhook_signature: str = Header(None),
):
    """Receive WooCommerce order.created → create journal draft."""
    body_bytes = await request.body()
    secret = os.environ.get("WOOCOMMERCE_WEBHOOK_SECRET", "")
    if secret and not _verify_woocommerce(body_bytes, x_wc_webhook_signature or "", secret):
        return http_error(401, "Invalid WooCommerce signature", "INVALID_SIGNATURE")

    try:
        event = json.loads(body_bytes)
    except Exception:
        return http_error(400, "Invalid JSON", "INVALID_BODY")

    tenant_id = request.headers.get("X-Tenant-ID") or os.environ.get("WOOCOMMERCE_TENANT_ID", "default")
    order_id  = str(event.get("id", "?"))
    total     = float(event.get("total", 0) or 0)
    billing   = event.get("billing", {})
    cname     = f"{billing.get('first_name','')} {billing.get('last_name','')}".strip() or "WooCommerce Customer"

    try:
        async with get_conn() as conn:
            await conn.execute(_q("""
                INSERT INTO journal_drafts
                    (tenant_id, date, description, partner, amount,
                     debit_account, credit_account, account_code,
                     reason, confidence, status, source_type)
                VALUES (%s, NOW()::date, %s, %s, %s,
                        '1120', '6110', '6110',
                        'woocommerce_order', 0.88, 'pending_approval', 'woocommerce')
            """), tenant_id, f"WooCommerce Order #{order_id} — {cname}", cname, total)
    except Exception as e:
        log.warning("woocommerce_webhook_db_error: %s", e)

    log.info("action=woocommerce_order tenant=%s order=%s amount=%.2f", tenant_id, order_id, total)
    return ok_response("WooCommerce order received", {"order_id": order_id, "amount": total})


@router.get("/status")
def integrations_status():
    """List which integrations are configured via env vars."""
    state = {
        "shopify":     bool(os.environ.get("SHOPIFY_WEBHOOK_SECRET")),
        "stripe":      bool(os.environ.get("STRIPE_WEBHOOK_SECRET")),
        "woocommerce": bool(os.environ.get("WOOCOMMERCE_WEBHOOK_SECRET")),
        "google_oauth":    bool(os.environ.get("GOOGLE_CLIENT_ID")),
        "microsoft_oauth": bool(os.environ.get("MICROSOFT_CLIENT_ID")),
    }
    env_vars = {
        "SHOPIFY_WEBHOOK_SECRET":     bool(os.environ.get("SHOPIFY_WEBHOOK_SECRET")),
        "STRIPE_WEBHOOK_SECRET":      bool(os.environ.get("STRIPE_WEBHOOK_SECRET")),
        "WOOCOMMERCE_WEBHOOK_SECRET": bool(os.environ.get("WOOCOMMERCE_WEBHOOK_SECRET")),
        "GOOGLE_CLIENT_ID":           bool(os.environ.get("GOOGLE_CLIENT_ID")),
        "GOOGLE_CLIENT_SECRET":       bool(os.environ.get("GOOGLE_CLIENT_SECRET")),
        "MICROSOFT_CLIENT_ID":        bool(os.environ.get("MICROSOFT_CLIENT_ID")),
        "MICROSOFT_CLIENT_SECRET":    bool(os.environ.get("MICROSOFT_CLIENT_SECRET")),
    }
    return ok_response("Integration status", {
        "configured": [k for k, v in state.items() if v],
        "all": list(state.keys()),
        "details": state,
        "env_vars": env_vars,
    })


@router.get("/events")
async def integration_events(request: Request, limit: int = 30):
    """Recent webhook-sourced journal drafts."""
    from app.api.authz import require_permission
    from app.api.tenant_context import resolve_tenant_id as _resolve
    require_permission(request, "reports:read")
    tenant_id = _resolve(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            rows = [dict(r) for r in await conn.fetch(_q("""
                SELECT id, source_type AS source, reason AS event_type,
                       description AS reference, status, created_at
                FROM journal_drafts
                WHERE tenant_id = %s
                  AND source_type IN ('shopify','stripe','woocommerce')
                ORDER BY created_at DESC LIMIT %s
            """), tenant_id, limit)]
        for r in rows:
            if r.get("created_at"):
                r["created_at"] = str(r["created_at"])[:19]
    except Exception as e:
        log.warning("integration_events error: %s", e)
        rows = []
    return ok_response("Integration events", {"items": rows})
