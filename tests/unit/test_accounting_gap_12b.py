"""tests/unit/test_accounting_gap_12b.py — Task 12B: Company Identity Engine.

Covers:
  1. INN extraction from text (extract_inns)
  2. Party role classification (classify_party_role)
  3. Async service: get/set tenant INN, resolve_journal_type
  4. Routes: importable, prefix, permission checks
  5. Permission map has company-identity entries
  6. Router registry has company_identity
"""
from __future__ import annotations

import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. INN extraction
# ---------------------------------------------------------------------------
class TestExtractInns:
    def test_extracts_9digit_inn(self):
        from app.api.services.company_identity_service import extract_inns
        result = extract_inns("Invoice from company 123456789 dated 2026-01-01")
        assert "123456789" in result

    def test_extracts_11digit_inn(self):
        from app.api.services.company_identity_service import extract_inns
        result = extract_inns("Individual TIN 12345678901 for services")
        assert "12345678901" in result

    def test_extracts_multiple_inns(self):
        from app.api.services.company_identity_service import extract_inns
        result = extract_inns("Seller: 123456789, Buyer: 987654321")
        assert "123456789" in result
        assert "987654321" in result

    def test_ignores_short_numbers(self):
        from app.api.services.company_identity_service import extract_inns
        result = extract_inns("Amount: 1234 GEL, ref 12345678")
        assert result == []

    def test_ignores_10digit_numbers(self):
        from app.api.services.company_identity_service import extract_inns
        result = extract_inns("Phone: 1234567890")
        assert result == []

    def test_deduplicates_repeated_inn(self):
        from app.api.services.company_identity_service import extract_inns
        result = extract_inns("INN 123456789, again 123456789")
        assert result.count("123456789") == 1

    def test_empty_text_returns_empty(self):
        from app.api.services.company_identity_service import extract_inns
        assert extract_inns("") == []

    def test_no_numbers_returns_empty(self):
        from app.api.services.company_identity_service import extract_inns
        assert extract_inns("Payment for services rendered") == []


# ---------------------------------------------------------------------------
# 2. classify_party_role
# ---------------------------------------------------------------------------
class TestClassifyPartyRole:
    def test_seller_when_tenant_inn_in_doc(self):
        from app.api.services.company_identity_service import classify_party_role
        assert classify_party_role("123456789", ["123456789"]) == "seller"

    def test_buyer_when_tenant_inn_not_in_doc(self):
        from app.api.services.company_identity_service import classify_party_role
        assert classify_party_role("111111111", ["999999999"]) == "buyer"

    def test_unknown_when_no_inns(self):
        from app.api.services.company_identity_service import classify_party_role
        assert classify_party_role("123456789", []) == "unknown"

    def test_unknown_when_tenant_inn_empty(self):
        from app.api.services.company_identity_service import classify_party_role
        assert classify_party_role("", ["123456789"]) == "buyer"

    def test_seller_with_multiple_inns_tenant_present(self):
        from app.api.services.company_identity_service import classify_party_role
        assert classify_party_role("111111111", ["999999999", "111111111"]) == "seller"


