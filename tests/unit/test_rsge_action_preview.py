"""tests/unit/test_rsge_action_preview.py — preview_action() coverage for all actions."""
import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest


def _doc(status="0", amount=1000.0, direction="incoming"):
    return {
        "id": 1, "tenant_id": "t1", "rsge_id": "500",
        "reg_no": "INV-001", "rsge_status": status,
        "rsge_status_code": status, "amount": amount,
        "full_amount": amount, "direction": direction,
        "waybill_number": "",
    }


async def _preview(action, doc=None, doc_type="document"):
    from app.api.services.rsge_action_service import preview_action
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=doc or _doc())
    return await preview_action(conn, "t1", 1, action, doc_type)


# ── 1. preview-confirm returns valid=True ────────────────────────────────────

def test_preview_confirm_valid():
    r = asyncio.run(_preview("confirm"))
    assert r["valid"] is True
    assert r["action"] == "confirm"
    assert r["test_mode"] is True
    assert r["requires_approval"] is True


# ── 2. preview-reject returns valid=True ─────────────────────────────────────

def test_preview_reject_valid():
    r = asyncio.run(_preview("reject"))
    assert r["valid"] is True
    assert r["action"] == "reject"


# ── 3. preview-correct returns valid=True ────────────────────────────────────

def test_preview_correct_valid():
    r = asyncio.run(_preview("correct"))
    assert r["valid"] is True
    assert r["action"] == "correct"


# ── 4. preview-cancel returns valid=True ─────────────────────────────────────

def test_preview_cancel_valid():
    r = asyncio.run(_preview("cancel"))
    assert r["valid"] is True
    assert r["action"] == "cancel"


# ── 5. preview-activate for waybill returns valid=True ───────────────────────

def test_preview_activate_waybill():
    r = asyncio.run(_preview("activate", doc_type="waybill"))
    assert r["valid"] is True
    assert r["action"] == "activate"


# ── 6. preview never mutates — no connector call ─────────────────────────────

def test_preview_makes_no_connector_call():
    import inspect
    from app.api.services import rsge_action_service as svc
    src = inspect.getsource(svc.preview_action)
    assert "connector" not in src, "preview_action must not call connector"


# ── 7. preview includes accounting_impact ────────────────────────────────────

def test_preview_includes_accounting_impact():
    r = asyncio.run(_preview("confirm"))
    assert "accounting_impact" in r
    assert r["accounting_impact"].get("impact") == "positive"


# ── 8. preview for cancel shows reversal impact ──────────────────────────────

def test_preview_cancel_shows_reversal():
    r = asyncio.run(_preview("cancel"))
    assert r["accounting_impact"].get("impact") == "reversal"


# ── 9. payload_preview has redacted credentials ──────────────────────────────

def test_preview_payload_redacted():
    r = asyncio.run(_preview("confirm"))
    pp = r["payload_preview"]
    assert pp["su"] == "****"
    assert pp["sp"] == "****"


# ── 10. preview for unknown action returns valid=False ───────────────────────

def test_preview_unknown_action_invalid():
    r = asyncio.run(_preview("HACK"))
    assert r["valid"] is False


# ── 11. preview includes current_status ──────────────────────────────────────

def test_preview_includes_current_status():
    r = asyncio.run(_preview("confirm", doc=_doc(status="0")))
    assert "current_status" in r


# ── 12. preview-confirm warns when already confirmed ─────────────────────────

def test_preview_confirm_warns_if_already_confirmed():
    r = asyncio.run(_preview("confirm", doc=_doc(status="confirmed")))
    assert r["valid"] is True
    assert len(r.get("warnings", [])) > 0


# ── 13. preview-correct warns when amount is zero ────────────────────────────

def test_preview_correct_warns_zero_amount():
    r = asyncio.run(_preview("correct", doc=_doc(amount=0.0)))
    assert len(r.get("warnings", [])) > 0


# ── 14. All 6 document actions are registered as routes ──────────────────────

def test_all_document_action_routes_registered():
    from app.api.routes_rs_ge import router
    paths = [r.path for r in router.routes]
    for action in ("confirm", "reject", "correct", "cancel"):
        assert any(f"preview-{action}" in p for p in paths), \
            f"preview-{action} route missing"
        assert any(f"test-{action}" in p for p in paths), \
            f"test-{action} route missing"


# ── 15. Production blocked for all actions ───────────────────────────────────

def test_production_blocked_for_all_actions():
    from fastapi import HTTPException
    from app.api.services.rsge_config import require_action_flag
    for action in ("confirm", "reject", "correct", "cancel"):
        with patch.dict(os.environ, {"RSGE_TEST_MODE": "false",
                                     f"RSGE_ALLOW_TEST_{action.upper()}": "false"}):
            with pytest.raises(HTTPException) as exc:
                require_action_flag(action)
            assert exc.value.status_code == 403
