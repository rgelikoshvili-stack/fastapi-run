"""
tests/unit/test_subscription_sensitive_route_blocks.py

Phase E3: Sensitive route blocking tests for subscription enforcement.
Validates that every sensitive action category is blocked for all
blocking tenant states, and that every always-safe and read-safe category
is allowed regardless of tenant state.

Rules:
  - No real DB, no network, no production secrets.
  - All tenant lookups mocked.
  - Middleware invoked directly (not registered in FastAPI).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("TEST_MODE", "1")

from app.api.middleware.subscription_middleware import (
    _classify_path,
    _is_safe_path,
    subscription_middleware,
)
from app.api.services.subscription_enforcement_service import ActionCategory

NOW = datetime.now(timezone.utc)
FUTURE = NOW + timedelta(days=365)
PAST = NOW - timedelta(days=1)

# ---------------------------------------------------------------------------
# Tenant record fixtures
# ---------------------------------------------------------------------------

ACTIVE = {"status": "active", "is_active": True, "plan": "PRO"}
SUSPENDED = {"status": "suspended", "is_active": True}
EXPIRED = {"status": "expired", "is_active": True}
TRIAL_VALID = {"status": "trial", "is_active": True, "trial_ends_at": FUTURE}
TRIAL_EXPIRED = {"status": "trial", "is_active": True, "trial_ends_at": PAST}
INACTIVE = {"status": "inactive", "is_active": False}

ALL_BLOCKING = [SUSPENDED, EXPIRED, TRIAL_EXPIRED, INACTIVE]


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

class _MockURL:
    def __init__(self, path: str):
        self.path = path


class _MockState:
    def __init__(self, tenant_id: str = "test_tenant"):
        self.tenant_id = tenant_id


class _MockRequest:
    def __init__(self, path: str, method: str = "GET", tenant_id: str = "test_tenant"):
        self.url = _MockURL(path)
        self.method = method
        self.state = _MockState(tenant_id)


async def _ok_call_next(request: Any):
    from fastapi.responses import JSONResponse
    return JSONResponse({"ok": True}, status_code=200)


def _mock_tenant(record):
    return patch(
        "app.api.middleware.subscription_middleware.get_tenant_subscription_record",
        new_callable=AsyncMock,
        return_value=record,
    )


# ---------------------------------------------------------------------------
# A) All sensitive categories blocked for all blocking states
# ---------------------------------------------------------------------------

# (path, method, expected_category)
SENSITIVE_PATHS = [
    ("/posting/apply/1", "POST", ActionCategory.POSTING_EXECUTE),
    ("/posting/balance/1", "POST", ActionCategory.POSTING_EXECUTE),
    ("/posting/onec/1", "POST", ActionCategory.POSTING_EXECUTE),
    ("/posting/oris/1", "POST", ActionCategory.POSTING_EXECUTE),
    ("/posting/mock/1", "POST", ActionCategory.POSTING_EXECUTE),
    ("/approval/approve/1", "POST", ActionCategory.APPROVAL_MUTATION),
    ("/approval/reject/1", "POST", ActionCategory.APPROVAL_MUTATION),
    ("/approval/correct/1", "POST", ActionCategory.APPROVAL_MUTATION),
    ("/balance-credentials/save", "POST", ActionCategory.CREDENTIAL_WRITE),
    ("/balance-credentials/test", "POST", ActionCategory.CREDENTIAL_WRITE),
    ("/documents/upload", "POST", ActionCategory.DOCUMENT_UPLOAD),
    ("/erp/import", "POST", ActionCategory.ADMIN_MUTATION),
    ("/erp/sync", "POST", ActionCategory.ADMIN_MUTATION),
    ("/ocr/process", "POST", ActionCategory.AI_HEAVY),
    ("/ai-journal/classify", "POST", ActionCategory.AI_HEAVY),
    ("/ai-chat/message", "POST", ActionCategory.AI_HEAVY),
]


class TestSensitiveCategoriesClassification:
    """_classify_path must map every sensitive path to the expected category."""

    @pytest.mark.parametrize("path,method,expected", SENSITIVE_PATHS)
    def test_classify_path(self, path, method, expected):
        assert _classify_path(path, method) == expected


class TestSensitiveBlockedForSuspended:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path,method,_cat", SENSITIVE_PATHS)
    async def test_suspended_blocks(self, path, method, _cat):
        with _mock_tenant(SUSPENDED):
            req = _MockRequest(path, method)
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402, f"Expected 402 for {method} {path} (suspended)"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path,method,_cat", SENSITIVE_PATHS)
    async def test_expired_blocks(self, path, method, _cat):
        with _mock_tenant(EXPIRED):
            req = _MockRequest(path, method)
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402, f"Expected 402 for {method} {path} (expired)"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path,method,_cat", SENSITIVE_PATHS)
    async def test_inactive_blocks(self, path, method, _cat):
        with _mock_tenant(INACTIVE):
            req = _MockRequest(path, method)
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402, f"Expected 402 for {method} {path} (inactive)"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path,method,_cat", SENSITIVE_PATHS)
    async def test_trial_expired_blocks(self, path, method, _cat):
        with _mock_tenant(TRIAL_EXPIRED):
            req = _MockRequest(path, method)
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402, f"Expected 402 for {method} {path} (trial_expired)"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path,method,_cat", SENSITIVE_PATHS)
    async def test_none_tenant_blocks(self, path, method, _cat):
        with _mock_tenant(None):
            req = _MockRequest(path, method)
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402, f"Expected 402 for {method} {path} (None tenant)"


# ---------------------------------------------------------------------------
# B) All sensitive categories ALLOWED for active tenant
# ---------------------------------------------------------------------------

class TestSensitiveAllowedForActive:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path,method,_cat", SENSITIVE_PATHS)
    async def test_active_allows(self, path, method, _cat):
        with _mock_tenant(ACTIVE):
            req = _MockRequest(path, method)
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200, f"Expected 200 for {method} {path} (active)"


# ---------------------------------------------------------------------------
# C) Valid trial: posting/connector BLOCKED, approval/credential ALLOWED
# ---------------------------------------------------------------------------

TRIAL_BLOCKED_PATHS = [
    ("/posting/apply/1", "POST"),
    ("/posting/balance/1", "POST"),
    ("/posting/onec/1", "POST"),
    ("/posting/oris/1", "POST"),
    ("/posting/mock/1", "POST"),
]

TRIAL_ALLOWED_PATHS = [
    ("/approval/approve/1", "POST"),
    ("/approval/reject/1", "POST"),
    ("/balance-credentials/save", "POST"),
    ("/balance-credentials/test", "POST"),
    ("/documents/upload", "POST"),
]


class TestValidTrialCategoryRules:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path,method", TRIAL_BLOCKED_PATHS)
    async def test_trial_blocks_posting_execute(self, path, method):
        with _mock_tenant(TRIAL_VALID):
            req = _MockRequest(path, method)
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402, f"Trial must block {method} {path}"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path,method", TRIAL_ALLOWED_PATHS)
    async def test_trial_allows_non_posting(self, path, method):
        with _mock_tenant(TRIAL_VALID):
            req = _MockRequest(path, method)
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200, f"Trial must allow {method} {path}"


# ---------------------------------------------------------------------------
# D) Always-safe paths — no DB lookup, always 200 regardless of tenant state
# ---------------------------------------------------------------------------

ALWAYS_SAFE_PATHS = [
    "/health",
    "/health/deep",
    "/health/ping",
    "/version",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/static/approval.html",
    "/static/logo.png",
    "/auth/login",
    "/auth/register",
    "/auth/refresh",
]


class TestAlwaysSafePathsNoDbLookup:

    @pytest.mark.parametrize("path", ALWAYS_SAFE_PATHS)
    def test_is_safe_path_returns_true(self, path):
        assert _is_safe_path(path) is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", ALWAYS_SAFE_PATHS)
    async def test_safe_path_passes_for_all_blocking_states(self, path):
        for record in ALL_BLOCKING:
            with _mock_tenant(record) as mock_lookup:
                req = _MockRequest(path, "GET")
                resp = await subscription_middleware(req, _ok_call_next)
            assert resp.status_code == 200, f"Safe path {path} must pass for {record['status']}"
            mock_lookup.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", ALWAYS_SAFE_PATHS)
    async def test_safe_path_passes_for_none_tenant(self, path):
        with _mock_tenant(None) as mock_lookup:
            req = _MockRequest(path, "GET")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200
        mock_lookup.assert_not_called()


# ---------------------------------------------------------------------------
# E) Read-safe paths — no DB lookup, always 200
# ---------------------------------------------------------------------------

READ_SAFE_PATHS = [
    ("/posting/balance-status", "GET"),
    ("/posting/onec-status", "GET"),
    ("/posting/oris-status", "GET"),
    ("/posting/logs", "GET"),
    ("/posting/history", "GET"),
    ("/posting/approved-drafts", "GET"),
    ("/approval/queue", "GET"),
    ("/balance-credentials/status", "GET"),
    ("/rsge-credentials/status", "GET"),
    ("/reports/trial-balance", "GET"),
    ("/reports/vat-summary", "GET"),
    ("/posting/logs/123", "GET"),
    ("/posting/history/detail", "GET"),
    ("/posting/payload/5", "GET"),
    ("/posting/preview/5", "GET"),
]


class TestReadSafePathsNoDbLookup:

    @pytest.mark.parametrize("path,method", READ_SAFE_PATHS)
    def test_classify_path_is_read_safe(self, path, method):
        assert _classify_path(path, method) == ActionCategory.READ_SAFE

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path,method", READ_SAFE_PATHS)
    async def test_read_safe_passes_for_all_blocking_states(self, path, method):
        for record in ALL_BLOCKING:
            with _mock_tenant(record) as mock_lookup:
                req = _MockRequest(path, method)
                resp = await subscription_middleware(req, _ok_call_next)
            assert resp.status_code == 200, (
                f"Read-safe path {path} must pass for {record['status']}"
            )
            mock_lookup.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path,method", READ_SAFE_PATHS)
    async def test_read_safe_passes_for_none_tenant(self, path, method):
        with _mock_tenant(None) as mock_lookup:
            req = _MockRequest(path, method)
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200
        mock_lookup.assert_not_called()


# ---------------------------------------------------------------------------
# F) Billing-safe paths — no DB lookup, always 200
# ---------------------------------------------------------------------------

BILLING_SAFE_PATHS = [
    "/subscriptions/status",
    "/subscriptions/upgrade",
    "/billing/invoices",
    "/billing/portal",
]


class TestBillingSafePaths:

    @pytest.mark.parametrize("path", BILLING_SAFE_PATHS)
    def test_classify_is_billing_safe(self, path):
        assert _classify_path(path, "GET") == ActionCategory.BILLING_SAFE

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", BILLING_SAFE_PATHS)
    async def test_billing_safe_passes_for_all_blocking_states(self, path):
        for record in ALL_BLOCKING:
            with _mock_tenant(record) as mock_lookup:
                req = _MockRequest(path, "GET")
                resp = await subscription_middleware(req, _ok_call_next)
            assert resp.status_code == 200, (
                f"Billing path {path} must pass for {record['status']}"
            )
            mock_lookup.assert_not_called()


# ---------------------------------------------------------------------------
# G) Error envelope contract for every blocking state
# ---------------------------------------------------------------------------

import json  # noqa: E402

BLOCKING_RECORDS_AND_CODES = [
    (SUSPENDED, "TENANT_SUSPENDED"),
    (EXPIRED, "SUBSCRIPTION_EXPIRED"),
    (INACTIVE, "TENANT_INACTIVE"),
    (TRIAL_EXPIRED, "TRIAL_EXPIRED"),
    (None, "TENANT_STATUS_UNKNOWN"),
]


class TestErrorEnvelopePerBlockingState:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("record,expected_code", BLOCKING_RECORDS_AND_CODES)
    async def test_error_envelope_structure(self, record, expected_code):
        with _mock_tenant(record):
            req = _MockRequest("/posting/apply/1", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402
        body = json.loads(resp.body)
        assert body["ok"] is False
        assert body["data"] is None
        assert "error" in body
        assert body["error"]["code"] == expected_code, (
            f"Expected code {expected_code} for record={record}, got {body['error']['code']}"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("record,_code", BLOCKING_RECORDS_AND_CODES)
    async def test_error_envelope_no_secrets(self, record, _code):
        with _mock_tenant(record):
            req = _MockRequest("/posting/apply/1", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        body_str = resp.body.decode()
        for forbidden in ("api_key", "password", "token", "encrypted_value", "raw_secret"):
            assert forbidden not in body_str, f"Forbidden field {forbidden!r} leaked in error body"


# ---------------------------------------------------------------------------
# H) GET vs POST method distinction on mutable-capable paths
# ---------------------------------------------------------------------------

class TestMethodDistinction:

    @pytest.mark.asyncio
    async def test_posting_apply_get_is_read_safe_and_passes_for_suspended(self):
        with _mock_tenant(SUSPENDED) as mock_lookup:
            req = _MockRequest("/posting/apply/1", "GET")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200
        mock_lookup.assert_not_called()

    @pytest.mark.asyncio
    async def test_posting_apply_post_blocked_for_suspended(self):
        with _mock_tenant(SUSPENDED):
            req = _MockRequest("/posting/apply/1", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402

    @pytest.mark.asyncio
    async def test_balance_credentials_get_is_read_safe_and_passes_for_suspended(self):
        with _mock_tenant(SUSPENDED) as mock_lookup:
            req = _MockRequest("/balance-credentials/status", "GET")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200
        mock_lookup.assert_not_called()

    @pytest.mark.asyncio
    async def test_approval_queue_get_read_safe_for_suspended(self):
        with _mock_tenant(SUSPENDED) as mock_lookup:
            req = _MockRequest("/approval/queue", "GET")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200
        mock_lookup.assert_not_called()

    @pytest.mark.asyncio
    async def test_approval_approve_post_blocked_for_suspended(self):
        with _mock_tenant(SUSPENDED):
            req = _MockRequest("/approval/approve/1", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402
