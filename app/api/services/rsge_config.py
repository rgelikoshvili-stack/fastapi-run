"""app/api/services/rsge_config.py — RS.ge mode flags and production blocker.

Every RS.ge mutation must call require_test_mode() or require_action_flag()
before executing. No env flag → production blocked.
"""
import os
from fastapi import HTTPException

_PROVIDER = "rs_ge"


def _flag(key: str, default: str = "false") -> bool:
    return os.getenv(key, default).lower() == "true"


def is_enabled() -> bool:
    return _flag("RSGE_ENABLED")


def is_test_mode() -> bool:
    return _flag("RSGE_TEST_MODE")


def is_read_only() -> bool:
    return _flag("RSGE_READ_ONLY", "true")


def live_actions_enabled() -> bool:
    return _flag("RSGE_LIVE_ACTIONS_ENABLED")


def allow_test_confirm() -> bool:
    return is_test_mode() and _flag("RSGE_ALLOW_TEST_CONFIRM")


def allow_test_reject() -> bool:
    return is_test_mode() and _flag("RSGE_ALLOW_TEST_REJECT")


def allow_test_correct() -> bool:
    return is_test_mode() and _flag("RSGE_ALLOW_TEST_CORRECT")


def allow_test_cancel() -> bool:
    return is_test_mode() and _flag("RSGE_ALLOW_TEST_CANCEL")


def allow_test_activate() -> bool:
    return is_test_mode() and _flag("RSGE_ALLOW_TEST_ACTIVATE")


def require_test_mode(action: str = "mutation") -> None:
    """Raise 403 if not in test mode — production blocker."""
    if live_actions_enabled():
        raise HTTPException(status_code=403, detail={
            "code": "LIVE_ACTIONS_BLOCKED",
            "details": "RSGE_LIVE_ACTIONS_ENABLED must remain false; all RS.ge mutations run in test mode only",
        })
    if not is_test_mode():
        raise HTTPException(status_code=403, detail={
            "code": "TEST_MODE_REQUIRED",
            "details": f"RS.ge {action} requires RSGE_TEST_MODE=true",
        })


_ACTION_FLAGS = {
    "confirm":  allow_test_confirm,
    "reject":   allow_test_reject,
    "correct":  allow_test_correct,
    "cancel":   allow_test_cancel,
    "activate": allow_test_activate,
}


def require_action_flag(action: str) -> None:
    """Require test mode AND specific action flag."""
    require_test_mode(action)
    fn = _ACTION_FLAGS.get(action)
    if fn is None or not fn():
        raise HTTPException(status_code=403, detail={
            "code": "ACTION_NOT_ALLOWED",
            "details": f"RS.ge {action} requires RSGE_ALLOW_TEST_{action.upper()}=true",
        })


def mode_summary() -> dict:
    """Return all mode flags for status endpoint."""
    return {
        "enabled":              is_enabled(),
        "test_mode":            is_test_mode(),
        "read_only":            is_read_only(),
        "live_actions_enabled": live_actions_enabled(),
        "allow_test_confirm":   allow_test_confirm(),
        "allow_test_reject":    allow_test_reject(),
        "allow_test_correct":   allow_test_correct(),
        "allow_test_cancel":    allow_test_cancel(),
        "allow_test_activate":  allow_test_activate(),
    }


PROVIDER = _PROVIDER
SOAP_CRED_TYPE = "soap_credentials"  # stored as JSON {"su": "...", "sp": "..."}
TOKEN_CRED_TYPE = "eapi_token"       # RSoAuth access token (eapi.rs.ge)
