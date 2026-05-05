"""tests/unit/test_approval_race_condition.py

Structural tests verifying that approve, reject, and correct draft operations
use SELECT FOR UPDATE NOWAIT to prevent double-processing race conditions.
Also verifies that a DRAFT_LOCKED error is returned when the lock is unavailable.
"""
import asyncio
import inspect
from unittest.mock import patch


# ── 1. FOR UPDATE NOWAIT present in all three mutating functions ───────────────

def test_approve_uses_for_update_nowait():
    from app.api.services import approval_service
    src = inspect.getsource(approval_service.approve_draft_service)
    assert "FOR UPDATE NOWAIT" in src, (
        "approve_draft_service must use SELECT ... FOR UPDATE NOWAIT to prevent race conditions"
    )


def test_reject_uses_for_update_nowait():
    from app.api.services import approval_service
    src = inspect.getsource(approval_service.reject_draft_service)
    assert "FOR UPDATE NOWAIT" in src, (
        "reject_draft_service must use SELECT ... FOR UPDATE NOWAIT to prevent race conditions"
    )


def test_correct_uses_for_update_nowait():
    from app.api.services import correct_draft_service as mod
    src = inspect.getsource(mod)
    assert "FOR UPDATE NOWAIT" in src, (
        "correct_draft_service must use SELECT ... FOR UPDATE NOWAIT to prevent race conditions"
    )


# ── 2. DRAFT_LOCKED error is returned on LockNotAvailable ─────────────────────

class _FakeTr:
    async def start(self): pass
    async def rollback(self): pass
    async def commit(self): pass


class _LockConn:
    """asyncpg connection mock that raises LockNotAvailableError on fetchrow."""

    def transaction(self):
        return _FakeTr()

    async def fetchrow(self, *a, **kw):
        import asyncpg
        raise asyncpg.exceptions.LockNotAvailableError()

    async def fetch(self, *a, **kw):
        return []

    async def fetchval(self, *a, **kw):
        return None

    async def execute(self, *a, **kw):
        pass


class _LockConnCM:
    async def __aenter__(self):
        return _LockConn()

    async def __aexit__(self, *a):
        pass


def test_approve_returns_draft_locked_on_lock_unavailable():
    """When the row lock is held by another request, approve must return DRAFT_LOCKED."""
    from app.api.services import approval_service

    with patch.object(approval_service, "get_conn", return_value=_LockConnCM()):
        result = asyncio.run(
            approval_service.approve_draft_service(draft_id=99, tenant_id="tenant-a")
        )

    assert result["ok"] is False
    assert result["error"]["code"] == "DRAFT_LOCKED"


def test_reject_returns_draft_locked_on_lock_unavailable():
    """When the row lock is held, reject must return DRAFT_LOCKED."""
    from app.api.services import approval_service

    with patch.object(approval_service, "get_conn", return_value=_LockConnCM()):
        result = asyncio.run(
            approval_service.reject_draft_service(
                draft_id=99, reason="test", tenant_id="tenant-a"
            )
        )

    assert result["ok"] is False
    assert result["error"]["code"] == "DRAFT_LOCKED"


def test_correct_returns_draft_locked_on_lock_unavailable():
    """When the row lock is held, correct must return DRAFT_LOCKED."""
    from app.api.services import correct_draft_service

    with patch.object(correct_draft_service, "get_conn", return_value=_LockConnCM()):
        result = asyncio.run(
            correct_draft_service.correct_draft(
                draft_id=99, payload={}, user="human", tenant_id="tenant-a"
            )
        )

    assert result["ok"] is False
    assert result["error"]["code"] == "DRAFT_LOCKED"
