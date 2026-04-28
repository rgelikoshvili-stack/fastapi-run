# Legacy shim — delegates to app/api/authz.py (Source of Truth).
# This file is kept only for backward compatibility.
# Do NOT add new permissions here. Use app/api/authz.py instead.
from app.api.authz import (
    ROLE_PERMISSIONS,
    has_role_permission,
    require_permission,
    require_auth,
)

__all__ = ["ROLE_PERMISSIONS", "has_role_permission", "require_permission", "require_auth"]
