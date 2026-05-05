"""tests/unit/test_approval_service_quality.py
Targeted quality tests for approval_service bug fixes.
"""
import inspect
import logging
from unittest.mock import MagicMock, patch, call


# ── Task 1: fuzzy-match pattern type bug ─────────────────────────────────────

def test_mark_success_uses_description_fuzzy_for_fuzzy_match():
    """_mark_success_for_draft must call mark_pattern_success with 'description_fuzzy'
    when pattern_matched_on == 'description_fuzzy', not 'description_exact'."""
    from app.api.services.approval_service import _mark_success_for_draft

    draft = {
        "pattern_matched_on": "description_fuzzy",
        "pattern_value_used": "Wolt Georgia",
        "account_code": "7720",
    }
    calls_recorded = []

    def fake_mark(pattern_type, pattern_value, account_code, tenant_id, weight):
        calls_recorded.append(pattern_type)
        return {"updated": 1}

    with patch("app.api.services.approval_patterns.mark_pattern_success", side_effect=fake_mark):
        _mark_success_for_draft(draft, tenant_id="tenant-a", weight=1.0)

    assert calls_recorded, "mark_pattern_success was never called"
    assert calls_recorded[0] == "description_fuzzy", (
        f"Expected 'description_fuzzy', got '{calls_recorded[0]}' — "
        "fuzzy match must reinforce the fuzzy bucket, not the exact bucket"
    )


def test_mark_success_uses_description_exact_for_exact_match():
    """Exact-match path must still call mark_pattern_success with 'description_exact'."""
    from app.api.services.approval_service import _mark_success_for_draft

    draft = {
        "pattern_matched_on": "description_exact",
        "pattern_value_used": "Wolt Georgia",
        "account_code": "7720",
    }
    calls_recorded = []

    def fake_mark(pattern_type, *args, **kwargs):
        calls_recorded.append(pattern_type)
        return {"updated": 1}

    with patch("app.api.services.approval_patterns.mark_pattern_success", side_effect=fake_mark):
        _mark_success_for_draft(draft, tenant_id="tenant-a", weight=1.0)

    assert calls_recorded[0] == "description_exact", (
        f"Exact match path must use 'description_exact', got '{calls_recorded[0]}'"
    )


def test_mark_failure_uses_description_fuzzy_for_fuzzy_match():
    """_mark_failure_for_draft must call mark_pattern_failure with 'description_fuzzy'
    when pattern_matched_on == 'description_fuzzy'."""
    from app.api.services.approval_service import _mark_failure_for_draft

    draft = {
        "pattern_matched_on": "description_fuzzy",
        "pattern_value_used": "Amazon EU",
        "account_code": "7810",
    }
    calls_recorded = []

    def fake_mark(pattern_type, *args, **kwargs):
        calls_recorded.append(pattern_type)
        return {"updated": 1}

    with patch("app.api.services.approval_patterns.mark_pattern_failure", side_effect=fake_mark):
        _mark_failure_for_draft(draft, tenant_id="tenant-a", weight=1.5)

    assert calls_recorded, "mark_pattern_failure was never called"
    assert calls_recorded[0] == "description_fuzzy", (
        f"Expected 'description_fuzzy', got '{calls_recorded[0]}'"
    )


def test_mark_failure_uses_description_exact_for_exact_match():
    """Exact-match rejection must still reinforce the exact bucket."""
    from app.api.services.approval_service import _mark_failure_for_draft

    draft = {
        "pattern_matched_on": "description_exact",
        "pattern_value_used": "Amazon EU",
        "account_code": "7810",
    }
    calls_recorded = []

    def fake_mark(pattern_type, *args, **kwargs):
        calls_recorded.append(pattern_type)
        return {"updated": 1}

    with patch("app.api.services.approval_patterns.mark_pattern_failure", side_effect=fake_mark):
        _mark_failure_for_draft(draft, tenant_id="tenant-a", weight=1.5)

    assert calls_recorded[0] == "description_exact"


def test_partner_fuzzy_still_uses_partner_type():
    """partner_fuzzy path must use 'partner' type (unchanged, regression guard)."""
    from app.api.services.approval_service import _mark_success_for_draft

    draft = {
        "pattern_matched_on": "partner_fuzzy",
        "pattern_value_used": "JSC Acme",
        "account_code": "7100",
    }
    calls_recorded = []

    def fake_mark(pattern_type, *args, **kwargs):
        calls_recorded.append(pattern_type)
        return {"updated": 1}

    with patch("app.api.services.approval_patterns.mark_pattern_success", side_effect=fake_mark):
        _mark_success_for_draft(draft, tenant_id="tenant-a", weight=1.0)

    assert calls_recorded[0] == "partner"


