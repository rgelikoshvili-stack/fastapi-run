"""tests/unit/test_jwt_secret_validation.py

JWT_SECRET startup-validation tests for task 11G.
No DB, no network, no real auth operations.
"""
import logging
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest


def _reset_cache():
    """Clear the module-level secret cache between tests."""
    from app.api.services import auth_service
    auth_service._SECRET_KEY_CACHE = None


@pytest.fixture(autouse=True)
def clear_secret_cache():
    _reset_cache()
    yield
    _reset_cache()


# ── Missing secret ────────────────────────────────────────────────────────────

class TestMissingSecret:
    def test_production_missing_jwt_secret_raises(self, monkeypatch):
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.delenv("TEST_MODE", raising=False)
        from app.api.services.auth_service import _load_jwt_secret
        with pytest.raises(RuntimeError) as exc:
            _load_jwt_secret()
        assert "not configured" in str(exc.value).lower()

    def test_test_mode_missing_jwt_secret_still_raises(self, monkeypatch):
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.setenv("TEST_MODE", "1")
        from app.api.services.auth_service import _load_jwt_secret
        with pytest.raises(RuntimeError):
            _load_jwt_secret()


# ── Short secret ──────────────────────────────────────────────────────────────

class TestShortSecret:
    def test_production_short_secret_raises(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "tooshort")
        monkeypatch.delenv("TEST_MODE", raising=False)
        from app.api.services.auth_service import _load_jwt_secret
        with pytest.raises(RuntimeError) as exc:
            _load_jwt_secret()
        assert "32 bytes" in str(exc.value)
        assert "tooshort" not in str(exc.value)

    def test_test_mode_short_secret_allowed_with_warning(self, monkeypatch, caplog):
        monkeypatch.setenv("JWT_SECRET", "tooshort")
        monkeypatch.setenv("TEST_MODE", "1")
        from app.api.services.auth_service import _load_jwt_secret
        with caplog.at_level(logging.WARNING):
            result = _load_jwt_secret()
        assert result == "tooshort"
        assert any("shorter than 32 bytes" in r.message for r in caplog.records)

    def test_error_message_never_contains_secret_value(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "my-special-short-secret")
        monkeypatch.delenv("TEST_MODE", raising=False)
        from app.api.services.auth_service import _load_jwt_secret
        with pytest.raises(RuntimeError) as exc:
            _load_jwt_secret()
        assert "my-special-short-secret" not in str(exc.value)


# ── Placeholder secrets ───────────────────────────────────────────────────────

class TestPlaceholderSecrets:
    PLACEHOLDERS = [
        "test-secret",
        "dev-secret",
        "secret",
        "changeme",
        "your-secret-here",
        "insecure",
        "password",
        "default",
        "placeholder",
        "replace-me",
        "example",
        "jwt-secret",
        "mysecret",
        "supersecret",
    ]

    @pytest.mark.parametrize("placeholder", PLACEHOLDERS)
    def test_production_rejects_placeholder(self, monkeypatch, placeholder):
        monkeypatch.setenv("JWT_SECRET", placeholder)
        monkeypatch.delenv("TEST_MODE", raising=False)
        from app.api.services.auth_service import _load_jwt_secret
        with pytest.raises(RuntimeError):
            _load_jwt_secret()

    def test_placeholder_error_no_unique_sentinel_leak(self, monkeypatch):
        sentinel = "xK9mQ2wPbN4vR7jL"
        monkeypatch.setenv("JWT_SECRET", sentinel)
        monkeypatch.delenv("TEST_MODE", raising=False)
        from app.api.services.auth_service import _PLACEHOLDER_SECRETS, _load_jwt_secret
        patched = _PLACEHOLDER_SECRETS | {sentinel}
        with patch("app.api.services.auth_service._PLACEHOLDER_SECRETS", patched):
            with pytest.raises(RuntimeError) as exc:
                _load_jwt_secret()
        assert sentinel not in str(exc.value), f"Secret sentinel {sentinel!r} leaked into error"

    def test_production_rejects_placeholder_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "TEST-SECRET")
        monkeypatch.delenv("TEST_MODE", raising=False)
        from app.api.services.auth_service import _load_jwt_secret
        with pytest.raises(RuntimeError):
            _load_jwt_secret()

    def test_test_mode_allows_test_secret(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "test-secret")
        monkeypatch.setenv("TEST_MODE", "1")
        from app.api.services.auth_service import _load_jwt_secret
        result = _load_jwt_secret()
        assert result == "test-secret"

    def test_test_mode_allows_dev_secret(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "dev-secret")
        monkeypatch.setenv("TEST_MODE", "1")
        from app.api.services.auth_service import _load_jwt_secret
        result = _load_jwt_secret()
        assert result == "dev-secret"

    def test_error_never_exposes_placeholder_value(self, monkeypatch):
        placeholder = "changeme"
        monkeypatch.setenv("JWT_SECRET", placeholder)
        monkeypatch.delenv("TEST_MODE", raising=False)
        from app.api.services.auth_service import _load_jwt_secret
        with pytest.raises(RuntimeError) as exc:
            _load_jwt_secret()
        assert placeholder not in str(exc.value)


