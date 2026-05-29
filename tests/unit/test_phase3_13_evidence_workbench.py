"""tests/unit/test_phase3_13_evidence_workbench.py — Task 13: Evidence Workbench.

Covers:
  1. list_bundles_for_draft (mocked DB)
  2. list_drafts_without_evidence — audit gap finder
  3. get_evidence_summary — coverage score: none / partial / full
  4. link_document_to_draft — happy path + errors
  5. Routes: importable, prefix, permission checks
  6. Permission map has evidence-workbench entries
  7. Router registry has evidence_workbench
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# DB mock helpers
# ---------------------------------------------------------------------------
def _ctx(fetchrow=None, fetch=None, fetchval=None):
    conn = AsyncMock()
    conn.fetchrow  = AsyncMock(return_value=fetchrow)
    conn.fetch     = AsyncMock(return_value=fetch or [])
    conn.fetchval  = AsyncMock(return_value=fetchval)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__  = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# 1. list_bundles_for_draft
# ---------------------------------------------------------------------------
class TestListBundlesForDraft:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        from app.api.services.evidence_workbench_service import list_bundles_for_draft
        row = {"id": 1, "tenant_id": "t1", "source_type": "ocr", "source_id": "s1",
               "document_id": 10, "journal_draft_id": 5, "confidence": 0.9,
               "status": "verified", "ai_reasoning": {}, "extracted_fields": {},
               "risk_flags": [], "created_at": "2026-01-01", "updated_at": "2026-01-01"}
        with patch("app.api.services.evidence_workbench_service.get_conn",
                   return_value=_ctx(fetch=[row])):
            result = await list_bundles_for_draft("t1", 5)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["journal_draft_id"] == 5

    @pytest.mark.asyncio
    async def test_empty_when_no_evidence(self):
        from app.api.services.evidence_workbench_service import list_bundles_for_draft
        with patch("app.api.services.evidence_workbench_service.get_conn",
                   return_value=_ctx(fetch=[])):
            result = await list_bundles_for_draft("t1", 999)
        assert result == []


# ---------------------------------------------------------------------------
# 2. list_drafts_without_evidence
# ---------------------------------------------------------------------------
class TestListDraftsWithoutEvidence:
    @pytest.mark.asyncio
    async def test_returns_dict_with_drafts_and_total(self):
        from app.api.services.evidence_workbench_service import list_drafts_without_evidence
        row = {"id": 7, "description": "Salary Jan", "amount": 1000,
               "status": "posted", "created_at": "2026-01-31",
               "partner": "Company", "source_document_id": None}
        ctx = _ctx(fetch=[row], fetchval=1)
        with patch("app.api.services.evidence_workbench_service.get_conn", return_value=ctx):
            result = await list_drafts_without_evidence("t1")
        assert "drafts" in result
        assert "total" in result
        assert result["total"] == 1
        assert result["drafts"][0]["id"] == 7

    @pytest.mark.asyncio
    async def test_empty_result(self):
        from app.api.services.evidence_workbench_service import list_drafts_without_evidence
        ctx = _ctx(fetch=[], fetchval=0)
        with patch("app.api.services.evidence_workbench_service.get_conn", return_value=ctx):
            result = await list_drafts_without_evidence("t1")
        assert result["total"] == 0
        assert result["drafts"] == []

    @pytest.mark.asyncio
    async def test_limit_offset_in_result(self):
        from app.api.services.evidence_workbench_service import list_drafts_without_evidence
        ctx = _ctx(fetch=[], fetchval=0)
        with patch("app.api.services.evidence_workbench_service.get_conn", return_value=ctx):
            result = await list_drafts_without_evidence("t1", limit=10, offset=20)
        assert result["limit"] == 10
        assert result["offset"] == 20


# ---------------------------------------------------------------------------
# 3. get_evidence_summary
# ---------------------------------------------------------------------------
class TestGetEvidenceSummary:
    @pytest.mark.asyncio
    async def test_no_evidence_score_zero(self):
        from app.api.services.evidence_workbench_service import get_evidence_summary
        row = {"bundle_count": 0, "max_confidence": 0, "avg_confidence": 0,
               "with_document": 0, "with_ai_reasoning": 0}
        with patch("app.api.services.evidence_workbench_service.get_conn",
                   return_value=_ctx(fetchrow=row)):
            result = await get_evidence_summary("t1", 5)
        assert result["coverage_score"] == 0.0
        assert result["coverage"] == "none"

    @pytest.mark.asyncio
    async def test_high_confidence_score_one(self):
        from app.api.services.evidence_workbench_service import get_evidence_summary
        row = {"bundle_count": 2, "max_confidence": 0.9, "avg_confidence": 0.85,
               "with_document": 1, "with_ai_reasoning": 1}
        with patch("app.api.services.evidence_workbench_service.get_conn",
                   return_value=_ctx(fetchrow=row)):
            result = await get_evidence_summary("t1", 5)
        assert result["coverage_score"] == 1.0
        assert result["coverage"] == "full"

    @pytest.mark.asyncio
    async def test_low_confidence_score_half(self):
        from app.api.services.evidence_workbench_service import get_evidence_summary
        row = {"bundle_count": 1, "max_confidence": 0.4, "avg_confidence": 0.4,
               "with_document": 0, "with_ai_reasoning": 0}
        with patch("app.api.services.evidence_workbench_service.get_conn",
                   return_value=_ctx(fetchrow=row)):
            result = await get_evidence_summary("t1", 5)
        assert result["coverage_score"] == 0.5
        assert result["coverage"] == "partial"

    @pytest.mark.asyncio
    async def test_summary_includes_draft_id(self):
        from app.api.services.evidence_workbench_service import get_evidence_summary
        row = {"bundle_count": 0, "max_confidence": 0, "avg_confidence": 0,
               "with_document": 0, "with_ai_reasoning": 0}
        with patch("app.api.services.evidence_workbench_service.get_conn",
                   return_value=_ctx(fetchrow=row)):
            result = await get_evidence_summary("t1", 42)
        assert result["draft_id"] == 42


# ---------------------------------------------------------------------------
# 4. link_document_to_draft
# ---------------------------------------------------------------------------
class TestLinkDocumentToDraft:
    @pytest.mark.asyncio
    async def test_happy_path_returns_bundle(self):
        from app.api.services.evidence_workbench_service import link_document_to_draft
        bundle_row = {"id": 99, "tenant_id": "t1", "source_type": "manual_link",
                      "document_id": 10, "journal_draft_id": 5,
                      "status": "verified", "created_at": "2026-01-01"}
        conn = AsyncMock()
        # draft exists, doc exists, not already linked, then insert
        conn.fetchrow = AsyncMock(side_effect=[
            {"id": 5},    # draft found
            {"id": 10},   # doc found
            None,         # not already linked
            bundle_row,   # insert result
        ])
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__  = AsyncMock(return_value=False)
        with patch("app.api.services.evidence_workbench_service.get_conn", return_value=ctx):
            result = await link_document_to_draft("t1", 5, 10, "user1")
        assert result["status"] == "verified"
        assert result["document_id"] == 10

    @pytest.mark.asyncio
    async def test_raises_if_draft_not_found(self):
        from app.api.services.evidence_workbench_service import link_document_to_draft
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__  = AsyncMock(return_value=False)
        with patch("app.api.services.evidence_workbench_service.get_conn", return_value=ctx):
            with pytest.raises(ValueError, match="DRAFT_NOT_FOUND"):
                await link_document_to_draft("t1", 999, 10)

    @pytest.mark.asyncio
    async def test_raises_if_already_linked(self):
        from app.api.services.evidence_workbench_service import link_document_to_draft
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=[
            {"id": 5},   # draft found
            {"id": 10},  # doc found
            {"id": 7},   # already linked!
        ])
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__  = AsyncMock(return_value=False)
        with patch("app.api.services.evidence_workbench_service.get_conn", return_value=ctx):
            with pytest.raises(ValueError, match="ALREADY_LINKED"):
                await link_document_to_draft("t1", 5, 10)


# ---------------------------------------------------------------------------
# 5. Routes
# ---------------------------------------------------------------------------
class TestEvidenceWorkbenchRoutes:
    def test_router_importable(self):
        import importlib
        mod = importlib.import_module("app.api.routes_evidence_workbench")
        assert hasattr(mod, "router")

    def test_router_prefix(self):
        from app.api.routes_evidence_workbench import router
        assert router.prefix == "/evidence-workbench"

    def test_gaps_requires_audit_view(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_evidence_workbench.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_evidence_gaps":
                assert "audit:view" in ast.unparse(node)
                return
        pytest.fail("get_evidence_gaps not found")

    def test_draft_evidence_requires_audit_read(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_evidence_workbench.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_draft_evidence":
                assert "audit:read" in ast.unparse(node)
                return
        pytest.fail("get_draft_evidence not found")


# ---------------------------------------------------------------------------
# 6. Permission map
# ---------------------------------------------------------------------------
class TestEvidenceWorkbenchPermissions:
    def test_permission_map_has_evidence_workbench(self):
        import pathlib
        src = pathlib.Path("app/api/policy/permission_map.py").read_text(encoding="utf-8")
        assert "/evidence-workbench" in src

    def test_get_maps_to_audit_read(self):
        from app.api.policy.permission_map import match_permission
        perm = match_permission("GET", "/evidence-workbench/draft/1")
        assert perm == "audit:read"

    def test_post_maps_to_audit_read(self):
        from app.api.policy.permission_map import match_permission
        perm = match_permission("POST", "/evidence-workbench/link")
        assert perm == "audit:read"


# ---------------------------------------------------------------------------
# 7. Router registry
# ---------------------------------------------------------------------------
class TestEvidenceWorkbenchRegistry:
    def test_router_registered(self):
        import pathlib
        src = pathlib.Path("app/core/router_registry.py").read_text(encoding="utf-8")
        assert "routes_evidence_workbench" in src

    def test_service_importable(self):
        import importlib
        mod = importlib.import_module("app.api.services.evidence_workbench_service")
        assert hasattr(mod, "list_bundles_for_draft")
        assert hasattr(mod, "list_drafts_without_evidence")
        assert hasattr(mod, "get_evidence_summary")
        assert hasattr(mod, "link_document_to_draft")
