"""FIN-11 RED-first: checker must revalidate the creator's audit provenance.

Synthetic in-transaction service tests; no live DB, ERP or production effects.
A previously valid maker review must become unapprovable when original
creation evidence is missing, duplicated or does not match the maker/source.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.api.db import authenticated_tenant_context
from app.api.services import correction_review_service as service


_DRAFT = {
    "id": 71,
    "tenant_id": "t_alpha",
    "entry_type": "reversal",
    "reversal_of_draft_id": 41,
    "fingerprint": "a" * 64,
}
_REVIEW = {
    "id": 101,
    "maker_subject": "auth:maker-71",
    "maker_role": "accountant",
    "source_fingerprint": "a" * 64,
    "state": "awaiting_checker",
    "source_id": 41,
    "entry_type": "reversal",
}
_VALID_EVENT = {
    "actor": "auth:maker-71",
    "new_value": {"source_id": 41, "status": "pending_approval"},
}


def _conn(events):
    conn = AsyncMock()
    conn.is_in_transaction = lambda: True

    async def fake_fetchrow(query, *args):
        sql = str(query)
        if "SELECT id,maker_subject" in sql:
            return dict(_REVIEW)
        if "UPDATE correction_review_intents" in sql:
            return {"id": 101, "state": "approved"}
        raise AssertionError("Unexpected SQL:" + sql)

    conn.fetchrow.side_effect = fake_fetchrow
    conn.fetch.return_value = events
    return conn


@pytest.mark.asyncio
@pytest.mark.parametrize("events,code", [
    ([], "FIN11_REVIEW_CREATOR_EVIDENCE_UNAVAILABLE"),
    ([_VALID_EVENT, _VALID_EVENT], "FIN11_REVIEW_CREATOR_EVIDENCE_UNAVAILABLE"),
    ([{"actor": "auth:other-maker", "new_value": _VALID_EVENT["new_value"]}],
     "FIN11_REVIEW_MAKER_NOT_CREATOR"),
    ([{"actor": "auth:maker-71",
       "new_value": {"source_id": 999, "status": "pending_approval"}}],
     "FIN11_REVIEW_MAKER_NOT_CREATOR"),
    ([{"actor": "auth:maker-71",
       "new_value": {"source_id": 41, "status": "posted"}}],
     "FIN11_REVIEW_MAKER_NOT_CREATOR"),
])
async def test_checker_refuses_changed_or_missing_creation_evidence(events, code):
    conn = _conn(events)
    with authenticated_tenant_context("t_alpha"), patch.object(
        service, "_verified_correction", new=AsyncMock(return_value=dict(_DRAFT))
    ):
        with pytest.raises(service.CorrectionReviewUnavailable, match=code):
            await service.decide_correction_review(
                conn, tenant_id="t_alpha", draft_id=71,
                checker_subject="auth:cfo-2", checker_role="cfo",
                decision="approved", reason="verified",
            )

    # Failure must precede terminal UPDATE, event INSERT and audit mutation.
    conn.execute.assert_not_awaited()
    assert conn.fetchrow.await_count == 1
    conn.fetch.assert_awaited_once()
    assert "tenant_id" in str(conn.fetch.call_args.args[0])


@pytest.mark.asyncio
async def test_checker_rechecks_valid_original_maker_without_posting():
    conn = _conn([_VALID_EVENT])
    with authenticated_tenant_context("t_alpha"), patch.object(
        service, "_verified_correction", new=AsyncMock(return_value=dict(_DRAFT))
    ):
        result = await service.decide_correction_review(
            conn, tenant_id="t_alpha", draft_id=71,
            checker_subject="auth:cfo-2", checker_role="cfo",
            decision="approved", reason="verified",
        )
    assert result["state"] == "approved"
    assert result["posted"] is False
    assert result["journal_status"] == "pending_approval"
    conn.fetch.assert_awaited_once()
