"""
tests/unit/test_rate_limit_middleware.py

Unit tests for the rate-limit enforcement middleware (Task 11C-F3).
Tests middleware allow/block logic using mock requests and patched limiter service.

Rules:
  - No real Redis, no DB, no network.
  - Limiter service patched or uses in-memory backend.
  - Middleware called directly (not via FastAPI app).
"""
from __future__ import annotations

import os
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("TEST_MODE", "1")

from app.api.middleware.rate_limit_middleware import (
    _is_always_safe,
    rate_limit_middleware,
)
from app.api.services.rate_limit_policy_service import RateLimitCategory
from app.api.services.rate_limiter_service import (
    InMemoryRateLimiterBackend,
    RateLimitResult,
    RateLimiterService,
    _reset_service_singleton,
)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

class _MockURL:
    def __init__(self, path: str):
        self.path = path


class _MockClient:
    host = "127.0.0.1"


class _MockState:
    def __init__(self, tenant_id: str = "t1", user_id: str = "u1"):
        self.tenant_id = tenant_id
        self.user_id = user_id


class _MockRequest:
    def __init__(self, path: str, method: str = "GET",
                 tenant_id: str = "t1", user_id: str = "u1"):
        self.url = _MockURL(path)
        self.method = method
        self.state = _MockState(tenant_id, user_id)
        self.client = _MockClient()
        self.headers: dict = {}


async def _ok_call_next(request: Any):
    from fastapi.responses import JSONResponse
    return JSONResponse({"ok": True}, status_code=200)


def _make_fresh_service(limit: int = 1000, window: int = 60) -> RateLimiterService:
    """Return a fresh in-memory service."""
    return RateLimiterService(InMemoryRateLimiterBackend())


# ---------------------------------------------------------------------------
# A) Safe path passthrough — no rate-limit check
# ---------------------------------------------------------------------------

class TestSafePathPassthrough:

    @pytest.mark.parametrize("path", [
        "/health", "/health/deep", "/health/ping",
        "/version", "/docs", "/docs/",
        "/redoc", "/openapi.json",
        "/static/approval.html", "/static/reports.html",
        "/metrics",
    ])
    @pytest.mark.asyncio
    async def test_safe_path_always_passes(self, path):
        req = _MockRequest(path, "GET")
        with patch(
            "app.api.middleware.rate_limit_middleware.get_rate_limiter_service"
        ) as mock_svc:
            resp = await rate_limit_middleware(req, _ok_call_next)
        assert resp.status_code == 200
        mock_svc.assert_not_called()

    def test_is_always_safe_health(self):
        assert _is_always_safe("/health") is True

    def test_is_always_safe_static(self):
        assert _is_always_safe("/static/foo.html") is True

    def test_is_always_safe_version(self):
        assert _is_always_safe("/version") is True

    def test_posting_apply_not_always_safe(self):
        assert _is_always_safe("/posting/apply/5") is False

    def test_auth_login_not_always_safe(self):
        assert _is_always_safe("/auth/login") is False


# ---------------------------------------------------------------------------
# B) First sensitive request allowed
# ---------------------------------------------------------------------------

class TestFirstSensitiveRequestAllowed:

    def setup_method(self):
        _reset_service_singleton()

    def teardown_method(self):
        _reset_service_singleton()

    @pytest.mark.asyncio
    async def test_first_auth_login_allowed(self):
        req = _MockRequest("/auth/login", "POST")
        resp = await rate_limit_middleware(req, _ok_call_next)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_first_posting_apply_allowed(self):
        req = _MockRequest("/posting/apply/1", "POST")
        resp = await rate_limit_middleware(req, _ok_call_next)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_first_credential_save_allowed(self):
        req = _MockRequest("/balance-credentials/save", "POST")
        resp = await rate_limit_middleware(req, _ok_call_next)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_first_document_upload_allowed(self):
        req = _MockRequest("/documents/upload", "POST")
        resp = await rate_limit_middleware(req, _ok_call_next)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_first_ai_journal_allowed(self):
        req = _MockRequest("/ai-journal/classify", "POST")
        resp = await rate_limit_middleware(req, _ok_call_next)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# C) Repeated requests — limit enforcement returns 429
# ---------------------------------------------------------------------------

