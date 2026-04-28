"""app/config/secrets.py — Unified secrets loader.

Priority chain:
  1. os.environ (always wins — allows local overrides and test injection)
  2. Google Secret Manager (production only, when GCP_PROJECT_ID is set)
  3. Raises RuntimeError if required secret is missing

Usage:
    from app.config.secrets import get_secret, require_secret

    db_url = require_secret("DATABASE_URL")          # raises if missing
    api_key = get_secret("OPENROUTER_API_KEY", "")   # default if missing
"""
import logging
import os
from functools import lru_cache
from typing import Optional

log = logging.getLogger(__name__)

_GCP_PROJECT = os.environ.get("GCP_PROJECT_ID", "")
_USE_GSM = bool(_GCP_PROJECT) and os.environ.get("USE_SECRET_MANAGER", "true").lower() == "true"

_gsm_client = None


def _get_gsm_client():
    global _gsm_client
    if _gsm_client is None:
        try:
            from google.cloud import secretmanager
            _gsm_client = secretmanager.SecretManagerServiceClient()
        except ImportError:
            log.warning("google-cloud-secret-manager not installed — GSM disabled")
            _gsm_client = False
    return _gsm_client if _gsm_client is not False else None


@lru_cache(maxsize=128)
def _fetch_from_gsm(secret_id: str) -> Optional[str]:
    """Fetch secret from Google Secret Manager. Cached per process lifetime."""
    client = _get_gsm_client()
    if not client:
        return None
    try:
        name = f"projects/{_GCP_PROJECT}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        value = response.payload.data.decode("utf-8").strip()
        log.info("action=gsm_secret_loaded secret=%s", secret_id)
        return value
    except Exception as e:
        log.warning("action=gsm_secret_miss secret=%s error=%s", secret_id, e)
        return None


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """Get secret value. Returns default if not found anywhere."""
    # 1. Environment variable (highest priority)
    value = os.environ.get(name)
    if value:
        return value

    # 2. Google Secret Manager (production)
    if _USE_GSM:
        gsm_value = _fetch_from_gsm(name)
        if gsm_value:
            # Cache in env so subsequent calls are instant
            os.environ[name] = gsm_value
            return gsm_value

    return default


def require_secret(name: str) -> str:
    """Get secret or raise RuntimeError if not found."""
    value = get_secret(name)
    if not value:
        raise RuntimeError(
            f"Required secret '{name}' is not configured. "
            f"Set it as an environment variable or add it to "
            f"Google Secret Manager (project: {_GCP_PROJECT or 'GCP_PROJECT_ID not set'})."
        )
    return value


def warm_up_secrets():
    """Pre-load critical secrets at startup to fail fast."""
    critical = ["DATABASE_URL", "JWT_SECRET"]
    missing = []
    for name in critical:
        val = get_secret(name)
        if not val:
            missing.append(name)
    if missing:
        raise RuntimeError(f"Missing required secrets at startup: {', '.join(missing)}")
    log.info("action=secrets_warmup ok secrets_loaded=%d", len(critical))
