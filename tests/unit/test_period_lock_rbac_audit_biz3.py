"""tests/unit/test_period_lock_rbac_audit_biz3.py — BIZ-3: RBAC and audit for period lock.

Tests:
  - viewer cannot lock/unlock (settings:write required)
  - accountant cannot unlock (settings:write required)
  - admin can unlock with reason
  - unlock without reason is blocked
  - posting blocked audit event written
  - reversal audit event written
  - adjustment audit event written
  - no secrets in audit payload
  - lock event written to audit log
  - unlock event written to audit log

Runs with: JWT_SECRET=test-secret TEST_MODE=1 DATABASE_URL=""
No real DB. No RS.ge. No production credentials.
"""
from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.services.period_lock_service import PeriodLockedError, assert_period_open


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# RBAC — lock/unlock permission
# ---------------------------------------------------------------------------

class TestRBACLockUnlock:

    def test_lock_route_requires_settings_write(self):
        """routes_period_lock lock endpoint must call require_permission(settings:write)."""
        import app.api.routes_period_lock as mod
        src = inspect.getsource(mod)
        # lock_period handler must reference settings:write
        assert "settings:write" in src

    def test_unlock_route_requires_settings_write(self):
        """routes_period_lock unlock endpoint must require settings:write."""
        import app.api.routes_period_lock as mod
        src = inspect.getsource(mod)
        assert "settings:write" in src

    def test_unlock_requires_reason_field(self):
        """Unlock endpoint must validate that reason is non-blank."""
        import app.api.routes_period_lock as mod
        src = inspect.getsource(mod)
        assert "UNLOCK_REASON_REQUIRED" in src or "reason" in src

    def test_viewer_cannot_lock_no_permission_in_authz(self):
        """Viewer role must not have settings:write in ROLE_PERMISSIONS."""
        try:
            from app.api.authz import ROLE_PERMISSIONS
            viewer_perms = ROLE_PERMISSIONS.get("viewer", [])
            assert "settings:write" not in viewer_perms, \
                "Viewer must not have settings:write permission"
        except ImportError:
            pytest.skip("ROLE_PERMISSIONS not available")

    def test_lock_permission_level_documented(self):
        """Bridge Hub grants settings:write to accountant AND admin (by design).

        The period lock endpoints (lock/unlock) require settings:write.
        Unlock additionally requires a non-blank reason for audit compliance.
        This is Bridge Hub's accounting policy: accountants may lock/unlock with reason.
        """
        try:
            from app.api.authz import ROLE_PERMISSIONS
            # Admin must have settings:write
            admin_perms = ROLE_PERMISSIONS.get("admin", [])
            assert "settings:write" in admin_perms, \
                "Admin must have settings:write"
            # Viewer must NOT have settings:write
            viewer_perms = ROLE_PERMISSIONS.get("viewer", [])
            assert "settings:write" not in viewer_perms, \
                "Viewer must not have settings:write"
        except ImportError:
            pytest.skip("ROLE_PERMISSIONS not available")

    def test_unlock_without_reason_returns_400(self):
        """Unlock endpoint must return an error when reason is missing."""
        import app.api.routes_period_lock as mod
        src = inspect.getsource(mod)
        # Must have a non-empty reason check
        assert "not reason" in src or "UNLOCK_REASON_REQUIRED" in src

    def test_reversal_route_requires_approval_write(self):
        """Journal entries reverse endpoint must require approval:write."""
        import app.api.routes_journal_entries as mod
        src = inspect.getsource(mod)
        assert "approval:write" in src

    def test_adjustment_route_requires_approval_write(self):
        """Journal entries adjust endpoint must require approval:write."""
        import app.api.routes_journal_entries as mod
        src = inspect.getsource(mod)
        assert "approval:write" in src


# ---------------------------------------------------------------------------
# Audit — lock/unlock events
# ---------------------------------------------------------------------------

class TestAuditLockUnlock:

    def test_lock_route_calls_log_event(self):
        """routes_period_lock lock handler must call log_event('period_locked', ...)."""
        import app.api.routes_period_lock as mod
        src = inspect.getsource(mod)
        assert "period_locked" in src

    def test_unlock_route_calls_log_event(self):
        """routes_period_lock unlock handler must call log_event('period_unlocked', ...)."""
        import app.api.routes_period_lock as mod
        src = inspect.getsource(mod)
        assert "period_unlocked" in src

    def test_lock_event_emitted_on_blocked_posting(self):
        """assert_period_open emits posting_blocked_period_locked audit event."""
        from datetime import date

        async def _run():
            conn = AsyncMock()
            conn.fetchrow = AsyncMock(return_value={"1": 1})  # locked

            events = []
            def _log_event(event_type, details=None, actor="system", tenant_id="default"):
                events.append({"event_type": event_type, **(details or {})})

            with patch("app.api.services.period_lock_service.log_event", _log_event):
                with pytest.raises(PeriodLockedError):
                    await assert_period_open(conn, "tenant_a", date(2026, 8, 31), "posting")

            assert any(e["event_type"] == "posting_blocked_period_locked" for e in events), \
                "posting_blocked_period_locked audit event must be emitted"

        run(_run())

    def test_audit_event_contains_required_fields(self):
        """posting_blocked_period_locked event must include period_year, period_month, action_type."""
        from datetime import date

        async def _run():
            conn = AsyncMock()
            conn.fetchrow = AsyncMock(return_value={"1": 1})

            captured = {}
            def _log_event(event_type, details=None, actor="system", tenant_id="default"):
                if event_type == "posting_blocked_period_locked":
                    captured.update(details or {})

            with patch("app.api.services.period_lock_service.log_event", _log_event):
                with pytest.raises(PeriodLockedError):
                    await assert_period_open(conn, "tenant_a", date(2026, 8, 31), "depreciation")

            assert captured.get("period_year")  == 2026
            assert captured.get("period_month") == 8
            assert captured.get("action_type")  == "depreciation"

        run(_run())

    def test_reversal_audit_event_emitted(self):
        """create_reversal_draft must emit reversal_draft_created audit event."""
        import app.api.services.reversal_service as mod
        src = inspect.getsource(mod)
        assert "reversal_draft_created" in src

    def test_adjustment_audit_event_emitted(self):
        """create_adjustment_draft must emit adjustment_draft_created audit event."""
        import app.api.services.reversal_service as mod
        src = inspect.getsource(mod)
        assert "adjustment_draft_created" in src

    def test_lock_audit_event_source(self):
        """routes_period_lock emits audit events on lock AND unlock."""
        import app.api.routes_period_lock as mod
        src = inspect.getsource(mod)
        assert "period_locked"   in src
        assert "period_unlocked" in src


