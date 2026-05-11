"""app/api/services/secret_crypto_provider.py
Bridge Hub — Credential Vault Crypto Provider (Task 11C-C2)

Provides AES-256-GCM encryption/decryption for credential vault secrets.
Uses a deterministic test key in TEST_MODE=1. Production key must come
from an approved secret store (e.g. GCP Secret Manager) — never hardcoded.

Public API:
    SecretCryptoProvider
        .encrypt_secret(raw_value, key_version=None) -> dict
        .decrypt_secret(encrypted_value, key_version) -> str
        .mask_secret(raw_value) -> str
        .validate_encrypted_payload(payload) -> bool
"""
from __future__ import annotations

import base64
import logging
import os
import secrets
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

_TEST_MODE_KEY_VERSION = "test-v1"
_TEST_MODE_KEY = b"test-key-32bytes-for-unit-tests!"  # 32 bytes — TEST_MODE only
_CURRENT_KEY_VERSION = "v1"  # default prod version label

# GCM nonce size: 12 bytes recommended per NIST SP 800-38D
_NONCE_BYTES = 12


def _get_key(key_version: str) -> bytes:
    """Return the raw encryption key for the given version.

    In TEST_MODE=1, always returns the deterministic test key.
    In production, reads from an environment variable or secret store.
    Raw key is never logged or returned to callers.
    """
    if os.environ.get("TEST_MODE") == "1":
        return _TEST_MODE_KEY

    # Production path: read from env (Cloud Run injects from Secret Manager).
    raw = os.environ.get(f"VAULT_ENCRYPTION_KEY_{key_version.upper()}", "")
    if not raw:
        # Fallback to generic key env var for single-key setups.
        raw = os.environ.get("VAULT_ENCRYPTION_KEY", "")
    if not raw:
        raise ValueError(
            f"Vault encryption key not configured for version {key_version!r}. "
            "Set VAULT_ENCRYPTION_KEY environment variable."
        )
    key_bytes = base64.b64decode(raw)
    if len(key_bytes) not in (16, 24, 32):
        raise ValueError("Vault encryption key must be 16, 24, or 32 bytes (AES-128/192/256).")
    return key_bytes


# ---------------------------------------------------------------------------
# SecretCryptoProvider
# ---------------------------------------------------------------------------

class SecretCryptoProvider:
    """Encrypts and decrypts credential secrets using AES-256-GCM.

    Caller contract:
      - Never log, print, or return raw_value from encrypt_secret.
      - decrypt_secret returns the raw secret in memory; caller must not
        persist, log, or include it in any response body.
      - Use TEST_MODE=1 only in unit tests; never in production/staging.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def encrypt_secret(
        self,
        raw_value: str,
        key_version: Optional[str] = None,
    ) -> dict:
        """Encrypt a raw secret value.

        Returns a dict with:
          - encrypted_value: str  — base64(nonce + ciphertext)
          - key_version: str      — version of the key used
          - masked_hint: str      — safe display hint

        Raises ValueError for empty raw_value.
        The raw_value is never stored or logged.
        """
        if not raw_value:
            raise ValueError("raw_value must not be empty")

        version = key_version or (
            _TEST_MODE_KEY_VERSION
            if os.environ.get("TEST_MODE") == "1"
            else _CURRENT_KEY_VERSION
        )
        key = _get_key(version)
        nonce = secrets.token_bytes(_NONCE_BYTES)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, raw_value.encode("utf-8"), None)
        blob = base64.b64encode(nonce + ciphertext).decode("ascii")

        return {
            "encrypted_value": blob,
            "key_version": version,
            "masked_hint": self.mask_secret(raw_value),
        }

    def decrypt_secret(self, encrypted_value: str, key_version: str) -> str:
        """Decrypt an encrypted value.

        Returns the raw secret in memory only.
        Caller must not log, store, or return this value in any response.

        Raises:
          ValueError  — empty/malformed inputs
          RuntimeError — decryption failure (wrong key, tampered ciphertext)
        """
        if not encrypted_value or not key_version:
            raise ValueError("encrypted_value and key_version must not be empty")
        try:
            key = _get_key(key_version)
            blob = base64.b64decode(encrypted_value)
            if len(blob) <= _NONCE_BYTES:
                raise ValueError("Encrypted payload too short")
            nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext.decode("utf-8")
        except (ValueError, KeyError):
            raise
        except Exception as exc:
            # Log a sanitized error without any credential data
            log.warning("decrypt_secret failed for key_version=%s: %s", key_version, type(exc).__name__)
            raise RuntimeError("Credential decryption failed") from exc

    def mask_secret(self, raw_value: str) -> str:
        """Derive a safe masked hint from a raw secret.

        Format: '****' + last 4 characters.
        If the secret is shorter than 8 characters, returns '****' only.
        The raw_value is not stored or logged.
        """
        if not raw_value or len(raw_value) < 8:
            return "****"
        return "****" + raw_value[-4:]

    def validate_encrypted_payload(self, payload: dict) -> bool:
        """Return True if a payload dict has the required non-empty vault fields.

        Does NOT attempt decryption. Safe to call on untrusted input.
        """
        if not isinstance(payload, dict):
            return False
        for field in ("encrypted_value", "key_version"):
            val = payload.get(field)
            if not val or not isinstance(val, str):
                return False
        return True
