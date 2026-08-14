"""RS.ge connector configuration and production safety gates.

Defaults are intentionally closed:
- connector disabled
- read-only enabled
- dry-run enabled
- live actions disabled
"""
from __future__ import annotations

import os


_ACTION_FLAGS = {
    "confirm": "RSGE_ALLOW_CONFIRM",
    "reject": "RSGE_ALLOW_REJECT",
    "cancel": "RSGE_ALLOW_CANCEL",
    "correct": "RSGE_ALLOW_CORRECT",
    "activate": "RSGE_ALLOW_ACTIVATE",
    "waybill": "RSGE_ALLOW_WAYBILL_ACTIONS",
    "waybill_confirm": "RSGE_ALLOW_WAYBILL_ACTIONS",
    "waybill_cancel": "RSGE_ALLOW_WAYBILL_ACTIONS",
    "waybill_correct": "RSGE_ALLOW_WAYBILL_ACTIONS",
}


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def environment() -> str:
    return os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or os.getenv("ENV") or "development"


def is_production() -> bool:
    return environment().strip().lower() == "production"


def is_enabled() -> bool:
    return _flag("RSGE_ENABLED", False) or _flag("RSGE_CONNECTOR_ENABLED", False)


def live_actions_enabled() -> bool:
    return _flag("RSGE_LIVE_ACTIONS_ENABLED", False)


def read_only() -> bool:
    return _flag("RSGE_READ_ONLY", True)


def dry_run() -> bool:
    return _flag("RSGE_DRY_RUN", True)


def test_mode() -> bool:
    default = os.getenv("TEST_MODE", "").strip() == "1"
    return _flag("RSGE_TEST_MODE", default)


def allow_action(action_type: str) -> bool:
    """Return True only when live RS.ge mutations are explicitly enabled."""
    action = (action_type or "").strip().lower()
    action_flag = _ACTION_FLAGS.get(action)
    if not action_flag:
        return False
    if not is_enabled():
        return False
    if read_only() or dry_run():
        return False
    if not live_actions_enabled():
        return False
    if not _flag(action_flag, False):
        return False
    if is_production() and not _flag("RSGE_FINAL_APPROVAL_RECORDED", False):
        return False
    return True
