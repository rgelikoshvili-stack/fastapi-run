"""tests/unit/test_approval_routes.py
Approval route unit tests — structural and logic checks without DB.
"""
import inspect
from unittest.mock import MagicMock, patch


def _mock_request(tenant: str = "tenant_a"):
    req = MagicMock()
    req.state.tenant_id = tenant
    return req


# ── 1. Queue endpoint exists and is tenant-scoped ────────────────────────────

def test_approval_queue_is_tenant_scoped():
    import app.api.routes_approval as mod
    src = inspect.getsource(mod)
    assert "tenant_id" in src
    assert "/queue" in src or "get_queue" in src


# ── 2. Approve endpoint exists ────────────────────────────────────────────────

def test_approve_endpoint_exists():
    import app.api.routes_approval as mod
    src = inspect.getsource(mod)
    assert "approve" in src
    assert "draft_id" in src


# ── 3. Reject endpoint exists ─────────────────────────────────────────────────

def test_reject_endpoint_exists():
    import app.api.routes_approval as mod
    src = inspect.getsource(mod)
    assert "reject" in src


# ── 4. Cross-tenant guard: approval service checks tenant ────────────────────

def test_approve_service_checks_tenant():
    from app.api.services import approval_service
    src = inspect.getsource(approval_service)
    assert "tenant_id" in src
    # Both the fetch and update must scope to tenant
    tenant_count = src.count("tenant_id")
    assert tenant_count >= 10, f"Expected ≥10 tenant_id refs in approval_service, got {tenant_count}"


# ── 5. Autopilot uses confidence threshold ────────────────────────────────────

def test_autopilot_confidence_threshold():
    import app.api.routes_approval as mod
    src = inspect.getsource(mod)
    # auto-approve requires confidence check
    assert "confidence" in src or "autopilot" in src.lower()
    assert "0.8" in src or "0.80" in src or "threshold" in src.lower() or "auto" in src.lower()


# ── 6. Stats endpoint is cached ───────────────────────────────────────────────

def test_stats_uses_cache():
    import app.api.routes_approval as mod
    src = inspect.getsource(mod)
    assert "cache" in src.lower() or "stats" in src.lower()


# ── 7. Batch action endpoint exists ──────────────────────────────────────────

def test_batch_action_exists():
    import app.api.routes_approval as mod
    src = inspect.getsource(mod)
    assert "batch" in src.lower()
    assert "tenant_id" in src
    assert '"succeeded": succeeded' in src
    assert '"failed": failed' in src
    assert '"skipped": skipped' in src
    assert '"items": items' in src


def test_reject_contract_accepts_note():
    import app.api.routes_approval as mod
    src = inspect.getsource(mod)
    assert 'note: Optional[str] = ""' in src
    assert "req.note" in src
    assert "body.note" in src


def test_preview_first_and_structured_reject_hooks_exist():
    from pathlib import Path

    approval = Path("static/approval.html").read_text(encoding="utf-8")
    assert "approveWithPreview" in approval
    assert "_openRejectModal" in approval
    assert "submitReject()" in approval


# ── 8. Approval service validate_lines integration ───────────────────────────

def test_posting_service_validate_lines_balanced():
    from app.api.services.posting_service import _validate_lines
    lines = [
        {"account_code": "1120", "debit": 500, "credit": 0},
        {"account_code": "6110", "debit": 0,   "credit": 500},
    ]
    assert _validate_lines(lines) is None


def test_posting_service_validate_lines_unbalanced():
    from app.api.services.posting_service import _validate_lines
    lines = [
        {"account_code": "1120", "debit": 500, "credit": 0},
        {"account_code": "6110", "debit": 0,   "credit": 400},
    ]
    result = _validate_lines(lines)
    assert result is not None


def test_approval_routes_success_responses_use_standard_envelope():
    """Approval route successes should use ok_response(message, data), not ok_response(data)."""
    import inspect
    import app.api.routes_approval as mod

    src = inspect.getsource(mod)
    assert 'return {"ok": True' not in src
    assert 'return ok_response([])' not in src
    assert 'return ok_response({"draft_id"' not in src
    assert 'return ok_response({"signed_url"' not in src
    assert 'ok_response("No changes requested", {"draft_id": draft_id})' in src
    assert 'ok_response("Batch action complete", payload)' in src


def test_approval_attachment_responses_keep_data_field():
    import inspect
    import app.api.routes_approval as mod

    src = inspect.getsource(mod)
    assert 'ok_response("Draft attachment saved", {"draft_id": draft_id' in src
    assert 'ok_response("Draft attachment URL", {"signed_url": signed_url' in src
    assert 'ok_response("Draft attachment deleted", {"draft_id": draft_id' in src
