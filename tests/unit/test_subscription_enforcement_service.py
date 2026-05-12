"""
tests/unit/test_subscription_enforcement_service.py

Unit tests for SubscriptionEnforcementService (Task 11C-E1).
Tests pure policy logic: allow/block decisions based on tenant status and action category.

Rules:
  - No DB, no network, no production secrets.
  - All decisions are pure-function evaluations.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("TEST_MODE", "1")

from app.api.services.subscription_enforcement_service import (
    ActionCategory,
    SubscriptionDecision,
    SubscriptionErrorCode,
    SubscriptionStatus,
    build_subscription_error,
    evaluate_subscription_access,
    is_sensitive_action,
)

NOW = datetime(2026, 5, 12, 12, 0, 0, tzinfo=timezone.utc)
FUTURE = NOW + timedelta(days=30)
PAST = NOW - timedelta(days=1)

# ---------------------------------------------------------------------------
# Sample tenant records
# ---------------------------------------------------------------------------

ACTIVE_RECORD = {"status": "active", "is_active": True, "plan": "PRO"}
TRIAL_VALID = {"status": "trial", "is_active": True, "plan": "TRIAL", "trial_ends_at": FUTURE}
TRIAL_EXPIRED_RECORD = {"status": "trial", "is_active": True, "plan": "TRIAL", "trial_ends_at": PAST}
TRIAL_STATUS_EXPIRED = {"status": "trial_expired", "is_active": True, "plan": "TRIAL"}
SUSPENDED_RECORD = {"status": "suspended", "is_active": True, "plan": "PRO"}
INACTIVE_RECORD = {"status": "inactive", "is_active": False, "plan": "FREE"}
INACTIVE_FLAG = {"status": "active", "is_active": False, "plan": "PRO"}
EXPIRED_RECORD = {"status": "expired", "is_active": True, "plan": "PRO"}
UNKNOWN_RECORD = {"status": "unknown_state", "is_active": False}
EMPTY_RECORD: dict = {}


# ---------------------------------------------------------------------------
# A) Active tenant — allowed for all categories
# ---------------------------------------------------------------------------

class TestActiveTenant:

    def test_active_allowed_for_posting_execute(self):
        d = evaluate_subscription_access(ACTIVE_RECORD, ActionCategory.POSTING_EXECUTE, now=NOW)
        assert d.allowed is True

    def test_active_allowed_for_connector_execute(self):
        d = evaluate_subscription_access(ACTIVE_RECORD, ActionCategory.CONNECTOR_EXECUTE, now=NOW)
        assert d.allowed is True

    def test_active_allowed_for_approval_mutation(self):
        d = evaluate_subscription_access(ACTIVE_RECORD, ActionCategory.APPROVAL_MUTATION, now=NOW)
        assert d.allowed is True

    def test_active_allowed_for_credential_write(self):
        d = evaluate_subscription_access(ACTIVE_RECORD, ActionCategory.CREDENTIAL_WRITE, now=NOW)
        assert d.allowed is True

    def test_active_allowed_for_document_upload(self):
        d = evaluate_subscription_access(ACTIVE_RECORD, ActionCategory.DOCUMENT_UPLOAD, now=NOW)
        assert d.allowed is True

    def test_active_allowed_for_ai_heavy(self):
        d = evaluate_subscription_access(ACTIVE_RECORD, ActionCategory.AI_HEAVY, now=NOW)
        assert d.allowed is True

    def test_active_allowed_for_admin_mutation(self):
        d = evaluate_subscription_access(ACTIVE_RECORD, ActionCategory.ADMIN_MUTATION, now=NOW)
        assert d.allowed is True

    def test_active_allowed_for_read_safe(self):
        d = evaluate_subscription_access(ACTIVE_RECORD, ActionCategory.READ_SAFE, now=NOW)
        assert d.allowed is True

    def test_active_status_in_decision(self):
        d = evaluate_subscription_access(ACTIVE_RECORD, ActionCategory.POSTING_EXECUTE, now=NOW)
        assert d.status == SubscriptionStatus.ACTIVE

    def test_active_no_error_code(self):
        d = evaluate_subscription_access(ACTIVE_RECORD, ActionCategory.POSTING_EXECUTE, now=NOW)
        assert d.error_code is None


# ---------------------------------------------------------------------------
# B) Valid trial tenant
# ---------------------------------------------------------------------------

class TestValidTrialTenant:

    def test_trial_allowed_for_read_safe(self):
        d = evaluate_subscription_access(TRIAL_VALID, ActionCategory.READ_SAFE, now=NOW)
        assert d.allowed is True

    def test_trial_allowed_for_approval_mutation(self):
        d = evaluate_subscription_access(TRIAL_VALID, ActionCategory.APPROVAL_MUTATION, now=NOW)
        assert d.allowed is True

    def test_trial_allowed_for_credential_write(self):
        d = evaluate_subscription_access(TRIAL_VALID, ActionCategory.CREDENTIAL_WRITE, now=NOW)
        assert d.allowed is True

    def test_trial_allowed_for_document_upload(self):
        d = evaluate_subscription_access(TRIAL_VALID, ActionCategory.DOCUMENT_UPLOAD, now=NOW)
        assert d.allowed is True

    def test_trial_allowed_for_ai_heavy(self):
        d = evaluate_subscription_access(TRIAL_VALID, ActionCategory.AI_HEAVY, now=NOW)
        assert d.allowed is True

    def test_trial_blocked_for_connector_execute(self):
        d = evaluate_subscription_access(TRIAL_VALID, ActionCategory.CONNECTOR_EXECUTE, now=NOW)
        assert d.allowed is False

    def test_trial_blocked_for_posting_execute(self):
        d = evaluate_subscription_access(TRIAL_VALID, ActionCategory.POSTING_EXECUTE, now=NOW)
        assert d.allowed is False

    def test_trial_blocked_connector_error_code(self):
        d = evaluate_subscription_access(TRIAL_VALID, ActionCategory.CONNECTOR_EXECUTE, now=NOW)
        assert d.error_code == SubscriptionErrorCode.SUBSCRIPTION_REQUIRED

    def test_trial_status_in_decision(self):
        d = evaluate_subscription_access(TRIAL_VALID, ActionCategory.READ_SAFE, now=NOW)
        assert d.status == SubscriptionStatus.TRIAL


# ---------------------------------------------------------------------------
# C) Expired trial tenant (trial_ends_at in past)
# ---------------------------------------------------------------------------

class TestExpiredTrialTenant:

    def test_expired_trial_blocked_for_connector_execute(self):
        d = evaluate_subscription_access(TRIAL_EXPIRED_RECORD, ActionCategory.CONNECTOR_EXECUTE, now=NOW)
        assert d.allowed is False

    def test_expired_trial_blocked_for_posting_execute(self):
        d = evaluate_subscription_access(TRIAL_EXPIRED_RECORD, ActionCategory.POSTING_EXECUTE, now=NOW)
        assert d.allowed is False

    def test_expired_trial_blocked_for_approval_mutation(self):
        d = evaluate_subscription_access(TRIAL_EXPIRED_RECORD, ActionCategory.APPROVAL_MUTATION, now=NOW)
        assert d.allowed is False

    def test_expired_trial_blocked_for_credential_write(self):
        d = evaluate_subscription_access(TRIAL_EXPIRED_RECORD, ActionCategory.CREDENTIAL_WRITE, now=NOW)
        assert d.allowed is False

    def test_expired_trial_allowed_for_billing_safe(self):
        d = evaluate_subscription_access(TRIAL_EXPIRED_RECORD, ActionCategory.BILLING_SAFE, now=NOW)
        assert d.allowed is True

    def test_expired_trial_allowed_for_read_safe(self):
        d = evaluate_subscription_access(TRIAL_EXPIRED_RECORD, ActionCategory.READ_SAFE, now=NOW)
        assert d.allowed is True

    def test_expired_trial_allowed_for_auth_safe(self):
        d = evaluate_subscription_access(TRIAL_EXPIRED_RECORD, ActionCategory.AUTH_SAFE, now=NOW)
        assert d.allowed is True

    def test_expired_trial_error_code_is_trial_expired(self):
        d = evaluate_subscription_access(TRIAL_EXPIRED_RECORD, ActionCategory.POSTING_EXECUTE, now=NOW)
        assert d.error_code == SubscriptionErrorCode.TRIAL_EXPIRED

    def test_trial_status_expired_record_blocked(self):
        d = evaluate_subscription_access(TRIAL_STATUS_EXPIRED, ActionCategory.POSTING_EXECUTE, now=NOW)
        assert d.allowed is False
        assert d.error_code == SubscriptionErrorCode.TRIAL_EXPIRED


# ---------------------------------------------------------------------------
# D) Suspended tenant
# ---------------------------------------------------------------------------

class TestSuspendedTenant:

    def test_suspended_blocked_for_posting_execute(self):
        d = evaluate_subscription_access(SUSPENDED_RECORD, ActionCategory.POSTING_EXECUTE, now=NOW)
        assert d.allowed is False

    def test_suspended_blocked_for_approval_mutation(self):
        d = evaluate_subscription_access(SUSPENDED_RECORD, ActionCategory.APPROVAL_MUTATION, now=NOW)
        assert d.allowed is False

    def test_suspended_blocked_for_connector_execute(self):
        d = evaluate_subscription_access(SUSPENDED_RECORD, ActionCategory.CONNECTOR_EXECUTE, now=NOW)
        assert d.allowed is False

    def test_suspended_blocked_for_credential_write(self):
        d = evaluate_subscription_access(SUSPENDED_RECORD, ActionCategory.CREDENTIAL_WRITE, now=NOW)
        assert d.allowed is False

    def test_suspended_allowed_for_read_safe(self):
        d = evaluate_subscription_access(SUSPENDED_RECORD, ActionCategory.READ_SAFE, now=NOW)
        assert d.allowed is True

    def test_suspended_allowed_for_billing_safe(self):
        d = evaluate_subscription_access(SUSPENDED_RECORD, ActionCategory.BILLING_SAFE, now=NOW)
        assert d.allowed is True

    def test_suspended_error_code(self):
        d = evaluate_subscription_access(SUSPENDED_RECORD, ActionCategory.POSTING_EXECUTE, now=NOW)
        assert d.error_code == SubscriptionErrorCode.TENANT_SUSPENDED

    def test_suspended_status_in_decision(self):
        d = evaluate_subscription_access(SUSPENDED_RECORD, ActionCategory.POSTING_EXECUTE, now=NOW)
        assert d.status == SubscriptionStatus.SUSPENDED


# ---------------------------------------------------------------------------
# E) Inactive tenant
# ---------------------------------------------------------------------------

class TestInactiveTenant:

    def test_inactive_blocked_for_posting_execute(self):
        d = evaluate_subscription_access(INACTIVE_RECORD, ActionCategory.POSTING_EXECUTE, now=NOW)
        assert d.allowed is False

    def test_inactive_blocked_for_approval_mutation(self):
        d = evaluate_subscription_access(INACTIVE_RECORD, ActionCategory.APPROVAL_MUTATION, now=NOW)
        assert d.allowed is False

    def test_inactive_blocked_for_document_upload(self):
        d = evaluate_subscription_access(INACTIVE_RECORD, ActionCategory.DOCUMENT_UPLOAD, now=NOW)
        assert d.allowed is False

    def test_inactive_flag_blocked_for_posting(self):
        d = evaluate_subscription_access(INACTIVE_FLAG, ActionCategory.POSTING_EXECUTE, now=NOW)
        assert d.allowed is False

    def test_inactive_allowed_for_billing_safe(self):
        d = evaluate_subscription_access(INACTIVE_RECORD, ActionCategory.BILLING_SAFE, now=NOW)
        assert d.allowed is True

    def test_inactive_error_code(self):
        d = evaluate_subscription_access(INACTIVE_RECORD, ActionCategory.POSTING_EXECUTE, now=NOW)
        assert d.error_code == SubscriptionErrorCode.TENANT_INACTIVE

    def test_inactive_status_in_decision(self):
        d = evaluate_subscription_access(INACTIVE_RECORD, ActionCategory.POSTING_EXECUTE, now=NOW)
        assert d.status == SubscriptionStatus.INACTIVE


# ---------------------------------------------------------------------------
# F) Expired tenant
# ---------------------------------------------------------------------------

class TestExpiredTenant:

    def test_expired_blocked_for_posting_execute(self):
        d = evaluate_subscription_access(EXPIRED_RECORD, ActionCategory.POSTING_EXECUTE, now=NOW)
        assert d.allowed is False

    def test_expired_blocked_for_connector_execute(self):
        d = evaluate_subscription_access(EXPIRED_RECORD, ActionCategory.CONNECTOR_EXECUTE, now=NOW)
        assert d.allowed is False

    def test_expired_allowed_for_read_safe(self):
        d = evaluate_subscription_access(EXPIRED_RECORD, ActionCategory.READ_SAFE, now=NOW)
        assert d.allowed is True

    def test_expired_error_code(self):
        d = evaluate_subscription_access(EXPIRED_RECORD, ActionCategory.POSTING_EXECUTE, now=NOW)
        assert d.error_code == SubscriptionErrorCode.SUBSCRIPTION_EXPIRED


# ---------------------------------------------------------------------------
# G) Unknown / missing tenant
# ---------------------------------------------------------------------------

class TestUnknownTenant:

    def test_none_record_blocks_sensitive(self):
        d = evaluate_subscription_access(None, ActionCategory.POSTING_EXECUTE, now=NOW)
        assert d.allowed is False

    def test_empty_record_blocks_sensitive(self):
        d = evaluate_subscription_access(EMPTY_RECORD, ActionCategory.POSTING_EXECUTE, now=NOW)
        assert d.allowed is False

    def test_none_record_error_code_unknown(self):
        d = evaluate_subscription_access(None, ActionCategory.POSTING_EXECUTE, now=NOW)
        assert d.error_code == SubscriptionErrorCode.TENANT_STATUS_UNKNOWN

    def test_none_record_allows_billing_safe(self):
        d = evaluate_subscription_access(None, ActionCategory.BILLING_SAFE, now=NOW)
        assert d.allowed is True

    def test_none_record_allows_auth_safe(self):
        d = evaluate_subscription_access(None, ActionCategory.AUTH_SAFE, now=NOW)
        assert d.allowed is True

    def test_none_record_allows_read_safe(self):
        d = evaluate_subscription_access(None, ActionCategory.READ_SAFE, now=NOW)
        assert d.allowed is True


# ---------------------------------------------------------------------------
# H) Error dict builder
# ---------------------------------------------------------------------------

class TestBuildSubscriptionError:

    def test_error_dict_has_ok_false(self):
        d = SubscriptionDecision(
            allowed=False, error_code=SubscriptionErrorCode.TENANT_SUSPENDED,
            message="Tenant is suspended", status=SubscriptionStatus.SUSPENDED,
        )
        err = build_subscription_error(d)
        assert err["ok"] is False

    def test_error_dict_has_error_code(self):
        d = SubscriptionDecision(
            allowed=False, error_code=SubscriptionErrorCode.TRIAL_EXPIRED,
            message="Trial expired", status=SubscriptionStatus.TRIAL_EXPIRED,
        )
        err = build_subscription_error(d)
        assert err["error"]["code"] == SubscriptionErrorCode.TRIAL_EXPIRED

    def test_error_dict_data_is_none(self):
        d = SubscriptionDecision(allowed=False, error_code="SUBSCRIPTION_REQUIRED")
        err = build_subscription_error(d)
        assert err["data"] is None

    def test_error_dict_no_secrets(self):
        d = SubscriptionDecision(
            allowed=False, error_code=SubscriptionErrorCode.TENANT_SUSPENDED,
            message="suspended", status=SubscriptionStatus.SUSPENDED,
        )
        err = build_subscription_error(d)
        err_str = str(err)
        for forbidden in ("api_key", "password", "token", "encrypted_value"):
            assert forbidden not in err_str

    def test_error_dict_no_raw_tenant_data(self):
        d = SubscriptionDecision(
            allowed=False, error_code=SubscriptionErrorCode.TENANT_INACTIVE,
            message="blocked", status=SubscriptionStatus.INACTIVE,
        )
        err = build_subscription_error(d)
        assert "is_active" not in str(err)
        assert "plan" not in str(err)

    def test_error_dict_uses_fallback_code_if_none(self):
        d = SubscriptionDecision(allowed=False, error_code=None)
        err = build_subscription_error(d)
        assert err["error"]["code"] == SubscriptionErrorCode.SUBSCRIPTION_REQUIRED


# ---------------------------------------------------------------------------
# I) is_sensitive_action helper
# ---------------------------------------------------------------------------

class TestIsSensitiveAction:

    def test_connector_execute_is_sensitive(self):
        assert is_sensitive_action(ActionCategory.CONNECTOR_EXECUTE) is True

    def test_posting_execute_is_sensitive(self):
        assert is_sensitive_action(ActionCategory.POSTING_EXECUTE) is True

    def test_approval_mutation_is_sensitive(self):
        assert is_sensitive_action(ActionCategory.APPROVAL_MUTATION) is True

    def test_credential_write_is_sensitive(self):
        assert is_sensitive_action(ActionCategory.CREDENTIAL_WRITE) is True

    def test_document_upload_is_sensitive(self):
        assert is_sensitive_action(ActionCategory.DOCUMENT_UPLOAD) is True

    def test_ai_heavy_is_sensitive(self):
        assert is_sensitive_action(ActionCategory.AI_HEAVY) is True

    def test_admin_mutation_is_sensitive(self):
        assert is_sensitive_action(ActionCategory.ADMIN_MUTATION) is True

    def test_read_safe_is_not_sensitive(self):
        assert is_sensitive_action(ActionCategory.READ_SAFE) is False

    def test_auth_safe_is_not_sensitive(self):
        assert is_sensitive_action(ActionCategory.AUTH_SAFE) is False

    def test_billing_safe_is_not_sensitive(self):
        assert is_sensitive_action(ActionCategory.BILLING_SAFE) is False


# ---------------------------------------------------------------------------
# J) Date boundary behavior
# ---------------------------------------------------------------------------

class TestDateBoundaryBehavior:

    def test_trial_expires_exactly_now_is_expired(self):
        record = {"status": "trial", "is_active": True, "trial_ends_at": NOW}
        # trial_ends_at == now means it expired at this exact moment
        d = evaluate_subscription_access(record, ActionCategory.POSTING_EXECUTE, now=NOW)
        assert d.allowed is False

    def test_trial_expires_one_second_in_future_is_valid(self):
        one_sec_future = NOW + timedelta(seconds=1)
        record = {"status": "trial", "is_active": True, "trial_ends_at": one_sec_future}
        d = evaluate_subscription_access(record, ActionCategory.APPROVAL_MUTATION, now=NOW)
        assert d.allowed is True

    def test_trial_with_no_expiry_date_is_valid(self):
        record = {"status": "trial", "is_active": True}
        d = evaluate_subscription_access(record, ActionCategory.APPROVAL_MUTATION, now=NOW)
        assert d.allowed is True

    def test_trial_with_string_iso_date_past_is_expired(self):
        past_str = "2020-01-01T00:00:00+00:00"
        record = {"status": "trial", "is_active": True, "trial_ends_at": past_str}
        d = evaluate_subscription_access(record, ActionCategory.POSTING_EXECUTE, now=NOW)
        assert d.allowed is False

    def test_trial_with_string_iso_date_future_is_valid(self):
        future_str = "2099-01-01T00:00:00+00:00"
        record = {"status": "trial", "is_active": True, "trial_ends_at": future_str}
        d = evaluate_subscription_access(record, ActionCategory.APPROVAL_MUTATION, now=NOW)
        assert d.allowed is True

    def test_now_defaults_to_utc_when_not_provided(self):
        record = {"status": "active", "is_active": True}
        d = evaluate_subscription_access(record, ActionCategory.POSTING_EXECUTE)
        assert d.allowed is True


# ---------------------------------------------------------------------------
# K) SubscriptionDecision is a dataclass with expected fields
# ---------------------------------------------------------------------------

class TestSubscriptionDecisionStructure:

    def test_decision_has_allowed_field(self):
        d = SubscriptionDecision(allowed=True)
        assert d.allowed is True

    def test_decision_has_status_field(self):
        d = SubscriptionDecision(allowed=True, status=SubscriptionStatus.ACTIVE)
        assert d.status == SubscriptionStatus.ACTIVE

    def test_decision_has_error_code_field(self):
        d = SubscriptionDecision(allowed=False, error_code=SubscriptionErrorCode.TRIAL_EXPIRED)
        assert d.error_code == SubscriptionErrorCode.TRIAL_EXPIRED

    def test_decision_has_message_field(self):
        d = SubscriptionDecision(allowed=False, message="blocked")
        assert d.message == "blocked"


# ---------------------------------------------------------------------------
# L) Status constants coverage
# ---------------------------------------------------------------------------

class TestStatusConstants:

    def test_active_constant(self):
        assert SubscriptionStatus.ACTIVE == "active"

    def test_trial_constant(self):
        assert SubscriptionStatus.TRIAL == "trial"

    def test_trial_expired_constant(self):
        assert SubscriptionStatus.TRIAL_EXPIRED == "trial_expired"

    def test_suspended_constant(self):
        assert SubscriptionStatus.SUSPENDED == "suspended"

    def test_inactive_constant(self):
        assert SubscriptionStatus.INACTIVE == "inactive"

    def test_expired_constant(self):
        assert SubscriptionStatus.EXPIRED == "expired"

    def test_unknown_constant(self):
        assert SubscriptionStatus.UNKNOWN == "unknown"
