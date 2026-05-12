"""
tests/unit/test_rate_limit_middleware_registration.py

Structural tests verifying that rate_limit_middleware is correctly registered
in main.py and satisfies safety constraints.

Rules:
  - No DB, no network, no production secrets.
  - Tests are static: inspect source text and module attributes.
  - Do not import main.py at module level.
"""
from __future__ import annotations

import os
import re

import pytest

os.environ.setdefault("TEST_MODE", "1")

MAIN_PY = os.path.join(os.path.dirname(__file__), "..", "..", "main.py")
MW_PY = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "app", "api", "middleware", "rate_limit_middleware.py",
)


def _read(path: str) -> str:
    with open(os.path.abspath(path), encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# A) Registration presence and uniqueness
# ---------------------------------------------------------------------------

class TestRegistrationInMainPy:

    def test_rate_limit_middleware_imported_in_main(self):
        src = _read(MAIN_PY)
        assert "from app.api.middleware.rate_limit_middleware import rate_limit_middleware" in src

    def test_rate_limit_middleware_registered_exactly_once(self):
        src = _read(MAIN_PY)
        registrations = re.findall(
            r'app\.middleware\("http"\)\(rate_limit_middleware\)', src
        )
        assert len(registrations) == 1, (
            f"Expected exactly 1 registration, found {len(registrations)}"
        )

    def test_rate_limit_middleware_import_exactly_once(self):
        src = _read(MAIN_PY)
        imports = re.findall(r'import rate_limit_middleware', src)
        assert len(imports) == 1


# ---------------------------------------------------------------------------
# B) Execution order: rate_limit runs AFTER subscription
#    (registered BEFORE subscription in Starlette LIFO order)
# ---------------------------------------------------------------------------

class TestRegistrationOrder:

    def test_rate_limit_registered_before_subscription(self):
        """rate_limit_middleware is registered before subscription_middleware in
        main.py so that in Starlette LIFO execution order it runs AFTER
        subscription (subscription rejects blocked tenants first)."""
        src = _read(MAIN_PY)
        pos_rl = src.find('app.middleware("http")(rate_limit_middleware)')
        pos_sub = src.find('app.middleware("http")(subscription_middleware)')
        assert pos_rl != -1, "rate_limit_middleware registration not found"
        assert pos_sub != -1, "subscription_middleware registration not found"
        assert pos_rl < pos_sub, (
            "rate_limit must be registered BEFORE subscription so it runs "
            "AFTER subscription in Starlette LIFO execution order"
        )

    def test_rate_limit_registered_after_audit_log(self):
        src = _read(MAIN_PY)
        pos_rl = src.find('app.middleware("http")(rate_limit_middleware)')
        pos_audit = src.find('app.middleware("http")(audit_log_middleware)')
        assert pos_rl > pos_audit, (
            "rate_limit must be registered AFTER audit_log"
        )

    def test_rbac_registered_after_rate_limit(self):
        """rbac registered after rate_limit → runs BEFORE rate_limit in execution
        → unauthenticated requests get 401 from rbac before rate-limit quota is consumed."""
        src = _read(MAIN_PY)
        pos_rl = src.find('app.middleware("http")(rate_limit_middleware)')
        pos_rbac = src.find('app.middleware("http")(rbac_middleware)')
        assert pos_rbac > pos_rl, (
            "rbac must be registered AFTER rate_limit so rbac executes BEFORE "
            "rate_limit — unauthenticated requests get 401 before consuming quota"
        )

    def test_tenant_middleware_registered_last(self):
        src = _read(MAIN_PY)
        pos_rl = src.find('app.middleware("http")(rate_limit_middleware)')
        pos_tenant = src.find('app.middleware("http")(tenant_middleware)')
        assert pos_tenant > pos_rl, (
            "tenant_middleware must be registered after rate_limit"
        )


# ---------------------------------------------------------------------------
# C) Middleware module safety
# ---------------------------------------------------------------------------

class TestRateLimitMiddlewareModuleSafety:

    def test_no_connector_imports(self):
        src = _read(MW_PY)
        for term in ("balance_connector", "BalanceConnector", "posting_service",
                     "approval_service", "financial_statements"):
            assert term not in src, f"Forbidden import {term!r} in rate_limit_middleware"

    def test_no_db_calls(self):
        src = _read(MW_PY)
        assert "get_conn" not in src
        assert "get_db" not in src

    def test_no_balance_api_key(self):
        src = _read(MW_PY)
        assert "BALANCE_API_KEY" not in src

    def test_middleware_exports_callable(self):
        from app.api.middleware.rate_limit_middleware import rate_limit_middleware
        assert callable(rate_limit_middleware)

    def test_safe_path_check_exported(self):
        from app.api.middleware.rate_limit_middleware import _is_always_safe
        assert callable(_is_always_safe)


# ---------------------------------------------------------------------------
# D) Safe paths preserved
# ---------------------------------------------------------------------------

class TestSafePathsPreserved:

    @pytest.mark.parametrize("path", [
        "/health", "/version", "/docs", "/openapi.json",
        "/static/approval.html", "/redoc", "/metrics",
    ])
    def test_safe_path_is_always_safe(self, path):
        from app.api.middleware.rate_limit_middleware import _is_always_safe
        assert _is_always_safe(path) is True

    def test_posting_apply_not_always_safe(self):
        from app.api.middleware.rate_limit_middleware import _is_always_safe
        assert _is_always_safe("/posting/apply/1") is False

    def test_auth_login_not_always_safe(self):
        from app.api.middleware.rate_limit_middleware import _is_always_safe
        assert _is_always_safe("/auth/login") is False


# ---------------------------------------------------------------------------
# E) No duplicate registrations
# ---------------------------------------------------------------------------

class TestNoDuplicateRegistrations:

    @pytest.mark.parametrize("mw_name", [
        "correlation_middleware",
        "audit_log_middleware",
        "rate_limit_middleware",
        "subscription_middleware",
        "rbac_middleware",
        "auth_middleware",
        "tenant_middleware",
    ])
    def test_no_duplicate_middleware_registration(self, mw_name):
        src = _read(MAIN_PY)
        pattern = rf'app\.middleware\("http"\)\({re.escape(mw_name)}\)'
        registrations = re.findall(pattern, src)
        assert len(registrations) == 1, (
            f"{mw_name} registered {len(registrations)} times — expected exactly 1"
        )


# ---------------------------------------------------------------------------
# F) Error response safety
# ---------------------------------------------------------------------------

class TestErrorResponseSafety:

    def test_rate_limit_error_code_not_unauthorized(self):
        from app.api.services.rate_limit_policy_service import (
            RateLimitCategory,
            build_rate_limit_error,
            get_rate_limit_rule,
        )
        rule = get_rate_limit_rule(RateLimitCategory.AUTH)
        err = build_rate_limit_error(rule, 30)
        assert err["error"]["code"] != "UNAUTHORIZED"
        assert err["error"]["code"] != "FORBIDDEN"

    def test_rate_limit_error_no_secrets(self):
        from app.api.services.rate_limit_policy_service import (
            RateLimitCategory,
            build_rate_limit_error,
            get_rate_limit_rule,
        )
        rule = get_rate_limit_rule(RateLimitCategory.CREDENTIAL)
        err = build_rate_limit_error(rule, 60)
        body_str = str(err)
        for forbidden in ("api_key", "password", "token", "encrypted_value"):
            assert forbidden not in body_str
