"""FIN-11: scope one active reversal attempt to its tenant and posted source.

A transaction-scoped PostgreSQL advisory lock serializes every cooperating
reversal preflight+insert. The SQL index candidate separately protects against
direct SQL, misconfigured workers and independent app instances. Both are
Draft only; no migration or production operation is activated by this module.
"""
from __future__ import annotations

import json

from app.api.db import _q, _validate_tenant_id


class ReversalSourceGateUnavailable(ValueError):
    """A missing durable source lock must never be interpreted as safe."""


def _deny(message: str = "FIN11_REVERSAL_SOURCE_GATE_UNAVAILABLE"):
    raise ReversalSourceGateUnavailable(message)


async def acquire_reversal_source_gate(conn, tenant_id: str, original_draft_id: int) -> None:
    """Hold lock through the caller's DB transaction COMMIT/ROLLBACK."""
    try:
        tenant = _validate_tenant_id(tenant_id)
    except ValueError:
        _deny()
    if type(original_draft_id) is not int or not (1 <= original_draft_id <= 9223372036854775807):
        _deny()
    if conn.is_in_transaction() is not True:
        _deny("FIN11_REVERSAL_TRANSACTION_REQUIRED")
    identity = json.dumps(
        ["bridge-reversal-v1", tenant, original_draft_id],
        separators=(",", ":"), ensure_ascii=True,
    )
    try:
        await conn.execute(
            _q("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))"),
            identity,
        )
    except Exception:
        _deny()