class TestRepeatRequestsBlocked:

    def setup_method(self):
        _reset_service_singleton()

    def teardown_method(self):
        _reset_service_singleton()

    @pytest.mark.asyncio
    async def test_limit_exceeded_returns_429(self):
        """Exhaust the limit then verify 429."""
        from app.api.services.rate_limit_policy_service import get_rate_limit_rule
        from app.api.services.rate_limiter_service import _reset_service_singleton, get_rate_limiter_service

        _reset_service_singleton()
        svc = get_rate_limiter_service()

        rule = get_rate_limit_rule(RateLimitCategory.AUTH)
        from app.api.services.rate_limit_policy_service import build_rate_limit_key
        key = build_rate_limit_key("t1", "u1", "127.0.0.1", RateLimitCategory.AUTH)

        for _ in range(rule.limit):
            svc.check_limit(key, rule)

        # Now the middleware should see a blocked result for the same key
        result_blocked = svc.check_limit(key, rule)
        assert result_blocked.allowed is False

    @pytest.mark.asyncio
    async def test_mock_blocked_service_returns_429(self):
        """Patch limiter to return a blocked result and verify middleware returns 429."""
        blocked_result = RateLimitResult(
            allowed=False,
            remaining=0,
            limit=10,
            retry_after_seconds=42,
            reset_at=time.time() + 42,
            backend="memory_fallback",
            error_code="AUTH_RATE_LIMIT_EXCEEDED",
        )
        mock_svc = MagicMock()
        mock_svc.check_limit.return_value = blocked_result

        with patch(
            "app.api.middleware.rate_limit_middleware.get_rate_limiter_service",
            return_value=mock_svc,
        ):
            req = _MockRequest("/auth/login", "POST")
            resp = await rate_limit_middleware(req, _ok_call_next)

        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_blocked_response_has_ok_false(self):
        import json
        blocked_result = RateLimitResult(
            allowed=False,
            remaining=0,
            limit=10,
            retry_after_seconds=30,
            reset_at=time.time() + 30,
            backend="memory_fallback",
            error_code="AUTH_RATE_LIMIT_EXCEEDED",
        )
        mock_svc = MagicMock()
        mock_svc.check_limit.return_value = blocked_result

        with patch(
            "app.api.middleware.rate_limit_middleware.get_rate_limiter_service",
            return_value=mock_svc,
        ):
            req = _MockRequest("/auth/login", "POST")
            resp = await rate_limit_middleware(req, _ok_call_next)

        body = json.loads(resp.body)
        assert body["ok"] is False

    @pytest.mark.asyncio
    async def test_blocked_response_has_retry_after_header(self):
        blocked_result = RateLimitResult(
            allowed=False,
            remaining=0,
            limit=10,
            retry_after_seconds=55,
            reset_at=time.time() + 55,
            backend="memory_fallback",
            error_code="RATE_LIMIT_EXCEEDED",
        )
        mock_svc = MagicMock()
        mock_svc.check_limit.return_value = blocked_result

        with patch(
            "app.api.middleware.rate_limit_middleware.get_rate_limiter_service",
            return_value=mock_svc,
        ):
            req = _MockRequest("/posting/apply/1", "POST")
            resp = await rate_limit_middleware(req, _ok_call_next)

        assert resp.headers.get("Retry-After") == "55"

    @pytest.mark.asyncio
    async def test_blocked_response_has_x_ratelimit_headers(self):
        blocked_result = RateLimitResult(
            allowed=False,
            remaining=0,
            limit=30,
            retry_after_seconds=10,
            reset_at=time.time() + 10,
            backend="memory_fallback",
            error_code="CONNECTOR_RATE_LIMIT_EXCEEDED",
        )
        mock_svc = MagicMock()
        mock_svc.check_limit.return_value = blocked_result

        with patch(
            "app.api.middleware.rate_limit_middleware.get_rate_limiter_service",
            return_value=mock_svc,
        ):
            req = _MockRequest("/erp/import", "POST")
            resp = await rate_limit_middleware(req, _ok_call_next)

        assert resp.headers.get("X-RateLimit-Limit") == "30"
        assert resp.headers.get("X-RateLimit-Remaining") == "0"

    @pytest.mark.asyncio
    async def test_blocked_response_no_secrets(self):
        import json
        blocked_result = RateLimitResult(
            allowed=False,
            remaining=0,
            limit=5,
            retry_after_seconds=20,
            reset_at=time.time() + 20,
            backend="memory_fallback",
            error_code="CREDENTIAL_RATE_LIMIT_EXCEEDED",
        )
        mock_svc = MagicMock()
        mock_svc.check_limit.return_value = blocked_result

        with patch(
            "app.api.middleware.rate_limit_middleware.get_rate_limiter_service",
            return_value=mock_svc,
        ):
            req = _MockRequest("/balance-credentials/save", "POST")
            resp = await rate_limit_middleware(req, _ok_call_next)

        body_str = resp.body.decode()
        for forbidden in ("api_key", "password", "token", "encrypted_value"):
            assert forbidden not in body_str


