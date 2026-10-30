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
