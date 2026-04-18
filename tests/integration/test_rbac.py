from app.api.authz import ROLE_PERMISSIONS


def _has(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


def test_rbac_viewer_no_write():
    assert _has("viewer", "posting:write") is False


def test_rbac_viewer_read():
    assert _has("viewer", "reports:read") is True


def test_rbac_admin_write():
    assert _has("admin", "posting:write") is True


def test_rbac_accountant_write():
    assert _has("accountant", "posting:write") is True