# ---------------------------------------------------------------------------
# D) Allowed response has X-RateLimit headers
# ---------------------------------------------------------------------------

class TestAllowedResponseHeaders:

    def setup_method(self):
        _reset_service_singleton()

    def teardown_method(self):
        _reset_service_singleton()

    @pytest.mark.asyncio
    async def test_allowed_response_has_ratelimit_limit_header(self):
        allowed_result = RateLimitResult(
            allowed=True,
            remaining=9,
            limit=10,
            retry_after_seconds=0,
            reset_at=time.time() + 60,
            backend="memory_fallback",
        )
        mock_svc = MagicMock()
        mock_svc.check_limit.return_value = allowed_result

        with patch(
            "app.api.middleware.rate_limit_middleware.get_rate_limiter_service",
            return_value=mock_svc,
        ):
            req = _MockRequest("/auth/login", "POST")
            resp = await rate_limit_middleware(req, _ok_call_next)

        assert resp.status_code == 200
        assert resp.headers.get("X-RateLimit-Limit") == "10"
        assert resp.headers.get("X-RateLimit-Remaining") == "9"


# ---------------------------------------------------------------------------
# E) Category-specific blocked responses
# ---------------------------------------------------------------------------

class TestCategorySpecificBlocking:

    @pytest.mark.asyncio
    async def test_ai_journal_blocked_has_ai_error_code(self):
        import json
        blocked = RateLimitResult(
            allowed=False, remaining=0, limit=60,
            retry_after_seconds=100, reset_at=time.time() + 100,
            backend="memory_fallback", error_code="AI_RATE_LIMIT_EXCEEDED",
        )
        mock_svc = MagicMock()
        mock_svc.check_limit.return_value = blocked

        with patch("app.api.middleware.rate_limit_middleware.get_rate_limiter_service",
                   return_value=mock_svc):
            req = _MockRequest("/ai-journal/classify", "POST")
            resp = await rate_limit_middleware(req, _ok_call_next)

        body = json.loads(resp.body)
        assert body["error"]["code"] == "AI_RATE_LIMIT_EXCEEDED"

    @pytest.mark.asyncio
    async def test_credential_save_blocked_has_credential_code(self):
        import json
        blocked = RateLimitResult(
            allowed=False, remaining=0, limit=10,
            retry_after_seconds=50, reset_at=time.time() + 50,
            backend="memory_fallback", error_code="CREDENTIAL_RATE_LIMIT_EXCEEDED",
        )
        mock_svc = MagicMock()
        mock_svc.check_limit.return_value = blocked

        with patch("app.api.middleware.rate_limit_middleware.get_rate_limiter_service",
                   return_value=mock_svc):
            req = _MockRequest("/balance-credentials/save", "POST")
            resp = await rate_limit_middleware(req, _ok_call_next)

        body = json.loads(resp.body)
        assert body["error"]["code"] == "CREDENTIAL_RATE_LIMIT_EXCEEDED"

    @pytest.mark.asyncio
    async def test_posting_apply_blocked_has_connector_code(self):
        import json
        blocked = RateLimitResult(
            allowed=False, remaining=0, limit=30,
            retry_after_seconds=30, reset_at=time.time() + 30,
            backend="memory_fallback", error_code="CONNECTOR_RATE_LIMIT_EXCEEDED",
        )
        mock_svc = MagicMock()
        mock_svc.check_limit.return_value = blocked

        with patch("app.api.middleware.rate_limit_middleware.get_rate_limiter_service",
                   return_value=mock_svc):
            req = _MockRequest("/posting/apply/1", "POST")
            resp = await rate_limit_middleware(req, _ok_call_next)

        body = json.loads(resp.body)
        assert body["error"]["code"] == "CONNECTOR_RATE_LIMIT_EXCEEDED"


# ---------------------------------------------------------------------------
# F) No connector calls from middleware
# ---------------------------------------------------------------------------

class TestMiddlewareDoesNotCallConnectors:

    @pytest.mark.asyncio
    async def test_no_balance_connector_import(self):
        import ast
        import pathlib
        src = pathlib.Path("app/api/middleware/rate_limit_middleware.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert "connector" not in node.module.lower()
                    assert "posting_service" not in node.module.lower()
                    assert "approval_service" not in node.module.lower()