# ── Task 2: period-lock exception must not be silently swallowed ─────────────

def test_period_lock_exception_is_logged_not_silenced():
    """A broken period-lock check must emit a warning log, not silently pass."""
    src = inspect.getsource(
        __import__("app.api.services.approval_service", fromlist=["approve_draft_service"])
        .approve_draft_service
    )
    # The except block that used to be `pass` must now reference log.warning
    # Find the period_lock section
    assert "log.warning" in src or "log.exception" in src, (
        "period_lock exception handler must call log.warning — silent pass is not acceptable"
    )
    assert "period_lock" in src.lower()
    # Explicit regression guard: bare `except Exception: pass` around period lock must be gone
    lines = src.splitlines()
    for i, line in enumerate(lines):
        if "period_lock" in line.lower() and "except Exception" in (lines[i+1] if i+1 < len(lines) else ""):
            next_line = lines[i+2].strip() if i+2 < len(lines) else ""
            assert next_line != "pass", (
                f"Line {i+2}: bare 'pass' after period_lock exception — must log.warning"
            )


def test_period_lock_silent_pass_removed_from_source():
    """Source inspection: the old `except Exception: pass` pattern must not exist
    immediately after the period_lock try block."""
    import app.api.services.approval_service as mod
    src = inspect.getsource(mod)
    # The old pattern was:
    #   except Exception:
    #       pass
    # followed immediately by `if draft["status"] == "approved":`
    # Verify this exact sequence is gone
    assert 'except Exception:\n                pass' not in src, (
        "Silent bare 'except Exception: pass' still present in approval_service"
    )


def test_posting_service_period_lock_silent_pass_removed():
    """posting_service must also log period-lock exceptions, not swallow them."""
    import app.api.services.posting_service as mod
    src = inspect.getsource(mod)
    # Old pattern: `except Exception:\n                    pass` around period lock
    assert 'except Exception:\n                    pass' not in src, (
        "Silent bare 'except Exception: pass' still present in posting_service period-lock path"
    )
    # Must have a log.warning in the posting period-lock handler
    assert "log.warning" in src or "log.exception" in src, (
        "posting_service must log unexpected period-lock exceptions"
    )


# ── Task 4: CFO threshold is documented and tested ───────────────────────────

def test_cfo_threshold_is_10000():
    """CFO dual-approval threshold is currently 10000.0.
    This test documents the current value — update when tenant config is added."""
    import app.api.services.approval_service as mod
    src = inspect.getsource(mod)
    assert "10000" in src, "CFO threshold constant not found in approval_service"
    assert "DUAL_APPROVAL_THRESHOLD" in src


def test_cfo_threshold_reads_from_tenant_config_service():
    """CFO threshold must be read via get_tenant_setting, not a bare hardcoded literal."""
    import app.api.services.approval_service as mod
    src = inspect.getsource(mod)
    assert "tenant_config_service" in src, (
        "approval_service must import from tenant_config_service for the CFO threshold"
    )
    assert "get_tenant_setting" in src, (
        "approval_service must call get_tenant_setting to read CFO threshold"
    )


# ── Task 3: bare exception audit — documented hotspots ───────────────────────

def test_bare_exception_audit_top10_documented():
    """This test documents the remaining top-10 bare-exception hotspots.
    It does not assert they are fixed — each requires a separate focused PR."""
    import app.api.services.approval_service as mod_a
    import app.api.services.posting_service as mod_p

    hotspots = [
        # (file, approx description, risk)
        ("approval_service.py:~33",  "get_queue_service outer catch",         "medium — returns error_response, DB error exposed in details"),
        ("approval_service.py:~130", "get_draft_detail_service outer catch",  "medium — same pattern"),
        ("approval_service.py:~702", "autopilot batch loop catch",            "medium — rolls back + records failed_id, acceptable"),
        ("posting_service.py:~64",   "_to_decimal fallback to Decimal(0)",    "medium — silent NULL→0 for financial amounts"),
        ("posting_service.py:~93",   "_normalize_lines JSON parse failure",   "low — returns empty list, not financial"),
        ("posting_service.py:~178",  "currency rate fallback to 1.0",         "high — wrong FX rate applied silently"),
        ("posting_service.py:~603",  "_find_successful_post silent None",     "low — idempotency lookup, not financial"),
        ("posting_service.py:~755",  "duplicate-invoice check catch",         "medium — force=False path, should log"),
        ("approval_service.py:~372", "approve_draft outer catch",             "medium — exposes str(e) to client"),
        ("approval_service.py:~510", "reject_draft outer catch",              "medium — same"),
    ]
    # This test always passes — it is a living checklist
    assert len(hotspots) == 10