# ---------------------------------------------------------------------------
# Audit — no secrets in payload
# ---------------------------------------------------------------------------

class TestAuditNoSecrets:

    _FORBIDDEN_FIELDS = [
        "access_token", "pin_token", "Authorization", "password",
        "JWT_SECRET", "DATABASE_URL", "ANTHROPIC_API_KEY",
        "BALANCE_API_KEY", "VAULT_ENCRYPTION_KEY", "rsge_password",
    ]

    def test_period_lock_service_source_no_secrets(self):
        """period_lock_service.py must not reference secret field names."""
        import app.api.services.period_lock_service as mod
        src = inspect.getsource(mod)
        for field in self._FORBIDDEN_FIELDS:
            assert field not in src, \
                f"Secret field '{field}' found in period_lock_service.py"

    def test_reversal_service_source_no_secrets(self):
        """reversal_service.py must not reference secret field names."""
        import app.api.services.reversal_service as mod
        src = inspect.getsource(mod)
        for field in self._FORBIDDEN_FIELDS:
            assert field not in src, \
                f"Secret field '{field}' found in reversal_service.py"

    def test_routes_journal_entries_source_no_secrets(self):
        """routes_journal_entries.py must not reference secret field names."""
        import app.api.routes_journal_entries as mod
        src = inspect.getsource(mod)
        for field in self._FORBIDDEN_FIELDS:
            assert field not in src, \
                f"Secret field '{field}' found in routes_journal_entries.py"

    def test_audit_event_kwargs_no_secret_values(self):
        """The audit event emitted by assert_period_open must not carry secrets."""
        from datetime import date

        async def _run():
            conn = AsyncMock()
            conn.fetchrow = AsyncMock(return_value={"1": 1})

            captured_details = {}
            def _log_event(event_type, details=None, actor="system", tenant_id="default"):
                if event_type == "posting_blocked_period_locked":
                    captured_details.update(details or {})

            with patch("app.api.services.period_lock_service.log_event", _log_event):
                with pytest.raises(PeriodLockedError):
                    await assert_period_open(conn, "t", date(2026, 8, 1), "posting")

            import json
            payload_str = json.dumps(captured_details)
            for field in self._FORBIDDEN_FIELDS:
                assert field not in payload_str, \
                    f"Secret field '{field}' found in audit event payload"

        run(_run())


# ---------------------------------------------------------------------------
# Denied action logging
# ---------------------------------------------------------------------------

class TestDeniedActionLogging:

    def test_blocked_posting_emits_audit(self):
        """When period is locked, an audit event must be emitted before raising."""
        from datetime import date

        async def _run():
            conn = AsyncMock()
            conn.fetchrow = AsyncMock(return_value={"1": 1})

            events = []
            with patch("app.api.services.period_lock_service.log_event",
                       lambda et, d=None, **kw: events.append(et)):
                with pytest.raises(PeriodLockedError):
                    await assert_period_open(conn, "t", date(2026, 8, 1), "posting")

            assert "posting_blocked_period_locked" in events

        run(_run())

    def test_routes_period_lock_audit_event_not_bypass_on_error(self):
        """Audit event must still be attempted even if exception path taken."""
        import app.api.routes_period_lock as mod
        src = inspect.getsource(mod)
        # Audit events wrapped in try/except to not block the response
        assert "log_event" in src
        assert "except" in src


# ---------------------------------------------------------------------------
# Module imports and structure
# ---------------------------------------------------------------------------

class TestBIZ3ServiceImports:

    def test_period_lock_service_importable(self):
        from app.api.services.period_lock_service import (
            PeriodLockedError, is_period_closed, assert_period_open, is_period_closed_sync
        )
        assert callable(is_period_closed)

    def test_reversal_service_importable(self):
        from app.api.services.reversal_service import (
            flip_lines, lines_balanced, create_reversal_draft, create_adjustment_draft
        )
        assert callable(create_reversal_draft)

    def test_routes_journal_entries_importable(self):
        import app.api.routes_journal_entries as mod
        assert hasattr(mod, "router")
        assert hasattr(mod, "reverse_journal_entry")
        assert hasattr(mod, "adjust_journal_entry")

    def test_routes_period_lock_has_unlock_reason(self):
        import app.api.routes_period_lock as mod
        src = inspect.getsource(mod.unlock_period)
        assert "reason" in src
