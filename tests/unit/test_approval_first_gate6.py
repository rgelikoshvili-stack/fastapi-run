"""tests/unit/test_approval_first_gate6.py — Gate 6: Approval-First Workflow.

Verifies that NO live posting can occur without a human-approved journal draft.

Tests:
- _validate_approved_draft rejects every non-approved status.
- _validate_approved_draft accepts only 'approved'.
- _validate_approved_draft rejects approved drafts with empty/invalid lines.
- apply_posting_service returns DRAFT_NOT_APPROVED for a non-approved draft.
- apply_posting_service proceeds to connector for an approved draft.
- Posting without prior approval is structurally blocked.
- approve_draft_service transitions draft to 'approved' status.
- Approval routes are guarded by approval:write RBAC.
- Posting routes are guarded by posting:write RBAC.
- _validate_approved_draft is called inside apply_posting_service.
- CFO dual-approval threshold check is present in approval source.
- Audit event is emitted on approval.
"""
import asyncio
import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# _validate_approved_draft — pure unit tests
# ---------------------------------------------------------------------------

def _make_draft(status="approved", lines=None):
    if lines is None:
        lines = [
            {"account_code": "1210", "debit": 500.0, "credit": 0,    "label": "Bank"},
            {"account_code": "3110", "debit": 0,     "credit": 500.0, "label": "Rev"},
        ]
    return {
        "id": 1, "tenant_id": "t1", "status": status,
        "amount": 500.0, "currency": "GEL",
        "lines": lines,
    }


def test_validate_rejects_drafted_status():
    from app.api.services.posting_service import _validate_approved_draft
    result = _validate_approved_draft(_make_draft(status="drafted"), 1, "t1")
    assert result is not None
    assert result["error"]["code"] == "DRAFT_NOT_APPROVED"


def test_validate_rejects_rejected_status():
    from app.api.services.posting_service import _validate_approved_draft
    result = _validate_approved_draft(_make_draft(status="rejected"), 1, "t1")
    assert result is not None
    assert result["error"]["code"] == "DRAFT_NOT_APPROVED"


def test_validate_rejects_pending_approval_status():
    from app.api.services.posting_service import _validate_approved_draft
    result = _validate_approved_draft(_make_draft(status="pending_approval"), 1, "t1")
    assert result is not None
    assert result["error"]["code"] == "DRAFT_NOT_APPROVED"


def test_validate_rejects_posted_status():
    from app.api.services.posting_service import _validate_approved_draft
    result = _validate_approved_draft(_make_draft(status="posted"), 1, "t1")
    assert result is not None
    assert result["error"]["code"] == "DRAFT_NOT_APPROVED"


def test_validate_rejects_awaiting_cfo_status():
    from app.api.services.posting_service import _validate_approved_draft
    result = _validate_approved_draft(_make_draft(status="awaiting_cfo"), 1, "t1")
    assert result is not None
    assert result["error"]["code"] == "DRAFT_NOT_APPROVED"


def test_validate_accepts_approved_status():
    from app.api.services.posting_service import _validate_approved_draft
    result = _validate_approved_draft(_make_draft(status="approved"), 1, "t1")
    assert result is None, "approved draft must pass validation"


def test_validate_rejects_approved_draft_with_empty_lines():
    from app.api.services.posting_service import _validate_approved_draft
    result = _validate_approved_draft(_make_draft(status="approved", lines=[]), 1, "t1")
    assert result is not None
    assert result["error"]["code"] == "INVALID_JOURNAL_LINES"


def test_validate_rejects_approved_draft_with_unbalanced_lines():
    from app.api.services.posting_service import _validate_approved_draft
    unbalanced = [
        {"account_code": "1210", "debit": 500.0, "credit": 0,    "label": "Bank"},
        {"account_code": "3110", "debit": 0,     "credit": 300.0, "label": "Rev"},
    ]
    result = _validate_approved_draft(_make_draft(status="approved", lines=unbalanced), 1, "t1")
    assert result is not None
    assert result["error"]["code"] == "INVALID_JOURNAL_LINES"


def test_validate_returns_not_found_for_none_draft():
    from app.api.services.posting_service import _validate_approved_draft
    result = _validate_approved_draft(None, 99, "t1")
    assert result is not None
    assert result["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# apply_posting_service — rejects non-approved draft (service-level)
# ---------------------------------------------------------------------------

class _FakeConnCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_):
        pass


def _make_posting_conn(status="drafted"):
    conn = AsyncMock()
    draft_row = {
        "id": 10, "tenant_id": "t1", "date": "2026-05-25",
        "description": "Test", "partner": "LLC",
        "amount": 500.0, "status": status, "currency": "GEL",
        "lines_json": [
            {"account_code": "1210", "debit": 500.0, "credit": 0,    "label": "Bank"},
            {"account_code": "3110", "debit": 0,     "credit": 500.0, "label": "Rev"},
        ],
    }
    conn.fetchrow = AsyncMock(return_value=draft_row)
    conn.fetchval = AsyncMock(return_value=None)
    conn.execute = AsyncMock()
    tr = AsyncMock()
    tr.start = AsyncMock()
    tr.commit = AsyncMock()
    tr.rollback = AsyncMock()
    conn.transaction = MagicMock(return_value=tr)
    return conn


@pytest.mark.asyncio
async def test_apply_posting_rejects_drafted_draft():
    conn = _make_posting_conn(status="drafted")
    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)):
        from app.api.services.posting_service import apply_posting_service
        result = await apply_posting_service(10, "balance", "t1")

    assert result["ok"] is False
    assert result["error"]["code"] == "DRAFT_NOT_APPROVED"


