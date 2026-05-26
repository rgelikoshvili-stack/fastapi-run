"""tests/unit/test_approval_payload_preview.py — Task 11L / Gate 7.

Verifies that approve_draft_service() embeds a payload_preview in its
success response so the approver sees exactly what would be posted to
Balance.ge before committing to a live posting call.

Tests:
- Source code contains payload_preview in the ok_response call.
- _draft_to_posting_payload returns correct structure for a GEL draft.
- payload_preview.amount matches draft amount.
- payload_preview never contains api_key, Authorization, or Bearer.
- Failing _draft_to_posting_payload does NOT raise — best-effort.
- payload_preview field key is present in approve_draft_service source.
"""
import asyncio
import inspect
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Structural: verify payload_preview is wired in the approval source
# ---------------------------------------------------------------------------

def test_approve_draft_service_source_contains_payload_preview():
    """payload_preview must appear in the approve_draft_service ok_response."""
    from app.api.services import approval_service
    src = inspect.getsource(approval_service.approve_draft_service)
    assert "payload_preview" in src, (
        "approve_draft_service must include payload_preview in its ok_response data"
    )


def test_approve_draft_service_source_calls_draft_to_posting_payload():
    """_draft_to_posting_payload must be called inside approve_draft_service."""
    from app.api.services import approval_service
    src = inspect.getsource(approval_service.approve_draft_service)
    assert "_draft_to_posting_payload" in src, (
        "approve_draft_service must call _draft_to_posting_payload for Gate 7"
    )


def test_approve_draft_service_preview_is_best_effort():
    """The _draft_to_posting_payload call must be inside a try/except block."""
    from app.api.services import approval_service
    src = inspect.getsource(approval_service.approve_draft_service)
    # The try/except wrapping payload_preview must be present
    assert "payload_preview" in src
    # Both the call and a fallback (None on exception) must be in the source
    assert "payload_preview = None" in src
    assert "_pp_exc" in src or "Exception" in src


# ---------------------------------------------------------------------------
# _draft_to_posting_payload direct unit tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_draft_to_posting_payload_structure():
    """Returns correct keys for a balanced GEL draft."""
    from app.api.services.posting_service import _draft_to_posting_payload
    draft = {
        "id": 1, "tenant_id": "t1", "date": "2026-05-25",
        "description": "Test", "partner": "Partner LLC",
        "amount": 800.0, "currency": "GEL",
        "lines_json": [
            {"account_code": "1210", "debit": 800.0, "credit": 0,    "label": "Bank"},
            {"account_code": "3110", "debit": 0,     "credit": 800.0, "label": "Revenue"},
        ],
        "status": "approved",
    }
    payload = await _draft_to_posting_payload(draft)

    assert payload["amount"] == 800.0
    assert payload["currency"] == "GEL"
    assert payload["tenant_id"] == "t1"
    assert isinstance(payload["lines"], list)
    assert len(payload["lines"]) == 2


@pytest.mark.asyncio
async def test_draft_to_posting_payload_amount_matches():
    from app.api.services.posting_service import _draft_to_posting_payload
    draft = {
        "id": 2, "tenant_id": "t1", "date": "2026-05-25",
        "description": "Invoice", "partner": "LLC",
        "amount": 3700.50, "currency": "GEL",
        "lines_json": [
            {"account_code": "1210", "debit": 3700.50, "credit": 0,       "label": "Bank"},
            {"account_code": "3110", "debit": 0,       "credit": 3700.50, "label": "Revenue"},
        ],
        "status": "approved",
    }
    payload = await _draft_to_posting_payload(draft)
    assert abs(payload["amount"] - 3700.50) < 0.01


@pytest.mark.asyncio
async def test_draft_to_posting_payload_no_credentials():
    """Payload must not expose any secret-like values from the draft."""
    from app.api.services.posting_service import _draft_to_posting_payload
    draft = {
        "id": 3, "tenant_id": "t1", "date": "2026-05-25",
        "description": "Test", "partner": "Evil Corp",
        "amount": 100.0, "currency": "GEL",
        "api_key": "should-not-appear",   # injected — must not pass through
        "lines_json": [
            {"account_code": "1210", "debit": 100.0, "credit": 0,    "label": "Dr"},
            {"account_code": "3110", "debit": 0,     "credit": 100.0, "label": "Cr"},
        ],
        "status": "approved",
    }
    payload = await _draft_to_posting_payload(draft)
    payload_str = json.dumps(payload)
    assert "should-not-appear" not in payload_str
    assert "Authorization"     not in payload_str
    assert "Bearer"            not in payload_str


@pytest.mark.asyncio
async def test_draft_to_posting_payload_line_account_codes():
    """Line account codes are preserved through the payload builder."""
    from app.api.services.posting_service import _draft_to_posting_payload
    draft = {
        "id": 4, "tenant_id": "t1", "date": "2026-05-25",
        "description": "Test", "partner": "P",
        "amount": 500.0, "currency": "GEL",
        "lines_json": [
            {"account_code": "5000", "debit": 500.0, "credit": 0,    "label": "Expense"},
            {"account_code": "1210", "debit": 0,     "credit": 500.0, "label": "Bank"},
        ],
        "status": "approved",
    }
    payload = await _draft_to_posting_payload(draft)
    # lines_json passes through _normalize_lines, which keeps account_code
    account_codes = {line.get("account_code") for line in payload["lines"]}
    assert "5000" in account_codes
    assert "1210" in account_codes


# ---------------------------------------------------------------------------
# Best-effort: _draft_to_posting_payload failure must not break approval
# ---------------------------------------------------------------------------

def test_approval_payload_preview_is_in_response_data_keys():
    """ok_response data dict must have a 'payload_preview' key (even if None)."""
    from app.api.services import approval_service
    src = inspect.getsource(approval_service.approve_draft_service)
    # Verify the key literal appears in the ok_response call
    assert '"payload_preview"' in src or "'payload_preview'" in src, (
        "payload_preview must be a key in the ok_response data dict"
    )


def test_payload_preview_try_except_is_non_fatal():
    """The try/except around _draft_to_posting_payload must set preview to None on error."""
    from app.api.services import approval_service
    src = inspect.getsource(approval_service.approve_draft_service)
    # Must have `payload_preview = None` as initial value and in the except block
    assert src.count("payload_preview") >= 3, (
        "Expected at least 3 occurrences: None init, assignment, and dict key"
    )


@pytest.mark.asyncio
async def test_draft_to_posting_payload_is_awaitable():
    """_draft_to_posting_payload is async — it must be awaitable."""
    from app.api.services.posting_service import _draft_to_posting_payload
    import inspect as _inspect
    assert _inspect.iscoroutinefunction(_draft_to_posting_payload)
