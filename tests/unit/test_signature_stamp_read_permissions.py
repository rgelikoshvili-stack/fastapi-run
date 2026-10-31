"""Regression tests: tenant signature/stamp read requires an authorized role.

No production credentials, database connections, or network calls are used.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from app.api.db import authenticated_tenant_context


def _request(*, authenticated: bool, role: str | None, tenant_id: str = "t_alpha"):
    return SimpleNamespace(state=SimpleNamespace(
        authenticated=authenticated, role=role, tenant_id=tenant_id,
        auth_tenant_id=tenant_id,
    ))


@pytest.mark.parametrize("handler_name", ["get_signature", "get_stamp"])
@pytest.mark.parametrize("authenticated,role,status", [
    (False, None, 401),
    (True, "viewer", 403),
])
def test_branding_image_read_denied_before_db(handler_name, authenticated, role, status):
    from app.api import routes_auth

    request = _request(authenticated=authenticated, role=role)
    with patch.object(routes_auth, "get_conn") as get_conn:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(getattr(routes_auth, handler_name)(request))
    assert exc.value.status_code == status
    get_conn.assert_not_called()


@pytest.mark.parametrize("handler_name,column", [
    ("get_signature", "signature_b64"),
    ("get_stamp", "stamp_b64"),
])
@pytest.mark.parametrize("role", ["admin", "accountant", "cfo"])
def test_branding_image_read_authorized_and_tenant_scoped(handler_name, column, role):
    from app.api import routes_auth

    requested_tenants = []

    class FakeConnection:
        async def fetchrow(self, query, tenant_id):
            requested_tenants.append(tenant_id)
            return {column: "data:image/png;base64,YQ=="}

    class FakeConnectionManager:
        async def __aenter__(self):
            return FakeConnection()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    request = _request(authenticated=True, role=role)
    # New security contract requires a JWT-derived tenant and the exact
    # transaction-local DB tenant context, not only request.state.tenant_id.
    with authenticated_tenant_context("t_alpha"):
        with patch.object(routes_auth, "get_conn", return_value=FakeConnectionManager()):
            result = asyncio.run(getattr(routes_auth, handler_name)(request))

    assert requested_tenants == ["t_alpha"]
    assert result["ok"] is True
    assert result["data"][column] == "data:image/png;base64,YQ=="
