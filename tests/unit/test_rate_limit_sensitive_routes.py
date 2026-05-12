"""
tests/unit/test_rate_limit_sensitive_routes.py

Parametrized coverage confirming that every sensitive endpoint category
is rate-limited, safe paths pass without quota, and blocked responses
are correctly structured.

Rules:
  - No real Redis, no DB, no network.
  - Limiter patched via mock to force blocked results.
  - Middleware called directly.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("TEST_MODE", "1")

from app.api.middleware.rate_limit_middleware import rate_limit_middleware
from app.api.services.rate_limit_policy_service import (
    RateLimitCategory,
    classify_rate_limit_category,
    is_rate_limited_category,
)
from app.api.services.rate_limiter_service import (
    RateLimitResult,
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
    def __init__(self, tenant_id="t1", user_id="u1"):
        self.tenant_id = tenant_id
        self.user_id = user_id


class _MockRequest:
    def __init__(self, path, method="GET", tenant_id="t1", user_id="u1"):
        self.url = _MockURL(path)
        self.method = method
        self.state = _MockState(tenant_id, user_id)
        self.client = _MockClient()
        self.headers = {}


async def _ok_call_next(request: Any):
    from fastapi.responses import JSONResponse
    return JSONResponse({"ok": True}, status_code=200)


def _blocked_result(error_code="RATE_LIMIT_EXCEEDED") -> RateLimitResult:
    return RateLimitResult(
        allowed=False, remaining=0, limit=10,
        retry_after_seconds=30, reset_at=time.time() + 30,
        backend="memory_fallback", error_code=error_code,
    )


def _allowed_result() -> RateLimitResult:
    return RateLimitResult(
        allowed=True, remaining=9, limit=10,
        retry_after_seconds=0, reset_at=time.time() + 60,
        backend="memory_fallback",
    )


# ---------------------------------------------------------------------------
# A) Category classification for sensitive paths
# ---------------------------------------------------------------------------

SENSITIVE_PATHS = [
    ("/auth/login", "POST", RateLimitCategory.AUTH),
    ("/auth/register", "POST", RateLimitCategory.AUTH),
    ("/auth/refresh", "POST", RateLimitCategory.AUTH),
    ("/balance-credentials/save", "POST", RateLimitCategory.CREDENTIAL),
    ("/balance-credentials/test", "POST", RateLimitCategory.CREDENTIAL),
    ("/rsge-credentials/save", "POST", RateLimitCategory.CREDENTIAL),
    ("/rsge-credentials/test", "POST", RateLimitCategory.CREDENTIAL),
    ("/posting/apply/1", "POST", RateLimitCategory.POSTING),
    ("/posting/balance/1", "POST", RateLimitCategory.POSTING),
    ("/posting/onec/1", "POST", RateLimitCategory.POSTING),
    ("/erp/import", "POST", RateLimitCategory.CONNECTOR),
    ("/erp-connectors/execute", "POST", RateLimitCategory.CONNECTOR),
    ("/ai-journal/classify", "POST", RateLimitCategory.AI_HEAVY),
    ("/ai-chat/message", "POST", RateLimitCategory.AI_HEAVY),
    ("/ocr/extract", "POST", RateLimitCategory.AI_HEAVY),
    ("/documents/upload", "POST", RateLimitCategory.DOCUMENT_UPLOAD),
    ("/bank-csv/import", "POST", RateLimitCategory.DOCUMENT_UPLOAD),
]


class TestSensitiveCategoryClassification:

    @pytest.mark.parametrize("path,method,expected", SENSITIVE_PATHS)
    def test_classify_path(self, path, method, expected):
        assert classify_rate_limit_category(path, method) == expected

    @pytest.mark.parametrize("path,method,expected", SENSITIVE_PATHS)
    def test_category_is_rate_limited(self, path, method, expected):
        assert is_rate_limited_category(expected) is True


# ---------------------------------------------------------------------------
# B) Blocked sensitive paths return 429 (patched limiter)
# ---------------------------------------------------------------------------

class TestSensitivePathsBlocked:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path,method,cat", SENSITIVE_PATHS)
    async def test_blocked_returns_429(self, path, method, cat):
        from app.api.services.rate_limit_policy_service import (
            _CATEGORY_ERROR_CODE,
        )
        error_code = _CATEGORY_ERROR_CODE.get(cat, "RATE_LIMIT_EXCEEDED")
        mock_svc = MagicMock()
        mock_svc.check_limit.return_value = _blocked_result(error_code)

        with patch(
            "app.api.middleware.rate_limit_middleware.get_rate_limiter_service",
            return_value=mock_svc,
        ):
            req = _MockRequest(path, method)
            resp = await rate_limit_middleware(req, _ok_call_next)

        assert resp.status_code == 429, (
            f"{method} {path} must return 429 when blocked"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path,method,cat", SENSITIVE_PATHS)
    async def test_blocked_has_ok_false(self, path, method, cat):
        mock_svc = MagicMock()
        mock_svc.check_limit.return_value = _blocked_result()

        with patch(
            "app.api.middleware.rate_limit_middleware.get_rate_limiter_service",
            return_value=mock_svc,
        ):
            req = _MockRequest(path, method)
            resp = await rate_limit_middleware(req, _ok_call_next)

        body = json.loads(resp.body)
        assert body["ok"] is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path,method,cat", SENSITIVE_PATHS)
    async def test_blocked_no_secrets_in_response(self, path, method, cat):
        mock_svc = MagicMock()
        mock_svc.check_limit.return_value = _blocked_result()

        with patch(
            "app.api.middleware.rate_limit_middleware.get_rate_limiter_service",
            return_value=mock_svc,
        ):
            req = _MockRequest(path, method)
            resp = await rate_limit_middleware(req, _ok_call_next)

        body_str = resp.body.decode()
        for forbidden in ("api_key", "password", "token", "encrypted_value"):
            assert forbidden not in body_str


# ---------------------------------------------------------------------------
# C) Sensitive paths ALLOWED when limiter says allowed
# ---------------------------------------------------------------------------

class TestSensitivePathsAllowedWhenUnderLimit:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path,method,cat", SENSITIVE_PATHS)
    async def test_allowed_returns_200(self, path, method, cat):
        mock_svc = MagicMock()
        mock_svc.check_limit.return_value = _allowed_result()

        with patch(
            "app.api.middleware.rate_limit_middleware.get_rate_limiter_service",
            return_value=mock_svc,
        ):
            req = _MockRequest(path, method)
            resp = await rate_limit_middleware(req, _ok_call_next)

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# D) Safe paths — limiter NEVER called
# ---------------------------------------------------------------------------

SAFE_PATHS = [
    "/health",
    "/health/deep",
    "/version",
    "/docs",
    "/openapi.json",
    "/static/approval.html",
    "/static/reports.html",
    "/static/documents.html",
    "/redoc",
    "/metrics",
]


class TestSafePathsNeverCallLimiter:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", SAFE_PATHS)
    async def test_safe_path_does_not_call_limiter(self, path):
        with patch(
            "app.api.middleware.rate_limit_middleware.get_rate_limiter_service"
        ) as mock_factory:
            req = _MockRequest(path, "GET")
            resp = await rate_limit_middleware(req, _ok_call_next)
        assert resp.status_code == 200
        mock_factory.assert_not_called()

    @pytest.mark.parametrize("path", SAFE_PATHS)
    def test_safe_path_classified_safe(self, path):
        cat = classify_rate_limit_category(path, "GET")
        assert cat == RateLimitCategory.SAFE


# ---------------------------------------------------------------------------
# E) No connector call from rate-limit layer
# ---------------------------------------------------------------------------

class TestNoConnectorFromRateLimit:

    @pytest.mark.asyncio
    async def test_posting_apply_blocked_does_not_call_connector(self):
        """Even when posting path is blocked by rate-limit, connector is never called."""
        mock_svc = MagicMock()
        mock_svc.check_limit.return_value = _blocked_result("CONNECTOR_RATE_LIMIT_EXCEEDED")

        connector_called = []

        async def _trap_call_next(request):
            connector_called.append(True)
            from fastapi.responses import JSONResponse
            return JSONResponse({"ok": True}, status_code=200)

        with patch(
            "app.api.middleware.rate_limit_middleware.get_rate_limiter_service",
            return_value=mock_svc,
        ):
            req = _MockRequest("/posting/apply/1", "POST")
            await rate_limit_middleware(req, _trap_call_next)

        assert not connector_called, "call_next must not be called when request is rate-limited"


# ---------------------------------------------------------------------------
# F) Balance.ge not activated
# ---------------------------------------------------------------------------

class TestBalanceGeNotActivated:

    def test_no_balance_api_key_in_env(self):
        key = os.environ.get("BALANCE_API_KEY", "")
        assert not key, "BALANCE_API_KEY must not be set in test environment"

    def test_rate_limit_middleware_does_not_import_balance_connector(self):
        import ast
        import pathlib
        src = pathlib.Path("app/api/middleware/rate_limit_middleware.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "balance" not in node.module.lower() or "credentials" in node.module.lower()
