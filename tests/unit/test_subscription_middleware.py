"""
tests/unit/test_subscription_middleware.py

Unit tests for subscription enforcement middleware (Task 11C-E2).
Tests middleware allow/block logic using mock requests and mocked tenant lookup.

Rules:
  - No real DB, no network, no production secrets.
  - tenant lookup is mocked via patch.
  - Middleware is called directly (not registered in FastAPI).
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

NOW = datetime(2026, 5, 12, 12, 0, 0, tzinfo=timezone.utc)
FUTURE = NOW + timedelta(days=30)
PAST = NOW - timedelta(days=1)

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

ACTIVE_RECORD = {"status": "active", "is_active": True, "plan": "PRO"}
SUSPENDED_RECORD = {"status": "suspended", "is_active": True}
EXPIRED_RECORD = {"status": "expired", "is_active": True}
TRIAL_VALID = {"status": "trial", "is_active": True, "trial_ends_at": FUTURE}
TRIAL_EXPIRED = {"status": "trial", "is_active": True, "trial_ends_at": PAST}
INACTIVE_RECORD = {"status": "inactive", "is_active": False}


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
# A) Safe path passthrough — no DB lookup
# ---------------------------------------------------------------------------

class TestSafePathPassthrough:

    @pytest.mark.asyncio
    async def test_health_allowed_for_suspended(self):
        with _mock_tenant(SUSPENDED_RECORD) as mock_lookup:
            req = _MockRequest("/health", "GET")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200
        mock_lookup.assert_not_called()

    @pytest.mark.asyncio
    async def test_version_allowed_for_suspended(self):
        with _mock_tenant(SUSPENDED_RECORD) as mock_lookup:
            req = _MockRequest("/version", "GET")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200
        mock_lookup.assert_not_called()

    @pytest.mark.asyncio
    async def test_static_allowed_for_suspended(self):
        with _mock_tenant(SUSPENDED_RECORD) as mock_lookup:
            req = _MockRequest("/static/approval.html", "GET")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200
        mock_lookup.assert_not_called()

    @pytest.mark.asyncio
    async def test_docs_allowed_for_inactive(self):
        with _mock_tenant(INACTIVE_RECORD) as mock_lookup:
            req = _MockRequest("/docs", "GET")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200
        mock_lookup.assert_not_called()

    @pytest.mark.asyncio
    async def test_auth_login_allowed_for_expired(self):
        with _mock_tenant(EXPIRED_RECORD) as mock_lookup:
            req = _MockRequest("/auth/login", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200
        mock_lookup.assert_not_called()

    @pytest.mark.asyncio
    async def test_health_deep_allowed(self):
        with _mock_tenant(SUSPENDED_RECORD) as mock_lookup:
            req = _MockRequest("/health/deep", "GET")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200
        mock_lookup.assert_not_called()


# ---------------------------------------------------------------------------
# B) Read-safe paths — allowed without DB lookup
# ---------------------------------------------------------------------------

class TestReadSafePassthrough:

    @pytest.mark.asyncio
    async def test_balance_credentials_status_allowed(self):
        with _mock_tenant(SUSPENDED_RECORD) as mock_lookup:
            req = _MockRequest("/balance-credentials/status", "GET")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200
        mock_lookup.assert_not_called()

    @pytest.mark.asyncio
    async def test_posting_balance_status_allowed(self):
        with _mock_tenant(SUSPENDED_RECORD) as mock_lookup:
            req = _MockRequest("/posting/balance-status", "GET")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200
        mock_lookup.assert_not_called()

    @pytest.mark.asyncio
    async def test_approval_queue_get_allowed(self):
        with _mock_tenant(SUSPENDED_RECORD) as mock_lookup:
            req = _MockRequest("/approval/queue", "GET")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200
        mock_lookup.assert_not_called()

    @pytest.mark.asyncio
    async def test_reports_read_allowed(self):
        with _mock_tenant(EXPIRED_RECORD) as mock_lookup:
            req = _MockRequest("/reports/trial-balance", "GET")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200
        mock_lookup.assert_not_called()


# ---------------------------------------------------------------------------
# C) Sensitive paths blocked for suspended tenant
# ---------------------------------------------------------------------------

class TestSuspendedTenantBlocked:

    @pytest.mark.asyncio
    async def test_posting_apply_blocked(self):
        with _mock_tenant(SUSPENDED_RECORD):
            req = _MockRequest("/posting/apply/5", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402

    @pytest.mark.asyncio
    async def test_posting_balance_blocked(self):
        with _mock_tenant(SUSPENDED_RECORD):
            req = _MockRequest("/posting/balance/5", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402

    @pytest.mark.asyncio
    async def test_approval_approve_blocked(self):
        with _mock_tenant(SUSPENDED_RECORD):
            req = _MockRequest("/approval/approve/5", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402

    @pytest.mark.asyncio
    async def test_balance_credentials_save_blocked(self):
        with _mock_tenant(SUSPENDED_RECORD):
            req = _MockRequest("/balance-credentials/save", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402

    @pytest.mark.asyncio
    async def test_documents_upload_blocked(self):
        with _mock_tenant(SUSPENDED_RECORD):
            req = _MockRequest("/documents/upload", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402

    @pytest.mark.asyncio
    async def test_erp_import_blocked(self):
        with _mock_tenant(SUSPENDED_RECORD):
            req = _MockRequest("/erp/import", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402


# ---------------------------------------------------------------------------
# D) Sensitive paths blocked for expired trial tenant
# ---------------------------------------------------------------------------

class TestExpiredTrialBlocked:

    @pytest.mark.asyncio
    async def test_posting_blocked_for_expired_trial(self):
        with _mock_tenant(TRIAL_EXPIRED):
            req = _MockRequest("/posting/apply/3", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402

    @pytest.mark.asyncio
    async def test_approval_mutation_blocked_for_expired_trial(self):
        with _mock_tenant(TRIAL_EXPIRED):
            req = _MockRequest("/approval/approve/3", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402

    @pytest.mark.asyncio
    async def test_credential_save_blocked_for_expired_trial(self):
        with _mock_tenant(TRIAL_EXPIRED):
            req = _MockRequest("/balance-credentials/save", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402

    @pytest.mark.asyncio
    async def test_document_upload_blocked_for_expired_trial(self):
        with _mock_tenant(TRIAL_EXPIRED):
            req = _MockRequest("/documents/upload", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402


# ---------------------------------------------------------------------------
# E) Active tenant — all paths allowed
# ---------------------------------------------------------------------------

class TestActiveTenantAllowed:

    @pytest.mark.asyncio
    async def test_active_posting_allowed(self):
        with _mock_tenant(ACTIVE_RECORD):
            req = _MockRequest("/posting/apply/5", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_active_approval_allowed(self):
        with _mock_tenant(ACTIVE_RECORD):
            req = _MockRequest("/approval/approve/5", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_active_credentials_save_allowed(self):
        with _mock_tenant(ACTIVE_RECORD):
            req = _MockRequest("/balance-credentials/save", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_active_document_upload_allowed(self):
        with _mock_tenant(ACTIVE_RECORD):
            req = _MockRequest("/documents/upload", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# F) Valid trial tenant
# ---------------------------------------------------------------------------

class TestValidTrialTenant:

    @pytest.mark.asyncio
    async def test_valid_trial_approval_allowed(self):
        with _mock_tenant(TRIAL_VALID):
            req = _MockRequest("/approval/approve/5", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_valid_trial_posting_blocked(self):
        with _mock_tenant(TRIAL_VALID):
            req = _MockRequest("/posting/apply/5", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402

    @pytest.mark.asyncio
    async def test_valid_trial_connector_execute_blocked(self):
        with _mock_tenant(TRIAL_VALID):
            req = _MockRequest("/posting/balance/5", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402


# ---------------------------------------------------------------------------
# G) Missing/unknown tenant
# ---------------------------------------------------------------------------

class TestMissingTenant:

    @pytest.mark.asyncio
    async def test_none_tenant_blocks_sensitive(self):
        with _mock_tenant(None):
            req = _MockRequest("/posting/apply/5", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 402

    @pytest.mark.asyncio
    async def test_none_tenant_allows_health(self):
        with _mock_tenant(None) as mock_lookup:
            req = _MockRequest("/health", "GET")
            resp = await subscription_middleware(req, _ok_call_next)
        assert resp.status_code == 200
        mock_lookup.assert_not_called()


# ---------------------------------------------------------------------------
# H) Error response format
# ---------------------------------------------------------------------------

class TestErrorResponseFormat:

    @pytest.mark.asyncio
    async def test_error_response_has_ok_false(self):
        import json
        with _mock_tenant(SUSPENDED_RECORD):
            req = _MockRequest("/posting/apply/5", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        body = json.loads(resp.body)
        assert body["ok"] is False

    @pytest.mark.asyncio
    async def test_error_response_has_error_code(self):
        import json
        with _mock_tenant(SUSPENDED_RECORD):
            req = _MockRequest("/posting/apply/5", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        body = json.loads(resp.body)
        assert "code" in body["error"]
        assert body["error"]["code"] == "TENANT_SUSPENDED"

    @pytest.mark.asyncio
    async def test_error_response_no_secrets(self):
        import json
        with _mock_tenant(SUSPENDED_RECORD):
            req = _MockRequest("/posting/apply/5", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        body_str = resp.body.decode()
        for forbidden in ("api_key", "password", "encrypted_value", "token"):
            assert forbidden not in body_str

    @pytest.mark.asyncio
    async def test_error_response_data_is_null(self):
        import json
        with _mock_tenant(EXPIRED_RECORD):
            req = _MockRequest("/approval/approve/5", "POST")
            resp = await subscription_middleware(req, _ok_call_next)
        body = json.loads(resp.body)
        assert body["data"] is None


# ---------------------------------------------------------------------------
# I) _classify_path unit tests
# ---------------------------------------------------------------------------

class TestClassifyPath:

    def test_posting_apply_post_is_posting_execute(self):
        assert _classify_path("/posting/apply/5", "POST") == ActionCategory.POSTING_EXECUTE

    def test_posting_balance_status_is_read_safe(self):
        assert _classify_path("/posting/balance-status", "GET") == ActionCategory.READ_SAFE

    def test_posting_onec_status_is_read_safe(self):
        assert _classify_path("/posting/onec-status", "GET") == ActionCategory.READ_SAFE

    def test_posting_oris_status_is_read_safe(self):
        assert _classify_path("/posting/oris-status", "GET") == ActionCategory.READ_SAFE

    def test_approval_queue_get_is_read_safe(self):
        assert _classify_path("/approval/queue", "GET") == ActionCategory.READ_SAFE

    def test_approval_approve_post_is_approval_mutation(self):
        assert _classify_path("/approval/approve/5", "POST") == ActionCategory.APPROVAL_MUTATION

    def test_balance_credentials_save_is_credential_write(self):
        assert _classify_path("/balance-credentials/save", "POST") == ActionCategory.CREDENTIAL_WRITE

    def test_balance_credentials_test_is_credential_write(self):
        assert _classify_path("/balance-credentials/test", "POST") == ActionCategory.CREDENTIAL_WRITE

    def test_balance_credentials_status_is_read_safe(self):
        assert _classify_path("/balance-credentials/status", "GET") == ActionCategory.READ_SAFE

    def test_documents_upload_is_document_upload(self):
        assert _classify_path("/documents/upload", "POST") == ActionCategory.DOCUMENT_UPLOAD

    def test_erp_import_is_admin_mutation(self):
        assert _classify_path("/erp/import", "POST") == ActionCategory.ADMIN_MUTATION

    def test_reports_read_is_read_safe(self):
        assert _classify_path("/reports/trial-balance", "GET") == ActionCategory.READ_SAFE

    def test_posting_balance_slash_post_is_posting_execute(self):
        assert _classify_path("/posting/balance/5", "POST") == ActionCategory.POSTING_EXECUTE

    def test_posting_logs_get_is_read_safe(self):
        assert _classify_path("/posting/logs", "GET") == ActionCategory.READ_SAFE


# ---------------------------------------------------------------------------
# J) _is_safe_path unit tests
# ---------------------------------------------------------------------------

class TestIsSafePath:

    def test_health_is_safe(self):
        assert _is_safe_path("/health") is True

    def test_version_is_safe(self):
        assert _is_safe_path("/version") is True

    def test_static_is_safe(self):
        assert _is_safe_path("/static/approval.html") is True

    def test_docs_is_safe(self):
        assert _is_safe_path("/docs") is True

    def test_auth_login_is_safe(self):
        assert _is_safe_path("/auth/login") is True

    def test_posting_apply_is_not_safe(self):
        assert _is_safe_path("/posting/apply/5") is False

    def test_approval_approve_is_not_safe(self):
        assert _is_safe_path("/approval/approve/5") is False

    def test_balance_credentials_save_is_not_safe(self):
        assert _is_safe_path("/balance-credentials/save") is False
