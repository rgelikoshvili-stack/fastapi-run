"""tests/unit/test_phase3_14_bank_brain.py — Task 14: Bank Brain.

Covers:
  1. extract_match_patterns — pure function
  2. suggest_categories_for_unmatched — pure function
  3. bucket_by_age — pure function
  4. compute_reconciliation_health (mocked DB)
  5. get_aged_unreconciled (mocked DB)
  6. Routes: importable, prefix, permission checks
  7. Permission map and registry
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ctx(fetchrow=None, fetch=None, fetchval=None):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow)
    conn.fetch    = AsyncMock(return_value=fetch or [])
    conn.fetchval = AsyncMock(return_value=fetchval)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__  = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# 1. extract_match_patterns
# ---------------------------------------------------------------------------
class TestExtractMatchPatterns:
    def test_empty_list_returns_empty(self):
        from app.api.services.bank_brain_service import extract_match_patterns
        assert extract_match_patterns([]) == []

    def test_single_match_creates_pattern(self):
        from app.api.services.bank_brain_service import extract_match_patterns
        matched = [{"matched_draft": {"partner": "TBC Bank", "account_code": "1120", "amount": 500}}]
        patterns = extract_match_patterns(matched)
        assert len(patterns) == 1
        assert patterns[0]["partner"] == "tbc bank"
        assert patterns[0]["account_code"] == "1120"
        assert patterns[0]["occurrences"] == 1

    def test_same_partner_aggregated(self):
        from app.api.services.bank_brain_service import extract_match_patterns
        matched = [
            {"matched_draft": {"partner": "Vendor A", "account_code": "3110", "amount": 100}},
            {"matched_draft": {"partner": "Vendor A", "account_code": "3110", "amount": 200}},
        ]
        patterns = extract_match_patterns(matched)
        assert len(patterns) == 1
        assert patterns[0]["occurrences"] == 2
        assert patterns[0]["avg_amount"] == 150.0

    def test_sorted_by_occurrences_descending(self):
        from app.api.services.bank_brain_service import extract_match_patterns
        matched = [
            {"matched_draft": {"partner": "Rare", "account_code": "7910", "amount": 50}},
            {"matched_draft": {"partner": "Common", "account_code": "3110", "amount": 100}},
            {"matched_draft": {"partner": "Common", "account_code": "3110", "amount": 100}},
        ]
        patterns = extract_match_patterns(matched)
        assert patterns[0]["partner"] == "common"
        assert patterns[0]["occurrences"] == 2

    def test_missing_partner_skipped(self):
        from app.api.services.bank_brain_service import extract_match_patterns
        matched = [{"matched_draft": {"partner": "", "account_code": "3110", "amount": 100}}]
        assert extract_match_patterns(matched) == []


# ---------------------------------------------------------------------------
# 2. suggest_categories_for_unmatched
# ---------------------------------------------------------------------------
class TestSuggestCategories:
    def test_no_patterns_returns_none_suggestions(self):
        from app.api.services.bank_brain_service import suggest_categories_for_unmatched
        txns = [{"description": "Payment to TBC"}]
        result = suggest_categories_for_unmatched(txns, [])
        assert result[0]["suggested_account"] is None

    def test_matching_pattern_fills_suggestion(self):
        from app.api.services.bank_brain_service import suggest_categories_for_unmatched
        txns = [{"description": "tbc bank fee"}]
        patterns = [{"partner": "tbc bank", "account_code": "1120", "occurrences": 5}]
        result = suggest_categories_for_unmatched(txns, patterns)
        assert result[0]["suggested_account"] == "1120"

    def test_high_confidence_when_occurrences_gte_3(self):
        from app.api.services.bank_brain_service import suggest_categories_for_unmatched
        txns = [{"description": "vendor a payment"}]
        patterns = [{"partner": "vendor a", "account_code": "3110", "occurrences": 4}]
        result = suggest_categories_for_unmatched(txns, patterns)
        assert result[0]["suggestion_confidence"] == "high"

    def test_low_confidence_when_occurrences_lt_3(self):
        from app.api.services.bank_brain_service import suggest_categories_for_unmatched
        txns = [{"description": "vendor b payment"}]
        patterns = [{"partner": "vendor b", "account_code": "3110", "occurrences": 1}]
        result = suggest_categories_for_unmatched(txns, patterns)
        assert result[0]["suggestion_confidence"] == "low"

    def test_no_match_on_unrelated_description(self):
        from app.api.services.bank_brain_service import suggest_categories_for_unmatched
        txns = [{"description": "some random payment xyz"}]
        patterns = [{"partner": "tbc bank", "account_code": "1120", "occurrences": 10}]
        result = suggest_categories_for_unmatched(txns, patterns)
        assert result[0]["suggested_account"] is None


# ---------------------------------------------------------------------------
# 3. bucket_by_age
# ---------------------------------------------------------------------------
class TestBucketByAge:
    def test_recent_item_in_0_30d(self):
        from app.api.services.bank_brain_service import bucket_by_age
        today = date.today()
        items = [{"created_at": today.isoformat(), "amount": 100}]
        buckets = bucket_by_age(items, reference_date=today)
        assert len(buckets["0_30d"]) == 1

    def test_old_item_in_over_90d(self):
        from app.api.services.bank_brain_service import bucket_by_age
        today = date.today()
        old = (today - timedelta(days=100)).isoformat()
        items = [{"created_at": old, "amount": 100}]
        buckets = bucket_by_age(items, reference_date=today)
        assert len(buckets["over_90d"]) == 1

    def test_31_60d_bucket(self):
        from app.api.services.bank_brain_service import bucket_by_age
        today = date.today()
        d = (today - timedelta(days=45)).isoformat()
        buckets = bucket_by_age([{"created_at": d}], reference_date=today)
        assert len(buckets["31_60d"]) == 1

    def test_empty_input(self):
        from app.api.services.bank_brain_service import bucket_by_age
        buckets = bucket_by_age([])
        assert all(len(v) == 0 for v in buckets.values())


# ---------------------------------------------------------------------------
# 4. compute_reconciliation_health (mocked DB)
# ---------------------------------------------------------------------------
class TestComputeReconciliationHealth:
    @pytest.mark.asyncio
    async def test_healthy_when_rate_ge_90(self):
        from app.api.services.bank_brain_service import compute_reconciliation_health
        row = {"total_drafts": 10, "reconciled_count": 9, "unreconciled_count": 1,
               "unreconciled_amount": 100, "total_amount": 5000}
        with patch("app.api.services.bank_brain_service.get_conn", return_value=_ctx(fetchrow=row)):
            result = await compute_reconciliation_health("t1", "2026-01")
        assert result["health_status"] == "healthy"
        assert result["reconciliation_rate_pct"] == 90.0

    @pytest.mark.asyncio
    async def test_critical_when_rate_lt_70(self):
        from app.api.services.bank_brain_service import compute_reconciliation_health
        row = {"total_drafts": 10, "reconciled_count": 5, "unreconciled_count": 5,
               "unreconciled_amount": 2000, "total_amount": 5000}
        with patch("app.api.services.bank_brain_service.get_conn", return_value=_ctx(fetchrow=row)):
            result = await compute_reconciliation_health("t1", "2026-01")
        assert result["health_status"] == "critical"

    @pytest.mark.asyncio
    async def test_returns_month_in_result(self):
        from app.api.services.bank_brain_service import compute_reconciliation_health
        row = {"total_drafts": 0, "reconciled_count": 0, "unreconciled_count": 0,
               "unreconciled_amount": 0, "total_amount": 0}
        with patch("app.api.services.bank_brain_service.get_conn", return_value=_ctx(fetchrow=row)):
            result = await compute_reconciliation_health("t1", "2026-06")
        assert result["month"] == "2026-06"

    @pytest.mark.asyncio
    async def test_100_percent_when_no_drafts(self):
        from app.api.services.bank_brain_service import compute_reconciliation_health
        row = {"total_drafts": 0, "reconciled_count": 0, "unreconciled_count": 0,
               "unreconciled_amount": 0, "total_amount": 0}
        with patch("app.api.services.bank_brain_service.get_conn", return_value=_ctx(fetchrow=row)):
            result = await compute_reconciliation_health("t1")
        assert result["reconciliation_rate_pct"] == 100.0


# ---------------------------------------------------------------------------
# 5. Routes
# ---------------------------------------------------------------------------
class TestBankBrainRoutes:
    def test_router_importable(self):
        import importlib
        mod = importlib.import_module("app.api.routes_bank_brain")
        assert hasattr(mod, "router")

    def test_router_prefix(self):
        from app.api.routes_bank_brain import router
        assert router.prefix == "/bank-brain"

    def test_health_requires_bank_process(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_bank_brain.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "reconciliation_health":
                assert "bank:process" in ast.unparse(node)
                return
        pytest.fail("reconciliation_health not found")

    def test_suggest_requires_bank_process(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_bank_brain.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "suggest_categories":
                assert "bank:process" in ast.unparse(node)
                return
        pytest.fail("suggest_categories not found")


# ---------------------------------------------------------------------------
# 6. Permission map and registry
# ---------------------------------------------------------------------------
class TestBankBrainRegistration:
    def test_permission_map_has_bank_brain(self):
        import pathlib
        src = pathlib.Path("app/api/policy/permission_map.py").read_text(encoding="utf-8")
        assert "/bank-brain" in src

    def test_get_bank_brain_maps_to_bank_process(self):
        from app.api.policy.permission_map import match_permission
        assert match_permission("GET", "/bank-brain/health") == "bank:process"

    def test_router_registered(self):
        import pathlib
        src = pathlib.Path("app/core/router_registry.py").read_text(encoding="utf-8")
        assert "routes_bank_brain" in src

    def test_service_importable(self):
        import importlib
        mod = importlib.import_module("app.api.services.bank_brain_service")
        assert hasattr(mod, "extract_match_patterns")
        assert hasattr(mod, "suggest_categories_for_unmatched")
        assert hasattr(mod, "bucket_by_age")
        assert hasattr(mod, "compute_reconciliation_health")
        assert hasattr(mod, "get_aged_unreconciled")
        assert hasattr(mod, "get_bank_brain_summary")
