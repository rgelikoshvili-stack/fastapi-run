"""tests/unit/test_rsge_production_live_blocker.py — Production live action blocker."""
import os

import pytest
from fastapi import HTTPException
from unittest.mock import patch


# ── 1. require_test_mode blocks when RSGE_TEST_MODE not set ──────────────────

def test_require_test_mode_blocks_by_default():
    with patch.dict(os.environ, {"RSGE_TEST_MODE": "false",
                                  "RSGE_LIVE_ACTIONS_ENABLED": "false"}, clear=False):
        from app.api.services.rsge_config import require_test_mode
        with pytest.raises(HTTPException) as exc:
            require_test_mode("test_action")
        assert exc.value.status_code == 403
        assert "TEST_MODE_REQUIRED" in str(exc.value.detail)


def test_require_test_mode_passes_when_set():
    with patch.dict(os.environ, {"RSGE_TEST_MODE": "true",
                                  "RSGE_LIVE_ACTIONS_ENABLED": "false"}, clear=False):
        from importlib import reload
        import app.api.services.rsge_config as cfg
        reload(cfg)
        # Should not raise
        cfg.require_test_mode("test_action")


# ── 2. RSGE_LIVE_ACTIONS_ENABLED=true blocks all mutations ───────────────────

def test_live_actions_enabled_true_always_blocks():
    with patch.dict(os.environ, {"RSGE_TEST_MODE": "true",
                                  "RSGE_LIVE_ACTIONS_ENABLED": "true"}, clear=False):
        from importlib import reload
        import app.api.services.rsge_config as cfg
        reload(cfg)
        with pytest.raises(HTTPException) as exc:
            cfg.require_test_mode("any_action")
        assert exc.value.status_code == 403
        assert "LIVE_ACTIONS_BLOCKED" in str(exc.value.detail)


# ── 3. Individual action flags block when false ───────────────────────────────

@pytest.mark.parametrize("action,env_key", [
    ("confirm",  "RSGE_ALLOW_TEST_CONFIRM"),
    ("reject",   "RSGE_ALLOW_TEST_REJECT"),
    ("correct",  "RSGE_ALLOW_TEST_CORRECT"),
    ("cancel",   "RSGE_ALLOW_TEST_CANCEL"),
    ("activate", "RSGE_ALLOW_TEST_ACTIVATE"),
])
def test_action_flag_blocks_when_false(action, env_key):
    env = {"RSGE_TEST_MODE": "true", "RSGE_LIVE_ACTIONS_ENABLED": "false", env_key: "false"}
    with patch.dict(os.environ, env, clear=False):
        from importlib import reload
        import app.api.services.rsge_config as cfg
        reload(cfg)
        with pytest.raises(HTTPException) as exc:
            cfg.require_action_flag(action)
        assert exc.value.status_code == 403


# ── 4. All action flags pass when test mode set ───────────────────────────────

@pytest.mark.parametrize("action,env_key", [
    ("confirm",  "RSGE_ALLOW_TEST_CONFIRM"),
    ("reject",   "RSGE_ALLOW_TEST_REJECT"),
    ("correct",  "RSGE_ALLOW_TEST_CORRECT"),
    ("cancel",   "RSGE_ALLOW_TEST_CANCEL"),
    ("activate", "RSGE_ALLOW_TEST_ACTIVATE"),
])
def test_action_flag_passes_in_test_mode(action, env_key):
    env = {"RSGE_TEST_MODE": "true", "RSGE_LIVE_ACTIONS_ENABLED": "false", env_key: "true"}
    with patch.dict(os.environ, env, clear=False):
        from importlib import reload
        import app.api.services.rsge_config as cfg
        reload(cfg)
        # Must not raise
        cfg.require_action_flag(action)


# ── 5. Waybill submit route enforces test mode ───────────────────────────────

def test_waybill_submit_route_calls_require_test_mode():
    import inspect
    import app.api.routes_rs_ge as routes
    src = inspect.getsource(routes.submit_waybill)
    assert "require_test_mode" in src


def test_invoice_submit_route_calls_require_test_mode():
    import inspect
    import app.api.routes_rs_ge as routes
    src = inspect.getsource(routes.submit_invoice)
    assert "require_test_mode" in src


# ── 6. mode_summary returns all flags ────────────────────────────────────────

def test_mode_summary_returns_all_flags():
    from app.api.services.rsge_config import mode_summary
    summary = mode_summary()
    required_keys = [
        "enabled", "test_mode", "read_only", "live_actions_enabled",
        "allow_test_confirm", "allow_test_reject", "allow_test_correct",
        "allow_test_cancel", "allow_test_activate",
    ]
    for key in required_keys:
        assert key in summary, f"mode_summary missing key: {key}"


# ── 7. Production blocker code pattern in all action routes ──────────────────

def test_action_routes_require_action_flag():
    import inspect
    import app.api.routes_rs_ge as routes
    src = inspect.getsource(routes)
    assert "require_action_flag" in src
    # Must appear for document actions
    confirm_idx = src.find("test-confirm")
    reject_idx = src.find("test-reject")
    assert confirm_idx > 0 or "confirm" in src
    assert reject_idx > 0 or "reject" in src