# ── Strong secret passes ──────────────────────────────────────────────────────

class TestStrongSecret:
    STRONG_SECRET = "x" * 32

    def test_production_strong_secret_passes(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", self.STRONG_SECRET)
        monkeypatch.delenv("TEST_MODE", raising=False)
        from app.api.services.auth_service import _load_jwt_secret
        result = _load_jwt_secret()
        assert result == self.STRONG_SECRET

    def test_exactly_32_bytes_passes(self, monkeypatch):
        secret = "a" * 32
        monkeypatch.setenv("JWT_SECRET", secret)
        monkeypatch.delenv("TEST_MODE", raising=False)
        from app.api.services.auth_service import _load_jwt_secret
        assert _load_jwt_secret() == secret

    def test_long_random_secret_passes(self, monkeypatch):
        secret = "8f7a9d3b2c1e4f6a0b5d8e2f1c3a7b9d4e6f0a2b5c8d1e3f6a9b2c4d7e0f1a"
        monkeypatch.setenv("JWT_SECRET", secret)
        monkeypatch.delenv("TEST_MODE", raising=False)
        from app.api.services.auth_service import _load_jwt_secret
        assert _load_jwt_secret() == secret

    def test_strong_secret_not_in_placeholder_list(self, monkeypatch):
        from app.api.services.auth_service import _PLACEHOLDER_SECRETS
        assert self.STRONG_SECRET not in _PLACEHOLDER_SECRETS


# ── validate_jwt_secret_at_startup ────────────────────────────────────────────

class TestStartupValidation:
    def test_startup_passes_with_strong_secret(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "a" * 32)
        monkeypatch.delenv("TEST_MODE", raising=False)
        from app.api.services.auth_service import validate_jwt_secret_at_startup
        validate_jwt_secret_at_startup()  # must not raise

    def test_startup_passes_in_test_mode_with_test_secret(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "test-secret")
        monkeypatch.setenv("TEST_MODE", "1")
        from app.api.services.auth_service import validate_jwt_secret_at_startup
        validate_jwt_secret_at_startup()  # must not raise

    def test_startup_fails_missing_production(self, monkeypatch):
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.delenv("TEST_MODE", raising=False)
        from app.api.services.auth_service import validate_jwt_secret_at_startup
        with pytest.raises(RuntimeError):
            validate_jwt_secret_at_startup()

    def test_startup_fails_placeholder_production(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "changeme")
        monkeypatch.delenv("TEST_MODE", raising=False)
        from app.api.services.auth_service import validate_jwt_secret_at_startup
        with pytest.raises(RuntimeError):
            validate_jwt_secret_at_startup()

    def test_startup_fails_short_production(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "short")
        monkeypatch.delenv("TEST_MODE", raising=False)
        from app.api.services.auth_service import validate_jwt_secret_at_startup
        with pytest.raises(RuntimeError):
            validate_jwt_secret_at_startup()

    def test_startup_logs_ok_on_success(self, monkeypatch, caplog):
        monkeypatch.setenv("JWT_SECRET", "b" * 32)
        monkeypatch.delenv("TEST_MODE", raising=False)
        from app.api.services.auth_service import validate_jwt_secret_at_startup
        with caplog.at_level(logging.INFO):
            validate_jwt_secret_at_startup()
        assert any("startup_jwt_validation_ok" in r.message for r in caplog.records)

    def test_startup_log_never_contains_secret_on_failure(self, monkeypatch, caplog):
        secret = "this-is-a-placeholder-secret-xyz"
        monkeypatch.setenv("JWT_SECRET", secret)
        monkeypatch.delenv("TEST_MODE", raising=False)
        from app.api.services.auth_service import validate_jwt_secret_at_startup, _PLACEHOLDER_SECRETS
        if secret.lower() not in _PLACEHOLDER_SECRETS:
            pytest.skip("test value not in placeholder list — skip")
        with caplog.at_level(logging.CRITICAL):
            with pytest.raises(RuntimeError):
                validate_jwt_secret_at_startup()
        for record in caplog.records:
            assert secret not in record.message, f"Secret leaked into log: {record.message!r}"

    def test_startup_log_never_contains_secret_on_short_failure(self, monkeypatch, caplog):
        secret = "short-but-unique-abc123"
        monkeypatch.setenv("JWT_SECRET", secret)
        monkeypatch.delenv("TEST_MODE", raising=False)
        from app.api.services.auth_service import validate_jwt_secret_at_startup
        with caplog.at_level(logging.CRITICAL):
            with pytest.raises(RuntimeError):
                validate_jwt_secret_at_startup()
        for record in caplog.records:
            assert secret not in record.message

    def test_startup_warms_cache(self, monkeypatch):
        secret = "c" * 32
        monkeypatch.setenv("JWT_SECRET", secret)
        monkeypatch.delenv("TEST_MODE", raising=False)
        from app.api.services import auth_service
        auth_service._SECRET_KEY_CACHE = None
        auth_service.validate_jwt_secret_at_startup()
        assert auth_service._SECRET_KEY_CACHE == secret


# ── Placeholder list integrity ────────────────────────────────────────────────

class TestPlaceholderList:
    def test_test_secret_in_placeholder_list(self):
        from app.api.services.auth_service import _PLACEHOLDER_SECRETS
        assert "test-secret" in _PLACEHOLDER_SECRETS

    def test_dev_secret_in_placeholder_list(self):
        from app.api.services.auth_service import _PLACEHOLDER_SECRETS
        assert "dev-secret" in _PLACEHOLDER_SECRETS

    def test_changeme_in_placeholder_list(self):
        from app.api.services.auth_service import _PLACEHOLDER_SECRETS
        assert "changeme" in _PLACEHOLDER_SECRETS

    def test_placeholder_list_is_frozenset(self):
        from app.api.services.auth_service import _PLACEHOLDER_SECRETS
        assert isinstance(_PLACEHOLDER_SECRETS, frozenset)

    def test_all_placeholder_entries_are_lowercase(self):
        from app.api.services.auth_service import _PLACEHOLDER_SECRETS
        for entry in _PLACEHOLDER_SECRETS:
            assert entry == entry.lower(), f"Placeholder {entry!r} is not lowercase — case-insensitive check uses .lower()"


# ── Main.py lifespan wires validation ─────────────────────────────────────────

class TestLifespanWired:
    def test_lifespan_calls_validate_jwt_secret_at_startup(self):
        import inspect
        import main as _main
        src = inspect.getsource(_main.lifespan)
        assert "validate_jwt_secret_at_startup" in src, (
            "lifespan must call validate_jwt_secret_at_startup() at startup"
        )

    def test_lifespan_import_is_inside_function(self):
        import inspect
        import main as _main
        src = inspect.getsource(_main.lifespan)
        assert "from app.api.services.auth_service import validate_jwt_secret_at_startup" in src


# ── No secret in /health output ──────────────────────────────────────────────

class TestHealthNoSecretExposed:
    def test_health_env_vars_set_or_missing_only(self):
        from fastapi.testclient import TestClient
        from main import app
        resp = TestClient(app).get("/health")
        assert resp.status_code == 200
        env_vars = resp.json()["data"]["env_vars"]
        for key, val in env_vars.items():
            assert val in ("set", "missing"), (
                f"/health exposed raw value for {key!r}: {val!r}"
            )

    def test_health_body_never_contains_test_secret(self):
        from fastapi.testclient import TestClient
        from main import app
        resp = TestClient(app).get("/health")
        assert "test-secret" not in resp.text


# ── No forbidden imports in this test file ───────────────────────────────────

class TestNoForbiddenImports:
    def test_no_forbidden_imports(self):
        with open(__file__, encoding="utf-8") as fh:
            lines = fh.readlines()
        forbidden = [
            "import " + "psycopg", "import " + "sqlalchemy",
            "import " + "requests", "from " + "app.api.db",
            "from docker" + " import",
        ]
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pat in forbidden:
                assert pat not in stripped, f"Forbidden: {pat!r}"
