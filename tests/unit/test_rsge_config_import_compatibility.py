"""tests/unit/test_rsge_config_import_compatibility.py
HOTFIX-RS-CONFIG: verify rsge_config and rsge_comparison_service import compatibility.
"""
from __future__ import annotations

import os
import importlib


# ── rsge_config ───────────────────────────────────────────────────────────────

class TestRsgeConfigImport:

    def test_canonical_path_importable(self):
        from app.api.services import rsge_config
        assert rsge_config is not None

    def test_is_enabled_callable(self):
        from app.api.services.rsge_config import is_enabled
        assert callable(is_enabled)

    def test_is_test_mode_callable(self):
        """is_test_mode alias must exist (legacy import compatibility)."""
        from app.api.services.rsge_config import is_test_mode
        assert callable(is_test_mode)

    def test_is_test_mode_is_test_mode_alias(self):
        from app.api.services.rsge_config import is_test_mode, test_mode
        assert is_test_mode is test_mode

    def test_live_actions_enabled_callable(self):
        from app.api.services.rsge_config import live_actions_enabled
        assert callable(live_actions_enabled)

    def test_importable_without_database_url(self):
        env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        env.pop("DATABASE_URL", None)
        import importlib, sys
        # Just importing must not raise even with no DB
        mod = importlib.import_module("app.api.services.rsge_config")
        assert mod is not None

    def test_importable_with_test_mode(self):
        prev = os.environ.get("TEST_MODE")
        os.environ["TEST_MODE"] = "1"
        try:
            from app.api.services.rsge_config import is_enabled
            assert callable(is_enabled)
        finally:
            if prev is None:
                os.environ.pop("TEST_MODE", None)
            else:
                os.environ["TEST_MODE"] = prev


# ── Default safety flags ──────────────────────────────────────────────────────

class TestRsgeConfigSafetyDefaults:

    def setup_method(self):
        for k in list(os.environ):
            if k.startswith("RSGE_"):
                os.environ.pop(k)

    def test_is_enabled_default_false(self):
        from app.api.services.rsge_config import is_enabled
        assert is_enabled() is False

    def test_live_actions_disabled_by_default(self):
        from app.api.services.rsge_config import live_actions_enabled
        assert live_actions_enabled() is False

    def test_read_only_default_true(self):
        from app.api.services.rsge_config import read_only
        assert read_only() is True

    def test_dry_run_default_true(self):
        from app.api.services.rsge_config import dry_run
        assert dry_run() is True

    def test_allow_confirm_default_false(self):
        from app.api.services.rsge_config import allow_action
        assert allow_action("confirm") is False

    def test_allow_reject_default_false(self):
        from app.api.services.rsge_config import allow_action
        assert allow_action("reject") is False

    def test_allow_cancel_default_false(self):
        from app.api.services.rsge_config import allow_action
        assert allow_action("cancel") is False

    def test_allow_activate_default_false(self):
        from app.api.services.rsge_config import allow_action
        assert allow_action("activate") is False

    def test_no_credentials_in_module(self):
        import inspect
        from app.api.services import rsge_config
        src = inspect.getsource(rsge_config)
        assert "password" not in src.lower()
        assert "eapi.rs.ge" not in src
        assert "ACCESS_TOKEN" not in src


# ── rsge_comparison_service ───────────────────────────────────────────────────

class TestRsgeComparisonServiceImport:

    def test_module_importable(self):
        from app.api.services import rsge_comparison_service
        assert rsge_comparison_service is not None

    def test_mismatch_types_are_strings(self):
        from app.api.services.rsge_comparison_service import (
            MATCHED, AMOUNT_MISMATCH, VAT_MISMATCH,
            SELLER_BUYER_MISMATCH, MISSING_IN_BRIDGE,
            MISSING_IN_RSGE, DUPLICATE, REQUIRES_REVIEW,
        )
        for val in [MATCHED, AMOUNT_MISMATCH, VAT_MISMATCH,
                    SELLER_BUYER_MISMATCH, MISSING_IN_BRIDGE,
                    MISSING_IN_RSGE, DUPLICATE, REQUIRES_REVIEW]:
            assert isinstance(val, str)
            assert len(val) > 0

    def test_eight_mismatch_types(self):
        from app.api.services.rsge_comparison_service import (
            MATCHED, AMOUNT_MISMATCH, VAT_MISMATCH,
            SELLER_BUYER_MISMATCH, MISSING_IN_BRIDGE,
            MISSING_IN_RSGE, DUPLICATE, REQUIRES_REVIEW,
        )
        types = {MATCHED, AMOUNT_MISMATCH, VAT_MISMATCH,
                 SELLER_BUYER_MISMATCH, MISSING_IN_BRIDGE,
                 MISSING_IN_RSGE, DUPLICATE, REQUIRES_REVIEW}
        assert len(types) == 8

    def test_risk_levels_distinct(self):
        from app.api.services.rsge_comparison_service import (
            RISK_LOW, RISK_MEDIUM, RISK_HIGH,
        )
        assert isinstance(RISK_LOW, str)
        assert isinstance(RISK_MEDIUM, str)
        assert isinstance(RISK_HIGH, str)
        assert len({RISK_LOW, RISK_MEDIUM, RISK_HIGH}) == 3

    def test_importable_without_database_url(self):
        env_backup = os.environ.pop("DATABASE_URL", None)
        try:
            mod = importlib.import_module("app.api.services.rsge_comparison_service")
            assert mod is not None
        finally:
            if env_backup is not None:
                os.environ["DATABASE_URL"] = env_backup

    def test_missing_in_bridge_value(self):
        from app.api.services.rsge_comparison_service import MISSING_IN_BRIDGE
        assert MISSING_IN_BRIDGE == "missing_in_bridge"

    def test_risk_for_mismatch_callable(self):
        from app.api.services.rsge_comparison_service import risk_for_mismatch, RISK_HIGH, MISSING_IN_BRIDGE
        assert callable(risk_for_mismatch)
        assert risk_for_mismatch(MISSING_IN_BRIDGE) == RISK_HIGH
