"""FIN-11 live journal route: synthetic *cryptographic* JWT acceptance.

No production secret, real account, external DB, ledger write, or ERP posting.
These tests exercise the actual HS256 verification path, unlike the mocked
claim-gate unit tests from Chat208. Membership remains an isolated stub.
"""
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from starlette.requests import Request

from app.api import routes_journal_entries as routes
from app.api.db import authenticated_tenant_context
from app.api.services import auth_service

_KEY = "CHAT209_SYNTHETIC_TEST_ONLY_NOT_A_PRODUCTION_SECRET"


def _new_request(token, *, state_role="accountant", state_tenant="t_alpha"):
    headers = [] if token is None else [
        (b"authorization", ("Bearer " + token).encode("ascii"))
    ]
    req = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/journal-entries/41/reverse",
        "headers": headers,
        "query_string": b"",
    })
    req.state.authenticated = True
    req.state.user_id = "71"
    req.state.user_email = "untrusted@example.invalid"
    req.state.role = state_role
    req.state.tenant_id = state_tenant
    req.state.auth_tenant_id = "t_alpha"
    return req


def _payload():
    return {
        "sub": "71",
        "email": "synthetic-user@example.invalid",
        "tenant_id": "t_alpha",
        "role": "accountant",
    }


async def _request_correction(kind, request):
    if kind == "reversal":
        return await routes.reverse_journal_entry(
            41, request, {"reversal_date": "2026-11-01", "reason": "synthetic"}
        )
    return await routes.adjust_journal_entry(
        41, request, {
            "adjustment_date": "2026-11-01", "reason": "synthetic",
            "lines": [{"account": "1100", "debit": 15, "credit": 0},
                      {"account": "4000", "debit": 0, "credit": 15}],
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["reversal", "adjustment"])
async def test_signed_jwt_creator_reaches_source_audit_as_canonical_id(kind):
    service_name = ("create_reversal_draft" if kind == "reversal"
                    else "create_adjustment_draft")
    with patch.object(auth_service, "_get_secret_key", return_value=_KEY), \
         patch.object(auth_service, "jwt_session_version_enabled",
                      return_value=False), \
         patch.object(auth_service, "verify_live_access_membership",
                      new_callable=AsyncMock, return_value=True) as member, \
         patch("app.api.services.reversal_service." + service_name,
               new_callable=AsyncMock,
               return_value={"id": 89, "status": "pending_approval"}) as create:
        token = auth_service.create_access_token(_payload())
        assert auth_service.verify_token(token)["sub"] == "71"
        request = _new_request(token)
        with authenticated_tenant_context("t_alpha"):
            response = await _request_correction(kind, request)
    assert response["ok"] is True
    assert create.await_args.kwargs["tenant_id"] == "t_alpha"
    assert create.await_args.kwargs["actor"] == "auth:71"
    assert create.await_args.kwargs["allow_closed_period"] is False
    member.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["reversal", "adjustment"])
@pytest.mark.parametrize("denied", [
    "no_token", "wrong_signature", "refresh", "role_mismatch",
    "tenant_mismatch", "revoked", "membership_unavailable",
])
async def test_signed_jwt_creator_denies_invalid_or_revoked_member_before_db(
    kind, denied,
):
    service_name = ("create_reversal_draft" if kind == "reversal"
                    else "create_adjustment_draft")
    with patch.object(auth_service, "_get_secret_key", return_value=_KEY), \
         patch.object(auth_service, "jwt_session_version_enabled",
                      return_value=False), \
         patch.object(auth_service, "verify_live_access_membership",
                      new_callable=AsyncMock) as membership, \
         patch("app.api.services.reversal_service." + service_name,
               new_callable=AsyncMock) as create:
        token = auth_service.create_access_token(_payload())
        if denied == "no_token":
            token = None
        elif denied == "wrong_signature":
            token = jwt.encode(
                auth_service.verify_token(token),
                "CHAT209_WRONG_TEST_SIGNATURE", algorithm="HS256",
            )
        elif denied == "refresh":
            token = auth_service.create_refresh_token(_payload())
        membership.return_value = denied != "revoked"
        if denied == "membership_unavailable":
            membership.side_effect = RuntimeError("synthetic membership unavailable")
        request = _new_request(
            token,
            state_role="admin" if denied == "role_mismatch" else "accountant",
            state_tenant="t_beta" if denied == "tenant_mismatch" else "t_alpha",
        )
        with authenticated_tenant_context("t_alpha"):
            result = await _request_correction(kind, request)
    assert result["ok"] is False
    assert result["error"]["code"] == "FIN11_CREATOR_IDENTITY_UNVERIFIED"
    create.assert_not_awaited()
