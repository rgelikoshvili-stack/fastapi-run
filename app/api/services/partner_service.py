"""app/api/services/partner_service.py — Partner API/SDK + White-label (Phase 7).

Partner API enables white-label resellers and integrators to:
  - Register as a partner (get a scoped API key)
  - Post transactions on behalf of their tenants
  - Configure white-label branding per tenant

Partner records stored in tenant_settings under "partner.*" keys.
Branding stored under "branding.*" keys.
"""
from __future__ import annotations

import hashlib
import os
import secrets
from typing import Any

from app.api.services.tenant_config_service import get_tenant_setting, set_tenant_setting

PARTNER_KEY_PREFIX   = "partner"
BRANDING_KEY_PREFIX  = "branding"

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def _generate_partner_key(partner_name: str) -> str:
    """Generate a stable but unique partner API key."""
    random_part = secrets.token_hex(16)
    name_hash   = hashlib.sha256(partner_name.encode()).hexdigest()[:8]
    return f"pk_{name_hash}_{random_part}"


def mask_partner_key(key: str) -> str:
    """Return only the last 4 characters of a partner key for display."""
    return f"pk_...{key[-4:]}" if len(key) >= 4 else "pk_****"


# ---------------------------------------------------------------------------
# Partner registration
# ---------------------------------------------------------------------------

async def register_partner(
    tenant_id: str,
    partner_name: str,
    contact_email: str,
    registered_by: str,
) -> dict[str, Any]:
    """Register a partner and issue an API key.

    Stores partner info in tenant_settings. Returns the new partner record
    (including the plaintext key — shown only once).
    """
    api_key = _generate_partner_key(partner_name)
    partner_data = {
        "name":           partner_name,
        "contact_email":  contact_email,
        "registered_by":  registered_by,
        "api_key_masked": mask_partner_key(api_key),
        "active":         True,
    }
    await set_tenant_setting(tenant_id, f"{PARTNER_KEY_PREFIX}.profile", partner_data)
    return {**partner_data, "api_key": api_key,
            "warning": "Store this key securely — it will not be shown again."}


async def get_partner_profile(tenant_id: str) -> dict[str, Any] | None:
    """Return the partner profile (without the plaintext key)."""
    return await get_tenant_setting(tenant_id, f"{PARTNER_KEY_PREFIX}.profile", None)


async def deactivate_partner(tenant_id: str) -> bool:
    """Deactivate a partner (disable their API key)."""
    profile = await get_partner_profile(tenant_id)
    if not profile:
        return False
    profile["active"] = False
    await set_tenant_setting(tenant_id, f"{PARTNER_KEY_PREFIX}.profile", profile)
    return True


# ---------------------------------------------------------------------------
# White-label branding
# ---------------------------------------------------------------------------

DEFAULT_BRANDING: dict[str, Any] = {
    "product_name":    "Bridge Hub",
    "logo_url":        "",
    "primary_color":   "#2563eb",
    "accent_color":    "#16a34a",
    "support_email":   "",
    "custom_domain":   "",
    "hide_powered_by": False,
}

BRANDING_FIELDS = set(DEFAULT_BRANDING.keys())


async def get_branding(tenant_id: str) -> dict[str, Any]:
    """Return the tenant's branding settings, merged with defaults."""
    stored = await get_tenant_setting(tenant_id, f"{BRANDING_KEY_PREFIX}.config", {})
    if not isinstance(stored, dict):
        stored = {}
    return {**DEFAULT_BRANDING, **stored}


async def set_branding(
    tenant_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """Upsert branding settings. Only known fields are saved."""
    safe_updates = {k: v for k, v in updates.items() if k in BRANDING_FIELDS}
    if not safe_updates:
        raise ValueError("NO_VALID_FIELDS: no recognised branding fields provided")
    existing = await get_branding(tenant_id)
    merged   = {**existing, **safe_updates}
    await set_tenant_setting(tenant_id, f"{BRANDING_KEY_PREFIX}.config", merged)
    return merged
