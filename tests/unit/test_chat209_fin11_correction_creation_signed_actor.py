"""FIN-11: live reversal/adjustment routes must use JWT-bound creator identity.

RED-first unit regressions. No real DB connection, posting, ERP, or dispatch.
The existing correction creation endpoints are public and must not use
free-text request.state.user_email or an unsigned tenant-header fallback.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from starlette.requests import Request

from app.api import routes_journal_entries as journal
from app.api.db import authenticated_tenant_context
from app.api.services import correction_review_service as reviews


def _request(*, role="accountant", actor_state="71", email="forged@example.invalid"):
    req = Request({
        "type": "http", "method": "POST",
        "path": "/api/journal-entries/41/reverse",
        "headers": [(b"authorization", b"Bearer synthetic.jwt")],
        "query_string": b"",
    })
    req.state.authenticated = True
    req.state.role = role
    req.state.user_id = actor_state
    req.state.user_email = email
    req.state.tenant_id = "t_alpha"
    req.state.auth_tenant_id = "t_alpha"
    return req


def _data(kind, **extra):
    return ({"reversal_date": "2026-11-01", "reason": "fix booking"}
            if kind == "reverse" else
            {"adjustment_date": "2026-11-01", "reason": "fix booking",
             "lines": [{"account": "1100", "debit": 10, "credit": 0},
                       {"account": "4100", "debit": 0, "credit": 10}]}) | extra


async def _call(kind, request, payload):
    fn = (journal.reverse_journal_entry if kind == "reverse"
          else journal.adjust_journal_entry)
    return await fn(41, request, payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["reverse", "adjust"])
@pytest.mark.parametrize("forged", [
    {"user_email": "attacker@example.invalid"},
    {"user_id": "888"},
    {"actor": "auth:attacker", "tenant_id": "t_beta", "role": "admin"},
])
async def test_journal_creator_audit_uses_attested_maker_only(kind, forged):
    req = _request(
        actor_state=forged.get("user_id", "71"),
        email=forged.get("user_email", "forged@example.invalid"),
    )
    attested = SimpleNamespace(subject="auth:71", tenant_id="t_alpha",
                               role="accountant")
    service_name = ("create_reversal_draft" if kind == "reverse"
                    else "create_adjustment_draft")
    with authenticated_tenant_context("t_alpha"), \
         patch.object(reviews, "resolve_signed_review_actor",
                      new_callable=AsyncMock, return_value=attested) as auth, \
         patch("app.api.services.reversal_service." + service_name,
               new_callable=AsyncMock,
               return_value={"id": 94, "status": "pending_approval"}) as create:
        result = await _call(kind, req, _data(kind, **forged))
    assert result["ok"] is True
    auth.assert_awaited_once_with(req, "maker")
    create.assert_awaited_once()
    args = create.await_args.kwargs
    assert args["tenant_id"] == "t_alpha"
    assert args["actor"] == "auth:71"
    assert args["original_draft_id"] == 41
    assert args["allow_closed_period"] is False
    assert "auth:attacker" not in str(args)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["reverse", "adjust"])
@pytest.mark.parametrize("error", [
    "FIN11_REVIEW_SIGNED_IDENTITY_REQUIRED",
    "FIN11_REVIEW_TENANT_UNAUTHORIZED",
    "FIN11_REVIEW_MEMBERSHIP_REVOKED",
    "FIN11_REVIEW_ROLE_FORBIDDEN",
])
async def test_journal_creation_denies_unverified_actor_without_audit_or_db(
    kind, error,
):
    req = _request()
    service_name = ("create_reversal_draft" if kind == "reverse"
                    else "create_adjustment_draft")
    with authenticated_tenant_context("t_alpha"), \
         patch.object(reviews, "resolve_signed_review_actor",
                      new_callable=AsyncMock,
                      side_effect=reviews.CorrectionReviewUnavailable(error)) as auth, \
         patch("app.api.services.reversal_service." + service_name,
               new_callable=AsyncMock) as create:
        result = await _call(kind, req, _data(kind))
    assert result["ok"] is False
    assert result["error"]["code"] == "FIN11_CREATOR_IDENTITY_UNVERIFIED"
    auth.assert_awaited_once_with(req, "maker")
    create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["reverse", "adjust"])
async def test_journal_creation_rejects_unavailable_attestation_without_side_effects(
    kind,
):
    req = _request()
    service_name = ("create_reversal_draft" if kind == "reverse"
                    else "create_adjustment_draft")
    with patch.object(reviews, "resolve_signed_review_actor",
                      new_callable=AsyncMock, side_effect=RuntimeError(
                          "synthetic tenant membership service unavailable"
                      )), patch("app.api.services.reversal_service." + service_name,
                                new_callable=AsyncMock) as create:
        result = await _call(kind, req, _data(kind))
    assert result["ok"] is False
    assert result["error"]["code"] == "FIN11_CREATOR_IDENTITY_UNVERIFIED"
    create.assert_not_awaited()
