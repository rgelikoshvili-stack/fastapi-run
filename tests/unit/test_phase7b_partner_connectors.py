"""tests/unit/test_phase7b_partner_connectors.py — Phase 7b: Partner + Connectors.

Covers:
  1. ORIS connector — demo mode status/preview/post
  2. FINA connector — demo mode
  3. APEX connector — demo mode
  4. erp_dispatch KNOWN_CONNECTORS has fina + apex
  5. partner_service — register, mask_key, get_profile, branding
  6. Routes: partner importable, prefix, permissions
  7. Permission map and registry
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. ORIS connector demo mode
# ---------------------------------------------------------------------------
class TestOrisConnector:
    def test_demo_mode_connected(self):
        from app.api.connectors.oris_connector import OrisConnector
        c = OrisConnector()
        assert c.mode == "demo"
        assert c.status()["connected"] is True

    def test_demo_preview_valid(self):
        from app.api.connectors.oris_connector import OrisConnector
        c = OrisConnector()
        result = c.preview({"lines": [{"account": "1120"}], "amount": 100})
        assert result["valid"] is True

    def test_demo_preview_invalid_no_lines(self):
        from app.api.connectors.oris_connector import OrisConnector
        c = OrisConnector()
        result = c.preview({"amount": 100})
        assert result["valid"] is False

    def test_demo_post_returns_success(self):
        from app.api.connectors.oris_connector import OrisConnector
        c = OrisConnector()
        result = c.post({"lines": [{"account": "1120"}], "amount": 100})
        assert result["success"] is True
        assert "ORIS-DEMO" in result["erp_id"]

    def test_demo_history_empty(self):
        from app.api.connectors.oris_connector import OrisConnector
        c = OrisConnector()
        assert c.history("t1") == []


# ---------------------------------------------------------------------------
# 2. FINA connector demo mode
# ---------------------------------------------------------------------------
class TestFinaConnector:
    def test_demo_mode_connected(self):
        from app.api.connectors.fina_connector import FinaConnector
        c = FinaConnector()
        assert c.mode == "demo"
        assert c.status()["connected"] is True

    def test_demo_post_returns_success(self):
        from app.api.connectors.fina_connector import FinaConnector
        c = FinaConnector()
        result = c.post({"lines": [{"account": "1120"}], "amount": 500, "description": "Test"})
        assert result["success"] is True
        assert "FINA-DEMO" in result["erp_id"]

    def test_preview_no_description_invalid(self):
        from app.api.connectors.fina_connector import FinaConnector
        c = FinaConnector()
        result = c.preview({"lines": [{"account": "1120"}], "amount": 100})
        assert result["valid"] is False
        assert any("description" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# 3. APEX connector demo mode
# ---------------------------------------------------------------------------
class TestApexConnector:
    def test_demo_mode_connected(self):
        from app.api.connectors.apex_connector import ApexConnector
        c = ApexConnector()
        assert c.mode == "demo"
        assert c.status()["connected"] is True

    def test_demo_post_returns_success(self):
        from app.api.connectors.apex_connector import ApexConnector
        c = ApexConnector()
        result = c.post({"lines": [{"account": "1120"}], "amount": 200})
        assert result["success"] is True
        assert "APEX-DEMO" in result["erp_id"]

    def test_validate_config_demo_true(self):
        from app.api.connectors.apex_connector import ApexConnector
        assert ApexConnector().validate_config() is True


# ---------------------------------------------------------------------------
# 4. erp_dispatch KNOWN_CONNECTORS updated
# ---------------------------------------------------------------------------
class TestKnownConnectors:
    def test_fina_in_known_connectors(self):
        from app.api.services.erp_dispatch_service import KNOWN_CONNECTORS
        assert "fina" in KNOWN_CONNECTORS

    def test_apex_in_known_connectors(self):
        from app.api.services.erp_dispatch_service import KNOWN_CONNECTORS
        assert "apex" in KNOWN_CONNECTORS

    def test_all_five_connectors(self):
        from app.api.services.erp_dispatch_service import KNOWN_CONNECTORS
        assert set(KNOWN_CONNECTORS) >= {"balance", "1c", "oris", "fina", "apex"}


# ---------------------------------------------------------------------------
# 5. partner_service
# ---------------------------------------------------------------------------
class TestPartnerService:
    def test_generate_and_mask_key(self):
        from app.api.services.partner_service import _generate_partner_key, mask_partner_key
        key = _generate_partner_key("Test Partner")
        assert key.startswith("pk_")
        masked = mask_partner_key(key)
        assert masked.startswith("pk_...")
        assert masked.endswith(key[-4:])

    @pytest.mark.asyncio
    async def test_register_returns_api_key(self):
        from app.api.services.partner_service import register_partner
        with patch("app.api.services.partner_service.set_tenant_setting",
                   new=AsyncMock(return_value=True)):
            result = await register_partner("t1", "Acme Corp", "acme@example.com", "admin")
        assert "api_key" in result
        assert result["api_key"].startswith("pk_")
        assert "warning" in result

    @pytest.mark.asyncio
    async def test_get_profile_returns_none_when_missing(self):
        from app.api.services.partner_service import get_partner_profile
        with patch("app.api.services.partner_service.get_tenant_setting",
                   new=AsyncMock(return_value=None)):
            result = await get_partner_profile("t1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_branding_merges_defaults(self):
        from app.api.services.partner_service import get_branding
        with patch("app.api.services.partner_service.get_tenant_setting",
                   new=AsyncMock(return_value={"product_name": "MyApp"})):
            result = await get_branding("t1")
        assert result["product_name"] == "MyApp"
        assert result["primary_color"] == "#2563eb"  # default retained

    @pytest.mark.asyncio
    async def test_set_branding_saves_valid_fields(self):
        from app.api.services.partner_service import set_branding
        with patch("app.api.services.partner_service.get_tenant_setting",
                   new=AsyncMock(return_value={})), \
             patch("app.api.services.partner_service.set_tenant_setting",
                   new=AsyncMock(return_value=True)):
            result = await set_branding("t1", {"product_name": "MyERP", "primary_color": "#ff0000"})
        assert result["product_name"] == "MyERP"

    @pytest.mark.asyncio
    async def test_set_branding_unknown_field_ignored(self):
        from app.api.services.partner_service import set_branding
        with patch("app.api.services.partner_service.get_tenant_setting",
                   new=AsyncMock(return_value={})), \
             patch("app.api.services.partner_service.set_tenant_setting",
                   new=AsyncMock(return_value=True)):
            result = await set_branding("t1", {"product_name": "MyERP", "hack_field": "bad"})
        assert "hack_field" not in result

    @pytest.mark.asyncio
    async def test_set_branding_empty_raises(self):
        from app.api.services.partner_service import set_branding
        with pytest.raises(ValueError, match="NO_VALID_FIELDS"):
            with patch("app.api.services.partner_service.get_tenant_setting",
                       new=AsyncMock(return_value={})):
                await set_branding("t1", {"unknown": "value"})


# ---------------------------------------------------------------------------
# 6. Routes
# ---------------------------------------------------------------------------
class TestPartnerRoutes:
    def test_router_importable(self):
        import importlib
        mod = importlib.import_module("app.api.routes_partner")
        assert hasattr(mod, "router")

    def test_router_prefix(self):
        from app.api.routes_partner import router
        assert router.prefix == "/partner"

    def test_register_requires_tenants_manage(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_partner.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "register":
                assert "tenants:manage" in ast.unparse(node)
                return
        pytest.fail("register not found")

    def test_branding_get_requires_reports_read(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_partner.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_brand":
                assert "reports:read" in ast.unparse(node)
                return
        pytest.fail("get_brand not found")


# ---------------------------------------------------------------------------
# 7. Permission map and registry
# ---------------------------------------------------------------------------
class TestPartnerRegistration:
    def test_permission_map_has_partner(self):
        import pathlib
        src = pathlib.Path("app/api/policy/permission_map.py").read_text(encoding="utf-8")
        assert '"/partner"' in src or "'/partner'" in src

    def test_get_partner_maps_reports_read(self):
        from app.api.policy.permission_map import match_permission
        assert match_permission("GET", "/partner/branding") == "reports:read"

    def test_post_partner_maps_tenants_manage(self):
        from app.api.policy.permission_map import match_permission
        assert match_permission("POST", "/partner/register") == "tenants:manage"

    def test_router_registered(self):
        import pathlib
        src = pathlib.Path("app/core/router_registry.py").read_text(encoding="utf-8")
        assert "routes_partner" in src
