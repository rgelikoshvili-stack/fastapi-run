"""Chat208 FIN-11: trusted JWT Maker/Checker identity gate (INERT).

RED-first: no public route, no real DB or token/secret, no posting.
All JWT signature and membership calls are mocked independently.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from starlette.requests import Request

from app.api.db import authenticated_tenant_context
from app.api.services import auth_service, correction_review_service as review

_NOW = int(datetime.now(timezone.utc).timestamp())


def _request(*, role="accountant", tenant="t_alpha", subject="71",
             header=b"Bearer synthetic.jwt", extra_headers=(),
             authenticated=True, state_tenant=None):
    headers = list(extra_headers)
    if header is not None:
        headers.append((b"authorization", header))
    req = Request({
        "type": "http", "method": "POST",
        "path": "/never-registered/fin11/review",
        "query_string": b"", "headers": headers,
    })
    req.state.authenticated = authenticated
    req.state.user_id = subject
    req.state.role = role
    req.state.tenant_id = tenant if state_tenant is None else state_tenant
    req.state.auth_tenant_id = tenant
    return req


def _claims(*, subject="71", role="accountant", tenant="t_alpha",
            token_type="access"):
    return {
        "sub": subject, "role": role, "tenant_id": tenant,
        "email": "synthetic@example.invalid", "type": token_type,
        "iat": _NOW - 60, "exp": _NOW + 3600,
    }


async def _resolve(req, phase, *, claims=None, member=True, verify_error=None):
    gate = getattr(review, "resolve_signed_review_actor", None)
    assert callable(gate), "FIN11_ATTESTED_ACTOR_GATE_MISSING"
    with patch.object(
        auth_service, "verify_token",
        side_effect=verify_error,
        return_value=claims if claims is not None else _claims(),
    ) as verify, patch.object(
        auth_service, "verify_live_access_membership",
        new_callable=AsyncMock, return_value=member,
    ) as membership:
        return await gate(req, phase), verify, membership


@pytest.mark.asyncio
@pytest.mark.parametrize("phase,role", [
    ("maker", "accountant"), ("maker", "admin"),
    ("checker", "cfo"), ("checker", "admin"),
])
async def test_signed_actor_accepts_only_verified_current_membership(phase, role):
    req = _request(role=role)
    with authenticated_tenant_context("t_alpha"):
        principal, verify, membership = await _resolve(
            req, phase, claims=_claims(role=role)
        )
    assert principal.subject == "auth:71"
    assert principal.role == role
    assert principal.tenant_id == "t_alpha"
    verify.assert_called_once_with("synthetic.jwt", expected_type="access")
    membership.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", [
    "no_bearer", "duplicate_authorization", "unsigned_request_state",
    "forged_state_subject", "forged_state_role", "forged_state_tenant",
    "foreign_tenant", "refresh_only", "membership_revoked",
    "invalid_sub", "wrong_role", "missing_exp", "missing_email",
    "missing_context", "unavailable_membership", "invalid_phase",
])
async def test_signed_actor_fails_closed_before_any_review_mutation(case):
    req = _request()
    payload = _claims()
    phase = "maker"
    member = True
    membership_error = None
    if case == "no_bearer":
        req = _request(header=None)
    elif case == "duplicate_authorization":
        req = _request(extra_headers=[(b"authorization", b"Bearer attacker")])
    elif case == "unsigned_request_state":
        req.state.authenticated = False
    elif case == "forged_state_subject":
        req.state.user_id = "72"
    elif case == "forged_state_role":
        req.state.role = "admin"
    elif case == "forged_state_tenant":
        req.state.tenant_id = "t_beta"
    elif case == "foreign_tenant":
        payload["tenant_id"] = "t_beta"
    elif case == "refresh_only":
        payload["type"] = "refresh"
    elif case == "membership_revoked":
        member = False
    elif case == "invalid_sub":
        payload["sub"] = "abc"
        req.state.user_id = "abc"
    elif case == "wrong_role":
        payload["role"] = "reviewer"
        req.state.role = "reviewer"
    elif case == "missing_exp":
        payload.pop("exp")
    elif case == "missing_email":
        payload.pop("email")
    elif case == "unavailable_membership":
        membership_error = RuntimeError("synthetic membership DB unavailable")
    elif case == "invalid_phase":
        phase = "unknown"

    gate = getattr(review, "resolve_signed_review_actor", None)
    assert callable(gate), "FIN11_ATTESTED_ACTOR_GATE_MISSING"
    with patch.object(auth_service, "verify_token", return_value=payload), \
         patch.object(auth_service, "verify_live_access_membership",
                      new_callable=AsyncMock) as membership:
        if membership_error is None:
            membership.return_value = member
        else:
            membership.side_effect = membership_error
        # All paths fail CLOSED, independent of headers, state or role strings.
        context = "t_beta" if case == "missing_context" else "t_alpha"
        if case == "missing_context":
            with pytest.raises(review.CorrectionReviewUnavailable):
                await gate(req, phase)
        else:
            with authenticated_tenant_context(context):
                with pytest.raises(review.CorrectionReviewUnavailable):
                    await gate(req, phase)


@pytest.mark.asyncio
async def test_valid_signed_checker_cannot_claim_another_tenant_context():
    req = _request(role="cfo")
    gate = getattr(review, "resolve_signed_review_actor", None)
    assert callable(gate), "FIN11_ATTESTED_ACTOR_GATE_MISSING"
    with authenticated_tenant_context("t_beta"), \
         patch.object(auth_service, "verify_token",
                      return_value=_claims(role="cfo")), \
         patch.object(auth_service, "verify_live_access_membership",
                      new_callable=AsyncMock, return_value=True):
        with pytest.raises(review.CorrectionReviewUnavailable):
            await gate(req, "checker")
