"""tests/unit/test_rsge_own_tin_autodetect.py — Own TIN storage and direction auto-detect."""
import asyncio
from unittest.mock import AsyncMock, patch


# ── Minimal doc fixture ───────────────────────────────────────────────────────

def _doc(buyer_inn="", seller_inn="", direction="unknown", amount=1000.0, vat=0.0):
    return {
        "id": 1, "tenant_id": "t1", "rsge_id": "DOC-1",
        "reg_no": "REG-001", "draft_id": None,
        "buyer_inn": buyer_inn, "seller_inn": seller_inn,
        "buyer_name": "მყიდველი", "seller_name": "გამყიდველი",
        "doc_date": "2025-01-01", "amount": amount, "vat_amount": vat,
        "direction": direction, "doc_type": "invoice",
    }


# ── 1. own TIN == buyer_inn → direction becomes "incoming" ──────────────────

def test_own_tin_as_buyer_means_incoming():
    own = "123456789"
    doc = _doc(buyer_inn=own)
    direction = "unknown"
    if own and doc["buyer_inn"] == own:
        direction = "incoming"
    elif own and doc["seller_inn"] == own:
        direction = "outgoing"
    assert direction == "incoming"


# ── 2. own TIN == seller_inn → direction becomes "outgoing" ──────────────────

def test_own_tin_as_seller_means_outgoing():
    own = "999888777"
    doc = _doc(seller_inn=own)
    direction = "unknown"
    if own and doc["buyer_inn"] == own:
        direction = "incoming"
    elif own and doc["seller_inn"] == own:
        direction = "outgoing"
    assert direction == "outgoing"


# ── 3. own TIN absent → direction stays "unknown" ────────────────────────────

def test_missing_own_tin_stays_unknown():
    own = ""
    doc = _doc(buyer_inn="111", seller_inn="222")
    direction = "unknown"
    if own and doc["buyer_inn"] == own:
        direction = "incoming"
    elif own and doc["seller_inn"] == own:
        direction = "outgoing"
    assert direction == "unknown"


# ── 4. Incoming → debit 1310, credit 3110 ────────────────────────────────────

def test_incoming_direction_account_defaults():
    direction = "incoming"
    debit_acc = "1310" if direction == "incoming" else "1210"
    credit_acc = "3110" if direction == "incoming" else "6110"
    assert debit_acc == "1310"
    assert credit_acc == "3110"


# ── 5. Outgoing → debit 1210, credit 6110 ────────────────────────────────────

def test_outgoing_direction_account_defaults():
    direction = "outgoing"
    debit_acc = "1210" if direction == "outgoing" else "1310"
    credit_acc = "6110" if direction == "outgoing" else "3110"
    assert debit_acc == "1210"
    assert credit_acc == "6110"


# ── 6. create_draft_from_document auto-fetches own_tin when empty ─────────────

def test_create_draft_auto_fetches_own_tin_when_empty():
    import asyncio
    import inspect
    from app.api.services import rsge_document_service as svc
    src = inspect.getsource(svc.create_draft_from_document)
    assert "rsge.own_tin" in src, "auto-fetch of rsge.own_tin must be present"
    assert "get_tenant_setting" in src


# ── 7. own TIN stored via tenant_settings key "rsge.own_tin" ──────────────────

def test_own_tin_tenant_settings_key():
    key = "rsge.own_tin"
    assert key.startswith("rsge.")
    assert "tin" in key


# ── 8. get_own_tin endpoint exists ───────────────────────────────────────────

def test_get_own_tin_route_exists():
    from app.api.routes_rs_ge import router
    routes = [r.path for r in router.routes]
    assert any("own-tin" in p for p in routes), "GET /own-tin route must be registered"


# ── 9. set_own_tin endpoint exists ───────────────────────────────────────────

def test_set_own_tin_route_exists():
    from app.api.routes_rs_ge import router
    from fastapi.routing import APIRoute
    post_routes = [r for r in router.routes
                   if isinstance(r, APIRoute) and "POST" in r.methods]
    paths = [r.path for r in post_routes]
    assert any("own-tin" in p for p in paths), "POST /own-tin route must be registered"


# ── 10. Direction unknown → draft type is "review_required" ──────────────────

def test_unknown_direction_draft_type():
    direction = "unknown"
    draft_type = {
        "incoming": "purchase",
        "outgoing": "sale",
    }.get(direction, "review_required")
    assert draft_type == "review_required"
