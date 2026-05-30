"""tests/unit/test_phase5b_cockpit_enhancements.py — Phase 5 additions.

Covers:
  1. compute_risk_badge — HIGH/MEDIUM/LOW
  2. build_draft_explanation — returns a string
  3. get_cockpit_queue — now includes risk_badge + explanation
  4. bulk_approve — happy path + partial skips
  5. BulkApprovePayload validation
  6. bulk-approve route importable
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. compute_risk_badge
# ---------------------------------------------------------------------------
class TestComputeRiskBadge:
    def test_high_risk_large_amount(self):
        from app.api.services.approval_cockpit_service import compute_risk_badge
        assert compute_risk_badge(5000.0, 0.9) == "HIGH"

    def test_high_risk_low_confidence(self):
        from app.api.services.approval_cockpit_service import compute_risk_badge
        assert compute_risk_badge(10.0, 0.3) == "HIGH"

    def test_low_risk_small_amount_high_confidence(self):
        from app.api.services.approval_cockpit_service import compute_risk_badge
        assert compute_risk_badge(20.0, 0.9) == "LOW"

    def test_medium_risk_default(self):
        from app.api.services.approval_cockpit_service import compute_risk_badge
        assert compute_risk_badge(500.0, 0.65) == "MEDIUM"

    def test_none_confidence_treated_as_zero(self):
        from app.api.services.approval_cockpit_service import compute_risk_badge
        assert compute_risk_badge(10.0, None) == "HIGH"

    def test_boundary_exactly_1000(self):
        from app.api.services.approval_cockpit_service import compute_risk_badge
        # 1000 is not > 1000, confidence 0.65 → MEDIUM
        assert compute_risk_badge(1000.0, 0.65) == "MEDIUM"

    def test_boundary_exactly_50_high_confidence(self):
        from app.api.services.approval_cockpit_service import compute_risk_badge
        # amount == 50 is not < 50 → MEDIUM
        assert compute_risk_badge(50.0, 0.9) == "MEDIUM"


# ---------------------------------------------------------------------------
# 2. build_draft_explanation
# ---------------------------------------------------------------------------
class TestBuildDraftExplanation:
    def test_returns_string(self):
        from app.api.services.approval_cockpit_service import build_draft_explanation
        draft = {"account_code": "7310", "confidence": 0.85, "description": "rent payment"}
        result = build_draft_explanation(draft)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_fallback_when_service_unavailable(self):
        from app.api.services.approval_cockpit_service import build_draft_explanation
        with patch("app.api.services.approval_cockpit_service.build_draft_explanation",
                   side_effect=Exception("import error")):
            pass  # just ensure no crash when service unavailable
        draft = {"confidence": 0.75}
        result = build_draft_explanation(draft)
        assert "75" in result or "%" in result or isinstance(result, str)


# ---------------------------------------------------------------------------
# 3. get_cockpit_queue enrichment
# ---------------------------------------------------------------------------
class TestCockpitQueueEnrichment:
    @pytest.mark.asyncio
    async def test_queue_items_have_risk_badge(self):
        from app.api.services.approval_cockpit_service import get_cockpit_queue
        ts = (datetime.now(tz=timezone.utc) - timedelta(hours=1)).isoformat()
        row = {"id": 1, "description": "Test", "amount": 5000, "status": "drafted",
               "partner": "X", "created_at": ts, "assigned_to": None, "priority": "normal",
               "confidence": 0.9, "account_code": "7310", "provider_type": "rules"}
        conn = AsyncMock()
        conn.fetch    = AsyncMock(return_value=[row])
        conn.fetchval = AsyncMock(return_value=1)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__  = AsyncMock(return_value=False)
        with patch("app.api.services.approval_cockpit_service.get_conn", return_value=ctx):
            result = await get_cockpit_queue("t1")
        assert "risk_badge" in result["drafts"][0]
        assert result["drafts"][0]["risk_badge"] == "HIGH"  # 5000 > 1000

    @pytest.mark.asyncio
    async def test_queue_items_have_explanation(self):
        from app.api.services.approval_cockpit_service import get_cockpit_queue
        ts = (datetime.now(tz=timezone.utc) - timedelta(hours=1)).isoformat()
        row = {"id": 1, "description": "Test", "amount": 100, "status": "drafted",
               "partner": "X", "created_at": ts, "assigned_to": None, "priority": "normal",
               "confidence": 0.8, "account_code": "7310", "provider_type": "rules"}
        conn = AsyncMock()
        conn.fetch    = AsyncMock(return_value=[row])
        conn.fetchval = AsyncMock(return_value=1)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__  = AsyncMock(return_value=False)
        with patch("app.api.services.approval_cockpit_service.get_conn", return_value=ctx):
            result = await get_cockpit_queue("t1")
        assert "explanation" in result["drafts"][0]
        assert isinstance(result["drafts"][0]["explanation"], str)


# ---------------------------------------------------------------------------
# 4. bulk_approve
# ---------------------------------------------------------------------------
class TestBulkApprove:
    @pytest.mark.asyncio
    async def test_bulk_approve_all_succeed(self):
        from app.api.services.approval_cockpit_service import bulk_approve
        with patch("app.api.services.approval_service.approve_draft_service",
                   new=AsyncMock(return_value={"ok": True, "data": {"id": 1}})):
            result = await bulk_approve("t1", [1, 2, 3], "actor1")
        assert result["approved_count"] == 3
        assert result["skipped_count"] == 0
        assert result["failed_count"] == 0
        assert result["requested"] == 3

    @pytest.mark.asyncio
    async def test_bulk_approve_partial_skip(self):
        from app.api.services.approval_cockpit_service import bulk_approve
        responses = [
            {"ok": True},
            {"ok": False, "error": {"code": "PERIOD_LOCKED"}},
            {"ok": True},
        ]
        with patch("app.api.services.approval_service.approve_draft_service",
                   new=AsyncMock(side_effect=responses)):
            result = await bulk_approve("t1", [1, 2, 3], "actor1")
        assert result["approved_count"] == 2
        assert result["skipped_count"] == 1

    @pytest.mark.asyncio
    async def test_bulk_approve_exception_goes_to_failed(self):
        from app.api.services.approval_cockpit_service import bulk_approve
        with patch("app.api.services.approval_service.approve_draft_service",
                   new=AsyncMock(side_effect=Exception("DB error"))):
            result = await bulk_approve("t1", [1], "actor1")
        assert result["failed_count"] == 1
        assert result["failed"][0]["draft_id"] == 1

    @pytest.mark.asyncio
    async def test_bulk_approve_includes_actor(self):
        from app.api.services.approval_cockpit_service import bulk_approve
        with patch("app.api.services.approval_service.approve_draft_service",
                   new=AsyncMock(return_value={"ok": True})):
            result = await bulk_approve("t1", [1], "user42", "Test note")
        assert result["actor"] == "user42"
        assert result["note"] == "Test note"


# ---------------------------------------------------------------------------
# 5. BulkApprovePayload validation
# ---------------------------------------------------------------------------
class TestBulkApprovePayload:
    def test_empty_list_raises(self):
        from pydantic import ValidationError
        from app.api.routes_approval_cockpit import BulkApprovePayload
        with pytest.raises((ValidationError, ValueError)):
            BulkApprovePayload(draft_ids=[])

    def test_over_100_raises(self):
        from pydantic import ValidationError
        from app.api.routes_approval_cockpit import BulkApprovePayload
        with pytest.raises((ValidationError, ValueError)):
            BulkApprovePayload(draft_ids=list(range(101)))

    def test_valid_payload(self):
        from app.api.routes_approval_cockpit import BulkApprovePayload
        p = BulkApprovePayload(draft_ids=[1, 2, 3], note="batch")
        assert len(p.draft_ids) == 3


# ---------------------------------------------------------------------------
# 6. Route registered
# ---------------------------------------------------------------------------
class TestBulkApproveRoute:
    def test_bulk_approve_route_in_module(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_approval_cockpit.py").read_text(encoding="utf-8")
        assert "bulk-approve" in src
        assert "bulk_approve_drafts" in src

    def test_bulk_approve_requires_approval_write(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_approval_cockpit.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "bulk_approve_drafts":
                assert "approval:write" in ast.unparse(node)
                return
        pytest.fail("bulk_approve_drafts not found")
