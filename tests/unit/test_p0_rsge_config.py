"""tests/unit/test_p0_rsge_config.py
P0-3: rsge_config.py safety defaults.
All tests are pure Python — no DB, no network.
"""
import os
import pytest
from unittest.mock import patch


def _import():
    from app.api.services import rsge_config
    return rsge_config


# ── Default safety ────────────────────────────────────────────────────────────

def test_is_enabled_false_by_default():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("RSGE_ENABLED", None)
        rc = _import()
        assert rc.is_enabled() is False


def test_live_actions_enabled_false_by_default():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("RSGE_LIVE_ACTIONS_ENABLED", None)
        rc = _import()
        assert rc.live_actions_enabled() is False


def test_read_only_true_by_default():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("RSGE_READ_ONLY", None)
        rc = _import()
        assert rc.read_only() is True


def test_dry_run_true_by_default():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("RSGE_DRY_RUN", None)
        rc = _import()
        assert rc.dry_run() is True


def test_test_mode_false_by_default():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("RSGE_TEST_MODE", None)
        rc = _import()
        assert rc.test_mode() is False


# ── allow_action defaults ─────────────────────────────────────────────────────

@pytest.mark.parametrize("action", [
    "confirm", "reject", "cancel", "correct", "activate", "waybill_action",
])
def test_allow_action_false_by_default(action):
    env_clean = {
        k: v for k, v in os.environ.items()
        if not k.startswith("RSGE_")
    }
    with patch.dict(os.environ, env_clean, clear=True):
        rc = _import()
        assert rc.allow_action(action) is False, f"allow_action('{action}') should be False by default"


def test_allow_action_false_for_unknown():
    with patch.dict(os.environ, {"RSGE_ENABLED": "true", "RSGE_LIVE_ACTIONS_ENABLED": "true",
                                  "RSGE_READ_ONLY": "false", "RSGE_DRY_RUN": "false"}, clear=False):
        rc = _import()
        assert rc.allow_action("unknown_action") is False


# ── Flag hierarchy: all gates must pass ───────────────────────────────────────

def test_allow_action_requires_all_gates():
    """Even with action-specific flag set, requires RSGE_ENABLED + READ_ONLY=false + DRY_RUN=false."""
    # Only set the action flag — no top-level gates
    with patch.dict(os.environ, {"RSGE_ALLOW_CONFIRM": "true"}, clear=False):
        for k in ["RSGE_ENABLED", "RSGE_LIVE_ACTIONS_ENABLED", "RSGE_READ_ONLY", "RSGE_DRY_RUN"]:
            os.environ.pop(k, None)
        rc = _import()
        assert rc.allow_action("confirm") is False


def test_allow_action_true_when_all_gates_set():
    env = {
        "RSGE_ENABLED": "true",
        "RSGE_READ_ONLY": "false",
        "RSGE_DRY_RUN": "false",
        "RSGE_LIVE_ACTIONS_ENABLED": "true",
        "RSGE_ALLOW_CONFIRM": "true",
    }
    with patch.dict(os.environ, env, clear=False):
        rc = _import()
        assert rc.allow_action("confirm") is True


def test_allow_action_blocked_if_read_only_still_set():
    env = {
        "RSGE_ENABLED": "true",
        "RSGE_READ_ONLY": "true",   # still read-only
        "RSGE_DRY_RUN": "false",
        "RSGE_LIVE_ACTIONS_ENABLED": "true",
        "RSGE_ALLOW_CONFIRM": "true",
    }
    with patch.dict(os.environ, env, clear=False):
        rc = _import()
        assert rc.allow_action("confirm") is False


def test_allow_action_blocked_if_dry_run_still_set():
    env = {
        "RSGE_ENABLED": "true",
        "RSGE_READ_ONLY": "false",
        "RSGE_DRY_RUN": "true",    # still dry-run
        "RSGE_LIVE_ACTIONS_ENABLED": "true",
        "RSGE_ALLOW_CONFIRM": "true",
    }
    with patch.dict(os.environ, env, clear=False):
        rc = _import()
        assert rc.allow_action("confirm") is False


# ── Case insensitivity ────────────────────────────────────────────────────────

def test_allow_action_case_insensitive():
    env = {
        "RSGE_ENABLED": "true",
        "RSGE_READ_ONLY": "false",
        "RSGE_DRY_RUN": "false",
        "RSGE_LIVE_ACTIONS_ENABLED": "true",
        "RSGE_ALLOW_WAYBILL_ACTIONS": "true",
    }
    with patch.dict(os.environ, env, clear=False):
        rc = _import()
        assert rc.allow_action("WAYBILL_ACTION") is True
        assert rc.allow_action("Waybill_Action") is True
