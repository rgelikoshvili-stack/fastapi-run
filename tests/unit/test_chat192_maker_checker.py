"""Chat192 FIN-11: independent maker/checker evidence contract (isolated).
No live connections, ERP posting or migration execution.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.api.db import authenticated_tenant_context
from app.api.services.correction_review_service import (
    CorrectionReviewUnavailable,
    _checked_actor, _require_independent_checker,
    correction_fingerprint, submit_correction_review,
)


def _synthetic_correction():
    return {
        "id": 71, "tenant_id": "t_alpha", "date": date(2026, 10, 30),
        "entry_type": "reversal", "status": "pending_approval",
        "reversal_of_draft_id": 41, "reversal_reason": "mistake corrected",
        "currency": "GEL", "amount": Decimal("100.00"),
        "lines_json": [
            {"account_code": "1120", "debit": 0, "credit": 100},
            {"account_code": "6110", "debit": 100, "credit": 0},
        ],
    }


@pytest.mark.parametrize("actor,role,phase", [
    ("", "accountant", "maker"), ("human", "accountant", "maker"),
    ("system", "cfo", "checker"), ("anon", "cfo", "checker"),
    ("user-1", "viewer", "maker"), ("user-2", "reviewer", "checker"),
    ("user-3", "superuser", "checker"), (" a ", "cfo", "checker"),
])
def test_unverified_placeholder_or_unauthorized_role_rejected(actor, role, phase):
    with pytest.raises(CorrectionReviewUnavailable):
        _checked_actor(actor, role, phase)


def test_only_real_distinct_cfo_or_admin_may_check():
    assert _checked_actor("acct:001", "accountant", "maker") == "acct:001"
    assert _checked_actor("cfo:001", "cfo", "checker") == "cfo:001"
    _require_independent_checker("acct:001", "cfo:001")
    with pytest.raises(CorrectionReviewUnavailable, match="FIN11_SELF_APPROVAL_DENIED"):
        _require_independent_checker("acct:001", "acct:001")


def test_fingerprint_covers_financial_fields_and_order_independent_json_keys():
    row = _synthetic_correction()
    first = correction_fingerprint(row)
    assert len(first) == 64
    copy = {k: row[k] for k in reversed(list(row))}
    assert correction_fingerprint(copy) == first
    tampered = {**row, "amount": Decimal("101.00")}
    assert correction_fingerprint(tampered) != first
    tampered = {**row, "lines_json": [{**row["lines_json"][0], "credit": 999}, row["lines_json"][1]]}
    assert correction_fingerprint(tampered) != first
    tampered = {**row, "reversal_reason": "different reason"}
    assert correction_fingerprint(tampered) != first


@pytest.mark.asyncio
async def test_submission_refuses_cross_tenant_without_any_sql():
    from unittest.mock import AsyncMock
    conn = AsyncMock()
    conn.is_in_transaction = lambda: True
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(CorrectionReviewUnavailable, match="FIN11_REVIEW_TENANT_UNAUTHORIZED"):
            await submit_correction_review(
                conn, tenant_id="t_beta", draft_id=71,
                maker_subject="acct:001", maker_role="accountant",
            )
    conn.fetchrow.assert_not_awaited()
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_submission_requires_existing_transaction():
    from unittest.mock import AsyncMock
    conn = AsyncMock()
    conn.is_in_transaction = lambda: False
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(CorrectionReviewUnavailable, match="FIN11_REVIEW_TRANSACTION_REQUIRED"):
            await submit_correction_review(
                conn, tenant_id="t_alpha", draft_id=71,
                maker_subject="acct:001", maker_role="accountant",
            )
    conn.fetchrow.assert_not_awaited()
