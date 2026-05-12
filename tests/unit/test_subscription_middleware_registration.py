"""
tests/unit/test_subscription_middleware_registration.py

Phase E4: Structural tests verifying that subscription_middleware is correctly
registered in main.py and that the registration satisfies safety constraints.

Rules:
  - No DB, no network, no production secrets.
  - Tests are static/structural: inspect source text and module attributes.
  - Do not import main.py at module level — it triggers DB connections.
"""
from __future__ import annotations

import os
import re

import pytest

os.environ.setdefault("TEST_MODE", "1")

MAIN_PY = os.path.join(os.path.dirname(__file__), "..", "..", "main.py")
MIDDLEWARE_PY = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "app", "api", "middleware", "subscription_middleware.py",
)


def _read(path: str) -> str:
    with open(os.path.abspath(path), encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# A) Registration presence and uniqueness in main.py
# ---------------------------------------------------------------------------

class TestRegistrationInMainPy:

    def test_subscription_middleware_imported_in_main(self):
        src = _read(MAIN_PY)
        assert "from app.api.middleware.subscription_middleware import subscription_middleware" in src

    def test_subscription_middleware_registered_exactly_once(self):
        src = _read(MAIN_PY)
        registrations = re.findall(
            r'app\.middleware\("http"\)\(subscription_middleware\)', src
        )
        assert len(registrations) == 1, (
            f"Expected exactly 1 registration, found {len(registrations)}"
        )

    def test_subscription_middleware_import_exactly_once(self):
        src = _read(MAIN_PY)
        imports = re.findall(r'import subscription_middleware', src)
        assert len(imports) == 1, (
            f"Expected exactly 1 import of subscription_middleware, found {len(imports)}"
        )

    def test_registration_order_subscription_before_rbac(self):
        """subscription_middleware must be registered before rbac_middleware so that
        in execution order (reversed) rbac runs first and can reject 401 before
        subscription checks tenant status."""
        src = _read(MAIN_PY)
        pos_sub = src.find('app.middleware("http")(subscription_middleware)')
        pos_rbac = src.find('app.middleware("http")(rbac_middleware)')
        assert pos_sub != -1, "subscription_middleware registration not found"
        assert pos_rbac != -1, "rbac_middleware registration not found"
        assert pos_sub < pos_rbac, (
            "subscription_middleware must be registered BEFORE rbac_middleware "
            "so it runs AFTER rbac in execution order (Starlette LIFO)"
        )

    def test_registration_order_subscription_after_audit_log(self):
        """subscription_middleware must be registered after audit_log_middleware
        so that it runs before audit_log in execution order."""
        src = _read(MAIN_PY)
        pos_sub = src.find('app.middleware("http")(subscription_middleware)')
        pos_audit = src.find('app.middleware("http")(audit_log_middleware)')
        assert pos_sub > pos_audit, (
            "subscription_middleware must be registered AFTER audit_log_middleware"
        )

    def test_tenant_middleware_registered_after_subscription(self):
        """tenant_middleware must be registered after subscription (later in registration
        = outermost = runs first in execution), ensuring tenant_id is set before
        subscription_middleware checks it."""
        src = _read(MAIN_PY)
        pos_sub = src.find('app.middleware("http")(subscription_middleware)')
        pos_tenant = src.find('app.middleware("http")(tenant_middleware)')
        assert pos_tenant > pos_sub, (
            "tenant_middleware must be registered AFTER subscription_middleware "
            "so tenant runs first in execution order"
        )


# ---------------------------------------------------------------------------
# B) Subscription middleware module — no connector or Balance.ge imports
# ---------------------------------------------------------------------------

class TestSubscriptionMiddlewareModuleSafety:

    def test_no_connector_imports_in_middleware(self):
        src = _read(MIDDLEWARE_PY)
        forbidden = [
            "balance_connector",
            "BalanceConnector",
            "posting_service",
            "approval_service",
            "financial_statements",
        ]
        for term in forbidden:
            assert term not in src, (
                f"subscription_middleware must not import {term!r}"
            )

    def test_no_balance_api_key_in_middleware(self):
        src = _read(MIDDLEWARE_PY)
        assert "BALANCE_API_KEY" not in src
        assert "balance.ge" not in src.lower() or "balance-credentials" in src.lower()

    def test_no_db_call_in_policy_logic(self):
        """The policy functions (evaluate, classify, is_safe) must not import DB modules."""
        src = _read(MIDDLEWARE_PY)
        # DB access is only allowed inside get_tenant_subscription_record
        # which lives in subscription_enforcement_service — not in the middleware itself.
        assert "get_conn" not in src
        assert "get_db" not in src

    def test_middleware_exports_expected_symbols(self):
        from app.api.middleware.subscription_middleware import (
            subscription_middleware,
            _classify_path,
            _is_safe_path,
        )
        assert callable(subscription_middleware)
        assert callable(_classify_path)
        assert callable(_is_safe_path)


# ---------------------------------------------------------------------------
# C) Safe paths are preserved in middleware module
# ---------------------------------------------------------------------------

class TestSafePathsPreserved:

    def test_health_is_safe(self):
        from app.api.middleware.subscription_middleware import _is_safe_path
        assert _is_safe_path("/health") is True

    def test_version_is_safe(self):
        from app.api.middleware.subscription_middleware import _is_safe_path
        assert _is_safe_path("/version") is True

    def test_docs_is_safe(self):
        from app.api.middleware.subscription_middleware import _is_safe_path
        assert _is_safe_path("/docs") is True

    def test_openapi_json_is_safe(self):
        from app.api.middleware.subscription_middleware import _is_safe_path
        assert _is_safe_path("/openapi.json") is True

    def test_static_is_safe(self):
        from app.api.middleware.subscription_middleware import _is_safe_path
        assert _is_safe_path("/static/approval.html") is True
        assert _is_safe_path("/static/reports.html") is True
        assert _is_safe_path("/static/documents.html") is True

    def test_auth_login_is_safe(self):
        from app.api.middleware.subscription_middleware import _is_safe_path
        assert _is_safe_path("/auth/login") is True


# ---------------------------------------------------------------------------
# D) Unauthenticated behavior: subscription error code must not be UNAUTHORIZED
# ---------------------------------------------------------------------------

class TestSubscriptionErrorNotUnauthorized:

    def test_subscription_blocked_error_code_is_not_unauthorized(self):
        """Subscription errors use payment-specific codes — never UNAUTHORIZED."""
        from app.api.services.subscription_enforcement_service import (
            SubscriptionErrorCode,
        )
        valid_codes = {
            SubscriptionErrorCode.SUBSCRIPTION_REQUIRED,
            SubscriptionErrorCode.TENANT_SUSPENDED,
            SubscriptionErrorCode.TENANT_INACTIVE,
            SubscriptionErrorCode.TRIAL_EXPIRED,
            SubscriptionErrorCode.SUBSCRIPTION_EXPIRED,
            SubscriptionErrorCode.TENANT_STATUS_UNKNOWN,
        }
        for code in valid_codes:
            assert code != "UNAUTHORIZED", (
                f"Subscription error code {code!r} must not be UNAUTHORIZED"
            )
            assert code != "FORBIDDEN", (
                f"Subscription error code {code!r} must not be FORBIDDEN"
            )

    def test_error_response_no_secrets(self):
        """build_subscription_error must not include any credential fields."""
        from app.api.services.subscription_enforcement_service import (
            SubscriptionDecision,
            SubscriptionErrorCode,
            SubscriptionStatus,
            build_subscription_error,
        )
        decision = SubscriptionDecision(
            allowed=False,
            status=SubscriptionStatus.SUSPENDED,
            error_code=SubscriptionErrorCode.TENANT_SUSPENDED,
            message="Tenant suspended",
        )
        error = build_subscription_error(decision)
        body_str = str(error)
        for forbidden in ("api_key", "password", "token", "encrypted_value", "raw_secret"):
            assert forbidden not in body_str


# ---------------------------------------------------------------------------
# E) Main.py middleware block — no duplicate registrations of any middleware
# ---------------------------------------------------------------------------

class TestNoDuplicateRegistrations:

    @pytest.mark.parametrize("mw_name", [
        "correlation_middleware",
        "audit_log_middleware",
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
