"""Chat189 FIN-11: source-specific reversal concurrency/idempotency regressions.

No provider, external services or Production migrations are used.
"""
import inspect
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_adjustment_does_not_consume_reversal_identity():
    """An adjustment with reversal_of_draft_id is NOT a reversal."""
    from app.api.services.reversal_service import _reversal_already_exists
    conn=AsyncMock()
    conn.fetchrow.return_value=None
    assert await _reversal_already_exists(conn,41,"t_alpha") is False
    statement=str(conn.fetchrow.call_args.args[0])
    assert "entry_type" in statement and "'reversal'" in statement
    assert "tenant_id" in statement
    assert conn.fetchrow.call_args.args[1:] == ("t_alpha",41)


@pytest.mark.asyncio
async def test_source_lock_requires_transaction_and_valid_original_id():
    from app.api.services.reversal_source_gate import (
        acquire_reversal_source_gate, ReversalSourceGateUnavailable,
    )
    conn=AsyncMock()
    conn.is_in_transaction=lambda: False
    with pytest.raises(ReversalSourceGateUnavailable):
        await acquire_reversal_source_gate(conn,"t_alpha",41)
    conn.execute.assert_not_called()
    conn.is_in_transaction=lambda: True
    for tid,original in (("default",41),("t_alpha",0),
                         ("t_alpha",False),("t_alpha",-1),("t_alpha","41")):
        with pytest.raises(ReversalSourceGateUnavailable):
            await acquire_reversal_source_gate(conn,tid,original)
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_source_lock_uses_one_transaction_advisory_key_per_tenant_source():
    from app.api.services.reversal_source_gate import acquire_reversal_source_gate
    conn=AsyncMock()
    conn.is_in_transaction=lambda: True
    await acquire_reversal_source_gate(conn,"t_alpha",41)
    await acquire_reversal_source_gate(conn,"t_beta",41)
    await acquire_reversal_source_gate(conn,"t_alpha",42)
    assert conn.execute.await_count == 3
    assert all("pg_advisory_xact_lock(" in call.args[0]
               for call in conn.execute.await_args_list)
    keys=[call.args[1] for call in conn.execute.await_args_list]
    assert len(set(keys))==3


def test_service_checks_source_gate_before_duplicate_read_and_insert():
    from app.api.services import reversal_service
    src=inspect.getsource(reversal_service.create_reversal_draft)
    a=src.index("await acquire_reversal_source_gate(")
    b=src.index("await _reversal_already_exists(")
    c=src.index("INSERT INTO journal_drafts")
    assert a<b<c


# Chat190 regressions: source authority and audit must fail closed.
@pytest.mark.asyncio
@pytest.mark.parametrize("source_type,source_ref", [
    (None, None), ("legacy_unknown", None),
    ("reversal", 41), ("normal", 41),
])
async def test_chat190_posted_correction_source_requires_unambiguous_normal_identity(
    source_type, source_ref
):
    from app.api.services.reversal_service import _fetch_draft
    conn = AsyncMock()
    conn.fetchrow.return_value = {
        "id": 55, "tenant_id": "t_alpha", "date": "2026-10-15",
        "description": "posted", "partner": "", "amount": 10,
        "currency": "GEL", "status": "posted",
        "lines_json": "[]", "entry_type": source_type,
        "reversal_of_draft_id": source_ref,
    }
    with pytest.raises(ValueError, match="FIN11_SOURCE_CLASSIFICATION_UNVERIFIED"):
        await _fetch_draft(conn, 55, "t_alpha")


@pytest.mark.asyncio
async def test_chat190_ambiguous_unrejected_prior_reference_denies_new_reversal():
    from app.api.services.reversal_service import _reversal_already_exists
    conn = AsyncMock()
    conn.fetchrow.side_effect = [{"id": 19, "entry_type": None}, None]
    with pytest.raises(ValueError, match="FIN11_AMBIGUOUS_CORRECTION_HISTORY"):
        await _reversal_already_exists(conn, 41, "t_alpha")


@pytest.mark.asyncio
async def test_chat190_correction_creation_rolls_back_when_same_transaction_audit_fails():
    from contextlib import asynccontextmanager
    from unittest.mock import patch
    from app.api.services import reversal_service as svc
    conn = AsyncMock()
    conn.is_in_transaction = lambda: True
    conn.fetchrow.return_value = {"id": 100}
    conn.execute.side_effect = RuntimeError("synthetic audit storage unavailable")
    @asynccontextmanager
    async def scoped():
        yield conn
    original = {
        "id": 41, "tenant_id": "t_alpha", "date": "2026-10-15",
        "description": "normal posted", "partner": "", "amount": 10,
        "currency": "GEL", "status": "posted", "entry_type": "normal",
        "reversal_of_draft_id": None,
        "lines": [
            {"account_code": "1120", "debit": 10, "credit": 0},
            {"account_code": "6110", "debit": 0, "credit": 10},
        ],
    }
    with patch.object(svc, "get_conn", scoped), \
         patch.object(svc, "_fetch_draft", new_callable=AsyncMock, return_value=original), \
         patch.object(svc, "acquire_posting_gate", new_callable=AsyncMock), \
         patch.object(svc, "assert_period_open", new_callable=AsyncMock), \
         patch.object(svc, "log_event"):
        with pytest.raises(RuntimeError, match="synthetic audit storage unavailable"):
            await svc.create_adjustment_draft(
                "t_alpha", 41, "2026-10-30", "correction",
                "maker-alpha", original["lines"],
            )
