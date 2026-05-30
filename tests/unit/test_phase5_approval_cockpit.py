"""tests/unit/test_phase5_approval_cockpit.py — Phase 5: Approval Cockpit 2.0.

Covers:
  1. compute_sla_status — ok / warning / overdue
  2. prioritise_queue   — sort order
  3. get_cockpit_queue  (mocked DB)
  4. set_priority       (mocked DB)
  5. delegate_draft     (mocked DB)
  6. add_comment / list_comments (mocked DB)
  7. get_overdue_summary (mocked DB)
  8. Routes: importable, prefix, permissions
  9. Permission map and registry
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# DB mock helper
# ---------------------------------------------------------------------------
def _ctx(rows=None, fetchrow=None, fetchval=None):
    conn = AsyncMock()
    conn.fetch    = AsyncMock(return_value=rows or [])
    conn.fetchrow = AsyncMock(return_value=fetchrow)
    conn.fetchval = AsyncMock(return_value=fetchval or 0)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__  = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# 1. compute_sla_status
# ---------------------------------------------------------------------------
class TestComputeSlaStatus:
    def test_recent_draft_is_ok(self):
        from app.api.services.approval_cockpit_service import compute_sla_status
        recent = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        result = compute_sla_status(recent.isoformat(), sla_hours=48)
        assert result["urgency"] == "ok"
        assert result["overdue"] is False

    def test_halfway_is_warning(self):
        from app.api.services.approval_cockpit_service import compute_sla_status
        halfway = datetime.now(tz=timezone.utc) - timedelta(hours=25)
        result = compute_sla_status(halfway.isoformat(), sla_hours=48)
        assert result["urgency"] == "warning"

    def test_old_draft_is_overdue(self):
        from app.api.services.approval_cockpit_service import compute_sla_status
        old = datetime.now(tz=timezone.utc) - timedelta(hours=72)
        result = compute_sla_status(old.isoformat(), sla_hours=48)
        assert result["overdue"] is True
        assert result["urgency"] == "overdue"

    def test_invalid_timestamp_defaults_ok(self):
        from app.api.services.approval_cockpit_service import compute_sla_status
        result = compute_sla_status("not-a-date")
        assert result["urgency"] == "ok"

    def test_returns_hours_waiting(self):
        from app.api.services.approval_cockpit_service import compute_sla_status
        two_hours_ago = datetime.now(tz=timezone.utc) - timedelta(hours=2)
        result = compute_sla_status(two_hours_ago.isoformat(), sla_hours=48)
        assert result["hours_waiting"] >= 1.9


# ---------------------------------------------------------------------------
# 2. prioritise_queue
# ---------------------------------------------------------------------------
class TestPrioritiseQueue:
    def _draft(self, priority="normal", hours_ago=1, amount=100):
        ts = (datetime.now(tz=timezone.utc) - timedelta(hours=hours_ago)).isoformat()
        return {"priority": priority, "created_at": ts, "amount": amount}

    def test_high_priority_first(self):
        from app.api.services.approval_cockpit_service import prioritise_queue
        drafts = [self._draft("low"), self._draft("normal"), self._draft("high")]
        result = prioritise_queue(drafts)
        assert result[0]["priority"] == "high"

    def test_overdue_before_ok_same_priority(self):
        from app.api.services.approval_cockpit_service import prioritise_queue
        ok_draft = self._draft("normal", hours_ago=1)
        overdue  = self._draft("normal", hours_ago=100)
        result   = prioritise_queue([ok_draft, overdue])
        assert result[0]["created_at"] == overdue["created_at"]

    def test_empty_list_ok(self):
        from app.api.services.approval_cockpit_service import prioritise_queue
        assert prioritise_queue([]) == []


# ---------------------------------------------------------------------------
# 3. get_cockpit_queue
# ---------------------------------------------------------------------------
class TestGetCockpitQueue:
    @pytest.mark.asyncio
    async def test_returns_drafts_with_sla(self):
        from app.api.services.approval_cockpit_service import get_cockpit_queue
        ts = (datetime.now(tz=timezone.utc) - timedelta(hours=1)).isoformat()
        row = {"id": 1, "description": "Test", "amount": 500, "status": "drafted",
               "partner": "X", "created_at": ts, "assigned_to": None, "priority": "normal"}
        with patch("app.api.services.approval_cockpit_service.get_conn",
                   return_value=_ctx(rows=[row], fetchval=1)):
            result = await get_cockpit_queue("t1")
        assert result["total"] == 1
        assert "sla" in result["drafts"][0]

    @pytest.mark.asyncio
    async def test_empty_queue(self):
        from app.api.services.approval_cockpit_service import get_cockpit_queue
        with patch("app.api.services.approval_cockpit_service.get_conn",
                   return_value=_ctx(rows=[], fetchval=0)):
            result = await get_cockpit_queue("t1")
        assert result["total"] == 0
        assert result["drafts"] == []


# ---------------------------------------------------------------------------
# 4. set_priority
# ---------------------------------------------------------------------------
class TestSetPriority:
    @pytest.mark.asyncio
    async def test_valid_priority_updated(self):
        from app.api.services.approval_cockpit_service import set_priority
        row = {"id": 1, "description": "Test", "status": "drafted",
               "priority": "high", "updated_at": "2026-01-01"}
        with patch("app.api.services.approval_cockpit_service.get_conn",
                   return_value=_ctx(fetchrow=row)):
            result = await set_priority("t1", 1, "high")
        assert result["priority"] == "high"

    @pytest.mark.asyncio
    async def test_invalid_priority_raises(self):
        from app.api.services.approval_cockpit_service import set_priority
        with pytest.raises(ValueError, match="INVALID_PRIORITY"):
            await set_priority("t1", 1, "urgent")

    @pytest.mark.asyncio
    async def test_not_found_raises(self):
        from app.api.services.approval_cockpit_service import set_priority
        with patch("app.api.services.approval_cockpit_service.get_conn",
                   return_value=_ctx(fetchrow=None)):
            with pytest.raises(ValueError, match="DRAFT_NOT_FOUND"):
                await set_priority("t1", 999, "high")


# ---------------------------------------------------------------------------
# 5. delegate_draft
# ---------------------------------------------------------------------------
class TestDelegateDraft:
    @pytest.mark.asyncio
    async def test_delegation_works(self):
        from app.api.services.approval_cockpit_service import delegate_draft
        row = {"id": 1, "description": "Test", "status": "drafted",
               "assigned_to": "user2", "delegated_by": "user1", "updated_at": "2026-01-01"}
        with patch("app.api.services.approval_cockpit_service.get_conn",
                   return_value=_ctx(fetchrow=row)):
            result = await delegate_draft("t1", 1, "user2", "user1")
        assert result["assigned_to"] == "user2"

    @pytest.mark.asyncio
    async def test_not_found_raises(self):
        from app.api.services.approval_cockpit_service import delegate_draft
        with patch("app.api.services.approval_cockpit_service.get_conn",
                   return_value=_ctx(fetchrow=None)):
            with pytest.raises(ValueError, match="DRAFT_NOT_FOUND_OR_WRONG_STATUS"):
                await delegate_draft("t1", 999, "user2", "user1")


# ---------------------------------------------------------------------------
# 6. Comments
# ---------------------------------------------------------------------------
class TestComments:
    @pytest.mark.asyncio
    async def test_add_comment_returns_comment(self):
        from app.api.services.approval_cockpit_service import add_comment
        comment_row = {"id": 1, "tenant_id": "t1", "draft_id": 5,
                       "author": "user1", "body": "Looks good", "created_at": "2026-01-01"}
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=[{"id": 5}, comment_row])
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__  = AsyncMock(return_value=False)
        with patch("app.api.services.approval_cockpit_service.get_conn", return_value=ctx):
            result = await add_comment("t1", 5, "user1", "Looks good")
        assert result["body"] == "Looks good"

    @pytest.mark.asyncio
    async def test_add_comment_draft_not_found(self):
        from app.api.services.approval_cockpit_service import add_comment
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__  = AsyncMock(return_value=False)
        with patch("app.api.services.approval_cockpit_service.get_conn", return_value=ctx):
            with pytest.raises(ValueError, match="DRAFT_NOT_FOUND"):
                await add_comment("t1", 999, "user1", "comment")

    @pytest.mark.asyncio
    async def test_list_comments_returns_list(self):
        from app.api.services.approval_cockpit_service import list_comments
        row = {"id": 1, "draft_id": 5, "author": "user1",
               "body": "Note", "created_at": "2026-01-01"}
        with patch("app.api.services.approval_cockpit_service.get_conn",
                   return_value=_ctx(rows=[row])):
            result = await list_comments("t1", 5)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# 7. get_overdue_summary
# ---------------------------------------------------------------------------
class TestGetOverdueSummary:
    @pytest.mark.asyncio
    async def test_returns_count_and_amount(self):
        from app.api.services.approval_cockpit_service import get_overdue_summary
        row = {"overdue_count": 3, "overdue_amount": 5000}
        with patch("app.api.services.approval_cockpit_service.get_conn",
                   return_value=_ctx(fetchrow=row)):
            result = await get_overdue_summary("t1", sla_hours=48)
        assert result["overdue_count"] == 3
        assert result["overdue_amount"] == 5000.0
        assert result["sla_hours"] == 48


# ---------------------------------------------------------------------------
# 8. Routes
# ---------------------------------------------------------------------------
class TestApprovalCockpitRoutes:
    def test_router_importable(self):
        import importlib
        mod = importlib.import_module("app.api.routes_approval_cockpit")
        assert hasattr(mod, "router")

    def test_router_prefix(self):
        from app.api.routes_approval_cockpit import router
        assert router.prefix == "/approval-cockpit"

    def test_queue_requires_approval_read(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_approval_cockpit.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "cockpit_queue":
                assert "approval:read" in ast.unparse(node)
                return
        pytest.fail("cockpit_queue not found")

    def test_delegate_requires_approval_write(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_approval_cockpit.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "delegate":
                assert "approval:write" in ast.unparse(node)
                return
        pytest.fail("delegate not found")


# ---------------------------------------------------------------------------
# 9. Permission map and registry
# ---------------------------------------------------------------------------
class TestCockpitRegistration:
    def test_permission_map_has_cockpit(self):
        import pathlib
        src = pathlib.Path("app/api/policy/permission_map.py").read_text(encoding="utf-8")
        assert "/approval-cockpit" in src

    def test_get_maps_approval_read(self):
        from app.api.policy.permission_map import match_permission
        assert match_permission("GET", "/approval-cockpit/queue") == "approval:read"

    def test_patch_maps_approval_write(self):
        from app.api.policy.permission_map import match_permission
        assert match_permission("PATCH", "/approval-cockpit/1/priority") == "approval:write"

    def test_router_registered(self):
        import pathlib
        src = pathlib.Path("app/core/router_registry.py").read_text(encoding="utf-8")
        assert "routes_approval_cockpit" in src

    def test_service_importable(self):
        import importlib
        mod = importlib.import_module("app.api.services.approval_cockpit_service")
        assert hasattr(mod, "compute_sla_status")
        assert hasattr(mod, "prioritise_queue")
        assert hasattr(mod, "get_cockpit_queue")
        assert hasattr(mod, "set_priority")
        assert hasattr(mod, "delegate_draft")
        assert hasattr(mod, "add_comment")
        assert hasattr(mod, "get_overdue_summary")