@pytest.mark.asyncio
async def test_apply_posting_rejects_rejected_draft():
    conn = _make_posting_conn(status="rejected")
    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)):
        from app.api.services.posting_service import apply_posting_service
        result = await apply_posting_service(10, "balance", "t1")

    assert result["ok"] is False
    assert result["error"]["code"] == "DRAFT_NOT_APPROVED"


@pytest.mark.asyncio
async def test_apply_posting_rejects_pending_approval_draft():
    conn = _make_posting_conn(status="pending_approval")
    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)):
        from app.api.services.posting_service import apply_posting_service
        result = await apply_posting_service(10, "balance", "t1")

    assert result["ok"] is False
    assert result["error"]["code"] == "DRAFT_NOT_APPROVED"


@pytest.mark.asyncio
async def test_apply_posting_reaches_connector_for_approved_draft():
    """An approved draft must pass validation and reach the connector readiness check."""
    conn = _make_posting_conn(status="approved")
    # Also mock the duplicate-log check fetchrow (second call returns None)
    conn.fetchrow = AsyncMock(side_effect=[
        {  # draft row
            "id": 10, "tenant_id": "t1", "date": "2026-05-25",
            "description": "Test", "partner": "LLC",
            "amount": 500.0, "status": "approved", "currency": "GEL",
            "lines_json": [
                {"account_code": "1210", "debit": 500.0, "credit": 0,    "label": "Bank"},
                {"account_code": "3110", "debit": 0,     "credit": 500.0, "label": "Rev"},
            ],
        },
        None,  # duplicate invoice check
        None,  # re-post guard
    ])
    conn.fetchval = AsyncMock(side_effect=[None, 77])  # period_lock=None, log_id=77

    not_ready = {"ok": False, "message": "connector not configured"}
    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.posting_service._get_connector_readiness",
               return_value=not_ready):
        from app.api.services.posting_service import apply_posting_service
        result = await apply_posting_service(10, "balance", "t1")

    # Approved draft reaches the connector check — it's not DRAFT_NOT_APPROVED
    assert result["error"]["code"] != "DRAFT_NOT_APPROVED"


# ---------------------------------------------------------------------------
# Structural: _validate_approved_draft is called in apply_posting_service
# ---------------------------------------------------------------------------

def test_apply_posting_service_calls_validate_approved_draft():
    from app.api.services import posting_service
    src = inspect.getsource(posting_service.apply_posting_service)
    assert "_validate_approved_draft" in src, (
        "apply_posting_service must call _validate_approved_draft to enforce approval-first"
    )


def test_validate_approved_draft_uses_approved_status_check():
    from app.api.services import posting_service
    src = inspect.getsource(posting_service._validate_approved_draft)
    assert "approved" in src
    assert "DRAFT_NOT_APPROVED" in src


# ---------------------------------------------------------------------------
# Structural: RBAC guards on approval and posting routes
# ---------------------------------------------------------------------------

def test_approve_route_requires_approval_write():
    from app.api import routes_approval
    src = inspect.getsource(routes_approval)
    assert 'require_permission' in src
    assert '"approval:write"' in src or "'approval:write'" in src


def test_posting_route_requires_posting_write():
    from app.api import routes_posting
    src = inspect.getsource(routes_posting)
    assert 'require_permission' in src
    assert '"posting:write"' in src or "'posting:write'" in src


def test_dry_run_route_requires_posting_write():
    from app.api import routes_posting
    src = inspect.getsource(routes_posting.dry_run_balance)
    assert "posting:write" in src


# ---------------------------------------------------------------------------
# Structural: CFO dual-approval threshold is enforced
# ---------------------------------------------------------------------------

def test_approve_service_enforces_cfo_threshold():
    from app.api.services import approval_service
    src = inspect.getsource(approval_service.approve_draft_service)
    assert "awaiting_cfo" in src, "approve_draft_service must enforce CFO dual-approval threshold"
    assert "DUAL_APPROVAL_THRESHOLD" in src or "cfo_threshold" in src.lower()


def test_approve_service_uses_for_update_nowait():
    """Race condition protection: SELECT must use FOR UPDATE NOWAIT."""
    from app.api.services import approval_service
    src = inspect.getsource(approval_service.approve_draft_service)
    assert "FOR UPDATE NOWAIT" in src


# ---------------------------------------------------------------------------
# Structural: audit trail on approval
# ---------------------------------------------------------------------------

def test_approve_service_emits_audit_event():
    from app.api.services import approval_service
    src = inspect.getsource(approval_service.approve_draft_service)
    assert "log_event" in src or "audit" in src.lower(), (
        "approve_draft_service must emit an audit event on approval"
    )


def test_approve_service_records_approved_by_mode():
    from app.api.services import approval_service
    src = inspect.getsource(approval_service.approve_draft_service)
    assert "approved_by_mode" in src, (
        "approved_by_mode must be set to track human vs auto approvals"
    )


# ---------------------------------------------------------------------------
# Full sequence: drafted → only 'approved' enables live posting
# ---------------------------------------------------------------------------

def test_all_non_approved_statuses_are_rejected():
    """Exhaustive check: every status except 'approved' must fail validation."""
    from app.api.services.posting_service import _validate_approved_draft
    blocked = [
        "drafted", "pending_approval", "auto_approved", "pending_human_review",
        "awaiting_cfo", "rejected", "posted", "simulated_success", "cancelled",
        "failed", "",
    ]
    for status in blocked:
        draft = _make_draft(status=status)
        result = _validate_approved_draft(draft, 1, "t1")
        assert result is not None, (
            f"status='{status}' must be rejected by _validate_approved_draft"
        )
        assert result["error"]["code"] == "DRAFT_NOT_APPROVED", (
            f"status='{status}' must return DRAFT_NOT_APPROVED, got {result['error']['code']}"
        )
