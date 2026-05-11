"""
tests/unit/test_secret_crypto_provider.py

Unit tests for SecretCryptoProvider (Task 11C-C2).
Tests verify encryption/decryption roundtrip, masking, and safety invariants.

Rules:
  - TEST_MODE=1 is set in conftest / environment; uses deterministic test key.
  - No DB, no network, no production secrets.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("TEST_MODE", "1")

from app.api.services.secret_crypto_provider import SecretCryptoProvider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def crypto():
    return SecretCryptoProvider()


TEST_SECRET = "my-super-secret-api-key-12345678"
SHORT_SECRET = "abc"


# ---------------------------------------------------------------------------
# A) Encryption / decryption roundtrip
# ---------------------------------------------------------------------------

class TestEncryptDecryptRoundtrip:

    def test_roundtrip_returns_original(self, crypto):
        payload = crypto.encrypt_secret(TEST_SECRET)
        result = crypto.decrypt_secret(payload["encrypted_value"], payload["key_version"])
        assert result == TEST_SECRET

    def test_encrypted_value_differs_from_raw(self, crypto):
        payload = crypto.encrypt_secret(TEST_SECRET)
        assert payload["encrypted_value"] != TEST_SECRET

    def test_two_encryptions_produce_different_ciphertext(self, crypto):
        p1 = crypto.encrypt_secret(TEST_SECRET)
        p2 = crypto.encrypt_secret(TEST_SECRET)
        assert p1["encrypted_value"] != p2["encrypted_value"]

    def test_key_version_included_in_payload(self, crypto):
        payload = crypto.encrypt_secret(TEST_SECRET)
        assert "key_version" in payload
        assert payload["key_version"]

    def test_masked_hint_included_in_payload(self, crypto):
        payload = crypto.encrypt_secret(TEST_SECRET)
        assert "masked_hint" in payload
        assert payload["masked_hint"]

    def test_roundtrip_with_explicit_key_version(self, crypto):
        payload = crypto.encrypt_secret(TEST_SECRET, key_version="test-v1")
        result = crypto.decrypt_secret(payload["encrypted_value"], "test-v1")
        assert result == TEST_SECRET

    def test_unicode_roundtrip(self, crypto):
        unicode_secret = "სეკრეტული-key-unicode-12345678"
        payload = crypto.encrypt_secret(unicode_secret)
        result = crypto.decrypt_secret(payload["encrypted_value"], payload["key_version"])
        assert result == unicode_secret

    def test_long_secret_roundtrip(self, crypto):
        long_secret = "x" * 256
        payload = crypto.encrypt_secret(long_secret)
        result = crypto.decrypt_secret(payload["encrypted_value"], payload["key_version"])
        assert result == long_secret


# ---------------------------------------------------------------------------
# B) Masking behavior
# ---------------------------------------------------------------------------

class TestMaskSecret:

    def test_mask_returns_four_star_prefix(self, crypto):
        result = crypto.mask_secret(TEST_SECRET)
        assert result.startswith("****")

    def test_mask_appends_last_4_chars(self, crypto):
        result = crypto.mask_secret("my-test-secret-abcd")
        assert result == "****abcd"

    def test_mask_short_secret_returns_four_stars_only(self, crypto):
        result = crypto.mask_secret(SHORT_SECRET)
        assert result == "****"

    def test_mask_exactly_8_chars_returns_last_4(self, crypto):
        result = crypto.mask_secret("12345678")
        assert result == "****5678"

    def test_mask_never_equals_raw(self, crypto):
        result = crypto.mask_secret(TEST_SECRET)
        assert result != TEST_SECRET

    def test_mask_empty_returns_four_stars(self, crypto):
        result = crypto.mask_secret("")
        assert result == "****"

    def test_masked_hint_in_encrypt_matches_mask_secret(self, crypto):
        payload = crypto.encrypt_secret(TEST_SECRET)
        assert payload["masked_hint"] == crypto.mask_secret(TEST_SECRET)


# ---------------------------------------------------------------------------
# C) Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:

    def test_empty_raw_value_raises(self, crypto):
        with pytest.raises(ValueError):
            crypto.encrypt_secret("")

    def test_none_like_raw_value_raises(self, crypto):
        with pytest.raises((ValueError, TypeError)):
            crypto.encrypt_secret(None)  # type: ignore

    def test_empty_encrypted_value_raises(self, crypto):
        with pytest.raises((ValueError, RuntimeError)):
            crypto.decrypt_secret("", "test-v1")

    def test_empty_key_version_raises(self, crypto):
        with pytest.raises((ValueError, RuntimeError)):
            crypto.decrypt_secret("somedata", "")

    def test_invalid_ciphertext_raises(self, crypto):
        with pytest.raises((ValueError, RuntimeError)):
            crypto.decrypt_secret("not-valid-base64!!!", "test-v1")

    def test_truncated_ciphertext_raises(self, crypto):
        import base64
        tiny = base64.b64encode(b"tooshort").decode()
        with pytest.raises((ValueError, RuntimeError)):
            crypto.decrypt_secret(tiny, "test-v1")

    def test_tampered_ciphertext_raises(self, crypto):
        import base64
        payload = crypto.encrypt_secret(TEST_SECRET)
        raw = base64.b64decode(payload["encrypted_value"])
        # Flip a byte in the ciphertext portion
        tampered = raw[:12] + bytes([raw[12] ^ 0xFF]) + raw[13:]
        tampered_b64 = base64.b64encode(tampered).decode()
        with pytest.raises((ValueError, RuntimeError)):
            crypto.decrypt_secret(tampered_b64, payload["key_version"])


# ---------------------------------------------------------------------------
# D) Validate encrypted payload
# ---------------------------------------------------------------------------

class TestValidatePayload:

    def test_valid_payload_returns_true(self, crypto):
        payload = crypto.encrypt_secret(TEST_SECRET)
        assert crypto.validate_encrypted_payload(payload) is True

    def test_missing_encrypted_value_returns_false(self, crypto):
        assert crypto.validate_encrypted_payload({"key_version": "v1"}) is False

    def test_missing_key_version_returns_false(self, crypto):
        assert crypto.validate_encrypted_payload({"encrypted_value": "abc"}) is False

    def test_empty_encrypted_value_returns_false(self, crypto):
        assert crypto.validate_encrypted_payload({"encrypted_value": "", "key_version": "v1"}) is False

    def test_empty_key_version_returns_false(self, crypto):
        assert crypto.validate_encrypted_payload({"encrypted_value": "abc", "key_version": ""}) is False

    def test_non_dict_returns_false(self, crypto):
        assert crypto.validate_encrypted_payload("not a dict") is False  # type: ignore

    def test_none_returns_false(self, crypto):
        assert crypto.validate_encrypted_payload(None) is False  # type: ignore


# ---------------------------------------------------------------------------
# E) Safety invariants
# ---------------------------------------------------------------------------

class TestSafetyInvariants:

    def test_raw_secret_not_in_payload_dict(self, crypto):
        payload = crypto.encrypt_secret(TEST_SECRET)
        for key, val in payload.items():
            assert TEST_SECRET not in str(val), f"Raw secret leaked into payload[{key!r}]"

    def test_raw_secret_not_in_repr_of_payload(self, crypto):
        payload = crypto.encrypt_secret(TEST_SECRET)
        assert TEST_SECRET not in repr(payload)

    def test_masked_hint_does_not_contain_first_part_of_secret(self, crypto):
        payload = crypto.encrypt_secret("ABCDEFGHIJKLMNOP")
        # The first characters should not appear in the masked hint
        assert "ABCDEFGH" not in payload["masked_hint"]

    def test_encrypt_decrypt_does_not_corrupt_unrelated_data(self, crypto):
        secrets_list = ["alpha-secret-12345678", "beta-secret-87654321", "gamma-secret-ABCDEFGH"]
        payloads = [crypto.encrypt_secret(s) for s in secrets_list]
        for original, payload in zip(secrets_list, payloads):
            decrypted = crypto.decrypt_secret(payload["encrypted_value"], payload["key_version"])
            assert decrypted == original

    def test_test_mode_key_deterministic_across_instances(self):
        c1 = SecretCryptoProvider()
        c2 = SecretCryptoProvider()
        payload = c1.encrypt_secret(TEST_SECRET)
        result = c2.decrypt_secret(payload["encrypted_value"], payload["key_version"])
        assert result == TEST_SECRET
