"""Chat208 FIN-11: stage only an identity-bound independent review entrypoint.

The original caller-supplied string service remains inert/unregistered.
This test proves safe wrappers pass ONLY an attested actor identity into
that service and never accept roles, tenants or subjects from request body.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api.services import correction_review_service as review


@pytest.mark.asyncio
@pytest.mark.parametrize("phase,wrapper_name,core_name,role,expected_kwargs", [
    (
        "maker", "submit_attested_correction_review", "submit_correction_review",
        "accountant", {
            "tenant_id": "t_alpha", "draft_id": 71,
            "maker_subject": "auth:71", "maker_role": "accountant",
        },
    ),
    (
        "checker", "decide_attested_correction_review", "decide_correction_review",
        "cfo", {
            "tenant_id": "t_alpha", "draft_id": 71,
            "checker_subject": "auth:71", "checker_role": "cfo",
            "decision": "approved", "reason": "double checked",
        },
    ),
])
async def test_attested_wrapper_delegates_only_signed_subject_and_role(
    phase, wrapper_name, core_name, role, expected_kwargs
):
    fn = getattr(review, wrapper_name, None)
    assert callable(fn), "FIN11_ATTESTED_WRAPPER_MISSING"
    attested = SimpleNamespace(subject="auth:71", role=role, tenant_id="t_alpha")
    req = SimpleNamespace()
    db_conn = object()
    with patch.object(review, "resolve_signed_review_actor",
                      new_callable=AsyncMock, return_value=attested) as identity, \
         patch.object(review, core_name,
                      new_callable=AsyncMock, return_value={"posted": False}) as core:
        if phase == "maker":
            result = await fn(db_conn, request=req, draft_id=71)
        else:
            result = await fn(db_conn, request=req, draft_id=71,
                              decision="approved", reason="double checked")
    assert result["posted"] is False
    identity.assert_awaited_once_with(req, phase)
    core.assert_awaited_once_with(db_conn, **expected_kwargs)


@pytest.mark.asyncio
async def test_maker_wrapper_denies_unsigned_context_without_core_db_calls():
    fn = getattr(review, "submit_attested_correction_review", None)
    assert callable(fn), "FIN11_ATTESTED_WRAPPER_MISSING"
    with patch.object(review, "resolve_signed_review_actor", new_callable=AsyncMock,
                      side_effect=review.CorrectionReviewUnavailable(
                          "FIN11_REVIEW_SIGNED_IDENTITY_REQUIRED"
                      )), patch.object(review, "submit_correction_review",
                                       new_callable=AsyncMock) as core:
        with pytest.raises(review.CorrectionReviewUnavailable):
            await fn(object(), request=SimpleNamespace(), draft_id=71)
        core.assert_not_awaited()
