"""app/api/services/rsge_config.py
Bridge Hub — RS.ge connector safety configuration.

All flags default to safe/off. Live RS.ge mutations require every
gate to be explicitly enabled via environment variables.
"""
from __future__ import annotations

import os

# ── Environment flag helpers ──────────────────────────────────────────────────

def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default).lower()).strip().lower() == "true"


# ── Public API ────────────────────────────────────────────────────────────────

def is_enabled() -> bool:
    """Return True only when RSGE_ENABLED=true. Off by default."""
    return _flag("RSGE_ENABLED", False)


def live_actions_enabled() -> bool:
    """Return True only when RSGE_LIVE_ACTIONS_ENABLED=true. Off by default."""
    return _flag("RSGE_LIVE_ACTIONS_ENABLED", False)


def read_only() -> bool:
    """Return True when RS.ge connector is in read-only mode (default: True)."""
    return _flag("RSGE_READ_ONLY", True)


def dry_run() -> bool:
    """Return True when RS.ge connector runs in dry-run mode (default: True)."""
    return _flag("RSGE_DRY_RUN", True)


def test_mode() -> bool:
    """Return True when running in test/CI mode (RSGE_TEST_MODE=true)."""
    return _flag("RSGE_TEST_MODE", False)


# ── Action-specific gates ─────────────────────────────────────────────────────

_ACTION_FLAGS: dict[str, str] = {
    "confirm":        "RSGE_ALLOW_CONFIRM",
    "reject":         "RSGE_ALLOW_REJECT",
    "cancel":         "RSGE_ALLOW_CANCEL",
    "correct":        "RSGE_ALLOW_CORRECT",
    "activate":       "RSGE_ALLOW_ACTIVATE",
    "waybill_action": "RSGE_ALLOW_WAYBILL_ACTIONS",
}


def allow_action(action_type: str) -> bool:
    """Return True only when ALL live-action gates pass AND action flag is set.

    All five conditions must be true:
      1. RSGE_ENABLED=true
      2. RSGE_READ_ONLY=false
      3. RSGE_DRY_RUN=false
      4. RSGE_LIVE_ACTIONS_ENABLED=true
      5. action-specific flag is true (e.g. RSGE_ALLOW_CONFIRM=true)
    """
    if not is_enabled():
        return False
    if read_only():
        return False
    if dry_run():
        return False
    if not live_actions_enabled():
        return False

    env_flag = _ACTION_FLAGS.get(action_type.lower())
    if env_flag is None:
        return False
    return _flag(env_flag, False)
