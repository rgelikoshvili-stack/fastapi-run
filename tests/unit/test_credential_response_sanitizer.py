"""
tests/unit/test_credential_response_sanitizer.py

Unit tests for CredentialResponseSanitizer (Task 11C-D).
Tests sanitizer behavior: forbidden key removal, safe field preservation,
case-variant handling, nested/list structures, and assertion utilities.

Rules:
  - No runtime DB imports, no network, no production secrets.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("TEST_MODE", "1")

from app.api.services.credential_response_sanitizer import (
    FORBIDDEN_CREDENTIAL_RESPONSE_KEYS,
    assert_no_raw_secret_fields,
    mask_known_secret_value,
    safe_configured_status,
    sanitize_credential_response,
)


# ---------------------------------------------------------------------------
# A) Top-level forbidden key removal
# ---------------------------------------------------------------------------

class TestSanitizeTopLevel:

    def test_removes_api_key(self):
        result = sanitize_credential_response({"api_key": "secret", "configured": True})
        assert "api_key" not in result

    def test_removes_password(self):
        result = sanitize_credential_response({"password": "pw", "configured": False})
        assert "password" not in result

    def test_removes_token(self):
        result = sanitize_credential_response({"token": "tok", "mode": "demo"})
        assert "token" not in result

    def test_removes_access_token(self):
        result = sanitize_credential_response({"access_token": "at", "mode": "demo"})
        assert "access_token" not in result

    def test_removes_refresh_token(self):
        result = sanitize_credential_response({"refresh_token": "rt", "mode": "demo"})
        assert "refresh_token" not in result

    def test_removes_secret(self):
        result = sanitize_credential_response({"secret": "s", "provider": "balance"})
        assert "secret" not in result

    def test_removes_client_secret(self):
        result = sanitize_credential_response({"client_secret": "cs"})
        assert "client_secret" not in result

    def test_removes_encrypted_value(self):
        result = sanitize_credential_response({"encrypted_value": "ev"})
        assert "encrypted_value" not in result

    def test_removes_raw_secret(self):
        result = sanitize_credential_response({"raw_secret": "rs"})
        assert "raw_secret" not in result

    def test_removes_decrypted_value(self):
        result = sanitize_credential_response({"decrypted_value": "dv"})
        assert "decrypted_value" not in result

    def test_removes_private_key(self):
        result = sanitize_credential_response({"private_key": "pk"})
        assert "private_key" not in result

    def test_preserves_configured(self):
        result = sanitize_credential_response({"configured": True, "api_key": "x"})
        assert result.get("configured") is True

    def test_preserves_provider(self):
        result = sanitize_credential_response({"provider": "balance", "secret": "x"})
        assert result["provider"] == "balance"

    def test_preserves_mode(self):
        result = sanitize_credential_response({"mode": "demo", "password": "x"})
        assert result["mode"] == "demo"

    def test_preserves_masked_hint(self):
        result = sanitize_credential_response({"masked_hint": "****1234", "api_key": "x"})
        assert result["masked_hint"] == "****1234"

    def test_preserves_last_test_status(self):
        result = sanitize_credential_response({"last_test_status": "ok", "token": "x"})
        assert result["last_test_status"] == "ok"

    def test_preserves_status_field(self):
        result = sanitize_credential_response({"status": "active", "password": "x"})
        assert result["status"] == "active"

    def test_preserves_company_id(self):
        result = sanitize_credential_response({"company_id": "COMP", "api_key": "x"})
        assert result["company_id"] == "COMP"

    def test_empty_dict_returns_empty(self):
        assert sanitize_credential_response({}) == {}

    def test_non_dict_string_passthrough(self):
        assert sanitize_credential_response("plain") == "plain"

    def test_non_dict_int_passthrough(self):
        assert sanitize_credential_response(42) == 42

    def test_none_passthrough(self):
        assert sanitize_credential_response(None) is None

    def test_returns_new_dict_not_original(self):
        original = {"configured": True, "api_key": "x"}
        result = sanitize_credential_response(original)
        assert result is not original

    def test_secret_value_not_in_result_string(self):
        result = sanitize_credential_response({"api_key": "my-real-secret-key"})
        assert "my-real-secret-key" not in str(result)


# ---------------------------------------------------------------------------
# B) Case variant handling
# ---------------------------------------------------------------------------

class TestSanitizeCaseVariants:

    def test_removes_apiKey_camelcase(self):
        result = sanitize_credential_response({"apiKey": "secret"})
        assert "apiKey" not in result

    def test_removes_apikey_lower(self):
        result = sanitize_credential_response({"apikey": "secret"})
        assert "apikey" not in result

    def test_removes_PASSWORD_upper(self):
        result = sanitize_credential_response({"PASSWORD": "x"})
        assert "PASSWORD" not in result

    def test_removes_access_token_upper(self):
        result = sanitize_credential_response({"ACCESS_TOKEN": "x"})
        assert "ACCESS_TOKEN" not in result

    def test_removes_Encrypted_Value_mixed(self):
        result = sanitize_credential_response({"Encrypted_Value": "x"})
        assert "Encrypted_Value" not in result

    def test_removes_Raw_Secret_mixed(self):
        result = sanitize_credential_response({"Raw_Secret": "x"})
        assert "Raw_Secret" not in result


# ---------------------------------------------------------------------------
# C) Nested and list structures
# ---------------------------------------------------------------------------

class TestSanitizeNested:

    def test_removes_forbidden_in_nested_dict(self):
        data = {"credentials": {"api_key": "secret", "provider": "balance"}}
        result = sanitize_credential_response(data)
        assert "api_key" not in result["credentials"]
        assert result["credentials"]["provider"] == "balance"

    def test_removes_forbidden_in_deeply_nested_dict(self):
        data = {"level1": {"level2": {"api_key": "secret", "mode": "demo"}}}
        result = sanitize_credential_response(data)
        assert "api_key" not in result["level1"]["level2"]
        assert result["level1"]["level2"]["mode"] == "demo"

    def test_removes_forbidden_in_list_of_dicts(self):
        data = [{"api_key": "k1", "provider": "p1"}, {"api_key": "k2", "provider": "p2"}]
        result = sanitize_credential_response(data)
        for item in result:
            assert "api_key" not in item
            assert "provider" in item

    def test_removes_forbidden_in_nested_list(self):
        data = {"items": [{"password": "pw", "username": "u"}]}
        result = sanitize_credential_response(data)
        assert "password" not in result["items"][0]
        assert result["items"][0]["username"] == "u"

    def test_removes_multiple_forbidden_keys(self):
        data = {"api_key": "k", "password": "p", "token": "t", "configured": True}
        result = sanitize_credential_response(data)
        assert "api_key" not in result
        assert "password" not in result
        assert "token" not in result
        assert result["configured"] is True

    def test_handles_mixed_safe_and_forbidden(self):
        data = {
            "provider": "balance",
            "configured": True,
            "mode": "live",
            "api_key": "strip-me",
            "masked_hint": "****1234",
            "encrypted_value": "strip-me-too",
        }
        result = sanitize_credential_response(data)
        assert "api_key" not in result
        assert "encrypted_value" not in result
        assert result["provider"] == "balance"
        assert result["configured"] is True
        assert result["masked_hint"] == "****1234"


# ---------------------------------------------------------------------------
# D) assert_no_raw_secret_fields
# ---------------------------------------------------------------------------

class TestAssertNoRawSecretFields:

    def test_raises_on_api_key(self):
        with pytest.raises(ValueError):
            assert_no_raw_secret_fields({"api_key": "x"})

    def test_raises_on_password(self):
        with pytest.raises(ValueError):
            assert_no_raw_secret_fields({"password": "x"})

    def test_raises_on_encrypted_value(self):
        with pytest.raises(ValueError):
            assert_no_raw_secret_fields({"encrypted_value": "x"})

    def test_raises_on_nested_forbidden(self):
        with pytest.raises(ValueError):
            assert_no_raw_secret_fields({"creds": {"encrypted_value": "x"}})

    def test_raises_on_list_with_forbidden(self):
        with pytest.raises(ValueError):
            assert_no_raw_secret_fields([{"api_key": "x"}])

    def test_does_not_raise_on_safe_dict(self):
        assert_no_raw_secret_fields({"configured": True, "provider": "balance", "mode": "demo"})

    def test_does_not_raise_on_empty_dict(self):
        assert_no_raw_secret_fields({})

    def test_error_message_does_not_include_secret_value(self):
        secret_value = "super-secret-should-not-appear-in-error"
        try:
            assert_no_raw_secret_fields({"api_key": secret_value})
            pytest.fail("Should have raised ValueError")
        except ValueError as exc:
            assert secret_value not in str(exc)

    def test_error_message_includes_key_name(self):
        try:
            assert_no_raw_secret_fields({"password": "x"})
            pytest.fail("Should have raised ValueError")
        except ValueError as exc:
            assert "password" in str(exc)


# ---------------------------------------------------------------------------
# E) mask_known_secret_value
# ---------------------------------------------------------------------------

class TestMaskKnownSecretValue:

    def test_long_secret_shows_last_4(self):
        assert mask_known_secret_value("my-secret-key-abcd") == "****abcd"

    def test_exactly_8_chars_shows_last_4(self):
        assert mask_known_secret_value("12345678") == "****5678"

    def test_short_secret_shows_stars_only(self):
        assert mask_known_secret_value("abc") == "****"

    def test_empty_string_returns_stars(self):
        assert mask_known_secret_value("") == "****"

    def test_result_never_equals_raw(self):
        raw = "super-secret-12345678"
        assert mask_known_secret_value(raw) != raw

    def test_result_starts_with_stars(self):
        assert mask_known_secret_value("any-secret-here").startswith("****")

    def test_seven_chars_returns_stars_only(self):
        assert mask_known_secret_value("1234567") == "****"

    def test_raw_value_not_in_result(self):
        raw = "realkey-abcdefgh"
        result = mask_known_secret_value(raw)
        assert raw not in result


# ---------------------------------------------------------------------------
# F) safe_configured_status
# ---------------------------------------------------------------------------

class TestSafeConfiguredStatus:

    def test_returns_provider_and_configured(self):
        result = safe_configured_status("balance", True)
        assert result["provider"] == "balance"
        assert result["configured"] is True

    def test_mode_defaults_to_live_when_configured(self):
        assert safe_configured_status("balance", True)["mode"] == "live"

    def test_mode_defaults_to_demo_when_not_configured(self):
        assert safe_configured_status("balance", False)["mode"] == "demo"

    def test_mode_can_be_overridden(self):
        result = safe_configured_status("balance", False, mode="not_configured")
        assert result["mode"] == "not_configured"

    def test_masked_hint_included_when_provided(self):
        result = safe_configured_status("balance", True, masked_hint="****1234")
        assert result["masked_hint"] == "****1234"

    def test_masked_hint_absent_when_not_provided(self):
        result = safe_configured_status("balance", True)
        assert "masked_hint" not in result

    def test_last_test_status_included(self):
        result = safe_configured_status("balance", True, last_test_status="ok")
        assert result["last_test_status"] == "ok"

    def test_credential_status_included(self):
        result = safe_configured_status("balance", True, credential_status="active")
        assert result["credential_status"] == "active"

    def test_last_tested_at_included(self):
        result = safe_configured_status("balance", True, last_tested_at="2026-01-01")
        assert result["last_tested_at"] == "2026-01-01"

    def test_no_forbidden_keys_when_configured(self):
        result = safe_configured_status(
            "balance", True, masked_hint="****1234",
            last_test_status="ok", credential_status="active",
        )
        forbidden = {"api_key", "password", "token", "secret", "encrypted_value"}
        for key in forbidden:
            assert key not in result, f"Forbidden key {key!r} found in safe_configured_status result"

    def test_no_forbidden_keys_when_not_configured(self):
        result = safe_configured_status("balance", False)
        forbidden = {"api_key", "password", "token", "secret", "encrypted_value"}
        for key in forbidden:
            assert key not in result


# ---------------------------------------------------------------------------
# G) FORBIDDEN_CREDENTIAL_RESPONSE_KEYS set membership
# ---------------------------------------------------------------------------

class TestForbiddenKeysSet:

    def test_api_key_in_set(self):
        assert "api_key" in FORBIDDEN_CREDENTIAL_RESPONSE_KEYS

    def test_password_in_set(self):
        assert "password" in FORBIDDEN_CREDENTIAL_RESPONSE_KEYS

    def test_token_in_set(self):
        assert "token" in FORBIDDEN_CREDENTIAL_RESPONSE_KEYS

    def test_access_token_in_set(self):
        assert "access_token" in FORBIDDEN_CREDENTIAL_RESPONSE_KEYS

    def test_secret_in_set(self):
        assert "secret" in FORBIDDEN_CREDENTIAL_RESPONSE_KEYS

    def test_client_secret_in_set(self):
        assert "client_secret" in FORBIDDEN_CREDENTIAL_RESPONSE_KEYS

    def test_encrypted_value_in_set(self):
        assert "encrypted_value" in FORBIDDEN_CREDENTIAL_RESPONSE_KEYS

    def test_raw_secret_in_set(self):
        assert "raw_secret" in FORBIDDEN_CREDENTIAL_RESPONSE_KEYS

    def test_decrypted_value_in_set(self):
        assert "decrypted_value" in FORBIDDEN_CREDENTIAL_RESPONSE_KEYS

    def test_private_key_in_set(self):
        assert "private_key" in FORBIDDEN_CREDENTIAL_RESPONSE_KEYS

    def test_set_is_frozenset(self):
        assert isinstance(FORBIDDEN_CREDENTIAL_RESPONSE_KEYS, frozenset)