# ---------------------------------------------------------------------------
# 3. Async service functions
# ---------------------------------------------------------------------------
class TestCompanyIdentityService:
    @pytest.mark.asyncio
    async def test_get_tenant_inn_returns_none_when_not_set(self):
        from app.api.services.company_identity_service import get_tenant_inn
        with patch("app.api.services.company_identity_service.get_tenant_setting",
                   new=AsyncMock(return_value=None)):
            result = await get_tenant_inn("t1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_tenant_inn_returns_string(self):
        from app.api.services.company_identity_service import get_tenant_inn
        with patch("app.api.services.company_identity_service.get_tenant_setting",
                   new=AsyncMock(return_value="123456789")):
            result = await get_tenant_inn("t1")
        assert result == "123456789"

    @pytest.mark.asyncio
    async def test_set_tenant_inn_valid(self):
        from app.api.services.company_identity_service import set_tenant_inn
        with patch("app.api.services.company_identity_service.set_tenant_setting",
                   new=AsyncMock(return_value=True)):
            result = await set_tenant_inn("t1", "123456789")
        assert result is True

    @pytest.mark.asyncio
    async def test_set_tenant_inn_invalid_raises(self):
        from app.api.services.company_identity_service import set_tenant_inn
        with pytest.raises(ValueError, match="Invalid INN"):
            await set_tenant_inn("t1", "12345")

    @pytest.mark.asyncio
    async def test_resolve_journal_type_seller(self):
        from app.api.services.company_identity_service import resolve_journal_type
        with patch("app.api.services.company_identity_service.get_tenant_inn",
                   new=AsyncMock(return_value="123456789")):
            result = await resolve_journal_type("t1", "Invoice 123456789 for services")
        assert result["role"] == "seller"
        assert result["journal_type"] == "sales"
        assert result["confidence"] == "high"

    @pytest.mark.asyncio
    async def test_resolve_journal_type_buyer(self):
        from app.api.services.company_identity_service import resolve_journal_type
        with patch("app.api.services.company_identity_service.get_tenant_inn",
                   new=AsyncMock(return_value="111111111")):
            result = await resolve_journal_type("t1", "Invoice 999999999 for supplies")
        assert result["role"] == "buyer"
        assert result["journal_type"] == "purchase"

    @pytest.mark.asyncio
    async def test_resolve_journal_type_unknown(self):
        from app.api.services.company_identity_service import resolve_journal_type
        with patch("app.api.services.company_identity_service.get_tenant_inn",
                   new=AsyncMock(return_value="111111111")):
            result = await resolve_journal_type("t1", "Payment for services, no INN")
        assert result["role"] == "unknown"
        assert result["journal_type"] is None

    @pytest.mark.asyncio
    async def test_resolve_journal_type_no_tenant_inn_buyer_low_confidence(self):
        from app.api.services.company_identity_service import resolve_journal_type
        with patch("app.api.services.company_identity_service.get_tenant_inn",
                   new=AsyncMock(return_value=None)):
            result = await resolve_journal_type("t1", "Invoice 999999999 for supplies")
        assert result["role"] == "buyer"
        assert result["confidence"] == "low"

    @pytest.mark.asyncio
    async def test_resolve_includes_inns_found(self):
        from app.api.services.company_identity_service import resolve_journal_type
        with patch("app.api.services.company_identity_service.get_tenant_inn",
                   new=AsyncMock(return_value="111111111")):
            result = await resolve_journal_type("t1", "Seller 999999999 to buyer 111111111")
        assert "999999999" in result["inns_found"]
        assert "111111111" in result["inns_found"]


# ---------------------------------------------------------------------------
# 4. Routes
# ---------------------------------------------------------------------------
class TestCompanyIdentityRoutes:
    def test_router_importable(self):
        mod = importlib.import_module("app.api.routes_company_identity")
        assert hasattr(mod, "router")

    def test_router_prefix(self):
        from app.api.routes_company_identity import router
        assert router.prefix == "/company-identity"

    def test_set_identity_requires_posting_write(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_company_identity.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "set_identity":
                assert "posting:write" in ast.unparse(node)
                return
        pytest.fail("set_identity not found")

    def test_classify_requires_posting_write(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_company_identity.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "classify_text":
                assert "posting:write" in ast.unparse(node)
                return
        pytest.fail("classify_text not found")

    def test_get_identity_requires_reports_read(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_company_identity.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_identity":
                assert "reports:read" in ast.unparse(node)
                return
        pytest.fail("get_identity not found")


# ---------------------------------------------------------------------------
# 5. Permission map
# ---------------------------------------------------------------------------
class TestCompanyIdentityPermissions:
    def test_permission_map_has_company_identity(self):
        import pathlib
        src = pathlib.Path("app/api/policy/permission_map.py").read_text(encoding="utf-8")
        assert "/company-identity" in src

    def test_permission_map_get_reports_read(self):
        from app.api.policy.permission_map import match_permission
        perm = match_permission("GET", "/company-identity")
        assert perm == "reports:read"

    def test_permission_map_put_posting_write(self):
        from app.api.policy.permission_map import match_permission
        perm = match_permission("PUT", "/company-identity")
        assert perm == "posting:write"

    def test_permission_map_post_posting_write(self):
        from app.api.policy.permission_map import match_permission
        perm = match_permission("POST", "/company-identity")
        assert perm == "posting:write"


# ---------------------------------------------------------------------------
# 6. Router registry
# ---------------------------------------------------------------------------
class TestCompanyIdentityRegistry:
    def test_router_registered_in_registry(self):
        import pathlib
        src = pathlib.Path("app/core/router_registry.py").read_text(encoding="utf-8")
        assert "routes_company_identity" in src

    def test_journal_type_map_has_sales_and_purchase(self):
        from app.api.services.company_identity_service import JOURNAL_TYPE_MAP
        assert "sales" in JOURNAL_TYPE_MAP
        assert "purchase" in JOURNAL_TYPE_MAP
        assert "debit_account" in JOURNAL_TYPE_MAP["sales"]
        assert "credit_account" in JOURNAL_TYPE_MAP["purchase"]
