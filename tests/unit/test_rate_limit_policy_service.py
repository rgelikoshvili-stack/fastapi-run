"""
tests/unit/test_rate_limit_policy_service.py

Unit tests for the rate-limit policy classification service (Task 11C-F1).
Pure function tests — no DB, no Redis, no network, no production secrets.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("TEST_MODE", "1")

from app.api.services.rate_limit_policy_service import (
    RateLimitCategory,
    RateLimitRule,
    build_rate_limit_error,
    build_rate_limit_key,
    classify_rate_limit_category,
    get_rate_limit_rule,
    is_rate_limited_category,
)


# ---------------------------------------------------------------------------
# A) Safe path classification
# ---------------------------------------------------------------------------

class TestSafePathClassification:

    def test_health_is_safe(self):
        assert classify_rate_limit_category("/health", "GET") == RateLimitCategory.SAFE

    def test_health_deep_is_safe(self):
        assert classify_rate_limit_category("/health/deep", "GET") == RateLimitCategory.SAFE

    def test_version_is_safe(self):
        assert classify_rate_limit_category("/version", "GET") == RateLimitCategory.SAFE

    def test_docs_is_safe(self):
        assert classify_rate_limit_category("/docs", "GET") == RateLimitCategory.SAFE

    def test_redoc_is_safe(self):
        assert classify_rate_limit_category("/redoc", "GET") == RateLimitCategory.SAFE

    def test_openapi_json_is_safe(self):
        assert classify_rate_limit_category("/openapi.json", "GET") == RateLimitCategory.SAFE

    def test_static_is_safe(self):
        assert classify_rate_limit_category("/static/approval.html", "GET") == RateLimitCategory.SAFE

    def test_static_reports_is_safe(self):
        assert classify_rate_limit_category("/static/reports.html", "GET") == RateLimitCategory.SAFE

    def test_metrics_is_safe(self):
        assert classify_rate_limit_category("/metrics", "GET") == RateLimitCategory.SAFE

    def test_root_is_safe(self):
        assert classify_rate_limit_category("/", "GET") == RateLimitCategory.SAFE


# ---------------------------------------------------------------------------
# B) Auth path classification
# ---------------------------------------------------------------------------

class TestAuthClassification:

    def test_auth_login_is_auth(self):
        assert classify_rate_limit_category("/auth/login", "POST") == RateLimitCategory.AUTH

    def test_auth_register_is_auth(self):
        assert classify_rate_limit_category("/auth/register", "POST") == RateLimitCategory.AUTH

    def test_auth_signup_is_auth(self):
        assert classify_rate_limit_category("/auth/signup", "POST") == RateLimitCategory.AUTH

    def test_auth_refresh_is_auth(self):
        assert classify_rate_limit_category("/auth/refresh", "POST") == RateLimitCategory.AUTH

    def test_auth_password_reset_is_auth(self):
        assert classify_rate_limit_category("/auth/password-reset/request", "POST") == RateLimitCategory.AUTH

    def test_auth_totp_is_auth(self):
        assert classify_rate_limit_category("/auth/totp/verify", "POST") == RateLimitCategory.AUTH


# ---------------------------------------------------------------------------
# C) Credential path classification
# ---------------------------------------------------------------------------

class TestCredentialClassification:

    def test_balance_credentials_save_is_credential(self):
        assert classify_rate_limit_category("/balance-credentials/save", "POST") == RateLimitCategory.CREDENTIAL

    def test_balance_credentials_test_is_credential(self):
        assert classify_rate_limit_category("/balance-credentials/test", "POST") == RateLimitCategory.CREDENTIAL

    def test_rsge_credentials_save_is_credential(self):
        assert classify_rate_limit_category("/rsge-credentials/save", "POST") == RateLimitCategory.CREDENTIAL

    def test_rsge_credentials_test_is_credential(self):
        assert classify_rate_limit_category("/rsge-credentials/test", "POST") == RateLimitCategory.CREDENTIAL

    def test_email_collector_save_is_credential(self):
        assert classify_rate_limit_category("/email-collector/save", "POST") == RateLimitCategory.CREDENTIAL


# ---------------------------------------------------------------------------
# D) Posting path classification
# ---------------------------------------------------------------------------

class TestPostingClassification:

    def test_posting_apply_post_is_posting(self):
        assert classify_rate_limit_category("/posting/apply/5", "POST") == RateLimitCategory.POSTING

    def test_posting_balance_post_is_posting(self):
        assert classify_rate_limit_category("/posting/balance/5", "POST") == RateLimitCategory.POSTING

    def test_posting_onec_post_is_posting(self):
        assert classify_rate_limit_category("/posting/onec/5", "POST") == RateLimitCategory.POSTING

    def test_posting_oris_post_is_posting(self):
        assert classify_rate_limit_category("/posting/oris/5", "POST") == RateLimitCategory.POSTING

    def test_posting_mock_post_is_posting(self):
        assert classify_rate_limit_category("/posting/mock/5", "POST") == RateLimitCategory.POSTING

    def test_posting_apply_get_is_default(self):
        assert classify_rate_limit_category("/posting/apply/5", "GET") == RateLimitCategory.DEFAULT


# ---------------------------------------------------------------------------
# E) Connector / ERP path classification
# ---------------------------------------------------------------------------

class TestConnectorClassification:

    def test_erp_import_is_connector(self):
        assert classify_rate_limit_category("/erp/import", "POST") == RateLimitCategory.CONNECTOR

    def test_erp_sync_is_connector(self):
        assert classify_rate_limit_category("/erp/sync", "POST") == RateLimitCategory.CONNECTOR

    def test_erp_connectors_execute_is_connector(self):
        assert classify_rate_limit_category("/erp-connectors/execute", "POST") == RateLimitCategory.CONNECTOR

    def test_balance_ge_is_connector(self):
        assert classify_rate_limit_category("/balance-ge/post", "POST") == RateLimitCategory.CONNECTOR

    def test_1c_post_is_connector(self):
        assert classify_rate_limit_category("/1c/post", "POST") == RateLimitCategory.CONNECTOR


# ---------------------------------------------------------------------------
# F) AI / OCR heavy path classification
# ---------------------------------------------------------------------------

class TestAiHeavyClassification:

    def test_ai_journal_is_ai_heavy(self):
        assert classify_rate_limit_category("/ai-journal/classify", "POST") == RateLimitCategory.AI_HEAVY

    def test_ai_chat_is_ai_heavy(self):
        assert classify_rate_limit_category("/ai-chat/message", "POST") == RateLimitCategory.AI_HEAVY

    def test_ai_recommend_is_ai_heavy(self):
        assert classify_rate_limit_category("/ai-recommend/suggest", "POST") == RateLimitCategory.AI_HEAVY

    def test_transaction_ai_is_ai_heavy(self):
        assert classify_rate_limit_category("/transaction-ai/draft", "POST") == RateLimitCategory.AI_HEAVY

    def test_ocr_is_ai_heavy(self):
        assert classify_rate_limit_category("/ocr/extract", "POST") == RateLimitCategory.AI_HEAVY

    def test_chat_is_ai_heavy(self):
        assert classify_rate_limit_category("/chat/send", "POST") == RateLimitCategory.AI_HEAVY

    def test_claude_chat_is_ai_heavy(self):
        assert classify_rate_limit_category("/claude-chat/ask", "POST") == RateLimitCategory.AI_HEAVY


# ---------------------------------------------------------------------------
# G) Document upload classification
# ---------------------------------------------------------------------------

class TestDocumentUploadClassification:

    def test_documents_upload_is_document_upload(self):
        assert classify_rate_limit_category("/documents/upload", "POST") == RateLimitCategory.DOCUMENT_UPLOAD

    def test_bank_csv_is_document_upload(self):
        assert classify_rate_limit_category("/bank-csv/import", "POST") == RateLimitCategory.DOCUMENT_UPLOAD

    def test_bank_statements_is_document_upload(self):
        assert classify_rate_limit_category("/bank-statements/upload", "POST") == RateLimitCategory.DOCUMENT_UPLOAD


# ---------------------------------------------------------------------------
# H) Admin classification
# ---------------------------------------------------------------------------

class TestAdminClassification:

    def test_tenants_is_admin(self):
        assert classify_rate_limit_category("/tenants/list", "GET") == RateLimitCategory.ADMIN

    def test_billing_is_admin(self):
        assert classify_rate_limit_category("/billing/invoices", "GET") == RateLimitCategory.ADMIN

    def test_admin_is_admin(self):
        assert classify_rate_limit_category("/admin/users", "GET") == RateLimitCategory.ADMIN


# ---------------------------------------------------------------------------
# I) Default classification
# ---------------------------------------------------------------------------

class TestDefaultClassification:

    def test_approval_queue_is_default(self):
        assert classify_rate_limit_category("/approval/queue", "GET") == RateLimitCategory.DEFAULT

    def test_reports_is_default(self):
        assert classify_rate_limit_category("/reports/trial-balance", "GET") == RateLimitCategory.DEFAULT

    def test_unknown_path_is_default(self):
        assert classify_rate_limit_category("/unknown/endpoint", "GET") == RateLimitCategory.DEFAULT

    def test_posting_logs_is_default(self):
        assert classify_rate_limit_category("/posting/logs", "GET") == RateLimitCategory.DEFAULT


# ---------------------------------------------------------------------------
# J) is_rate_limited_category
# ---------------------------------------------------------------------------

class TestIsRateLimitedCategory:

    def test_safe_is_not_rate_limited(self):
        assert is_rate_limited_category(RateLimitCategory.SAFE) is False

    def test_auth_is_rate_limited(self):
        assert is_rate_limited_category(RateLimitCategory.AUTH) is True

    def test_credential_is_rate_limited(self):
        assert is_rate_limited_category(RateLimitCategory.CREDENTIAL) is True

    def test_posting_is_rate_limited(self):
        assert is_rate_limited_category(RateLimitCategory.POSTING) is True

    def test_connector_is_rate_limited(self):
        assert is_rate_limited_category(RateLimitCategory.CONNECTOR) is True

    def test_ai_heavy_is_rate_limited(self):
        assert is_rate_limited_category(RateLimitCategory.AI_HEAVY) is True

    def test_document_upload_is_rate_limited(self):
        assert is_rate_limited_category(RateLimitCategory.DOCUMENT_UPLOAD) is True

    def test_admin_is_rate_limited(self):
        assert is_rate_limited_category(RateLimitCategory.ADMIN) is True

    def test_default_is_rate_limited(self):
        assert is_rate_limited_category(RateLimitCategory.DEFAULT) is True


# ---------------------------------------------------------------------------
# K) get_rate_limit_rule
# ---------------------------------------------------------------------------

class TestGetRateLimitRule:

    def test_auth_rule_is_strict(self):
        rule = get_rate_limit_rule(RateLimitCategory.AUTH)
        assert rule.limit <= 20
        assert rule.window_seconds > 0
        assert rule.error_code == "AUTH_RATE_LIMIT_EXCEEDED"

    def test_credential_rule_has_correct_error_code(self):
        rule = get_rate_limit_rule(RateLimitCategory.CREDENTIAL)
        assert rule.error_code == "CREDENTIAL_RATE_LIMIT_EXCEEDED"
        assert rule.limit <= 20

    def test_connector_rule_has_correct_error_code(self):
        rule = get_rate_limit_rule(RateLimitCategory.CONNECTOR)
        assert rule.error_code == "CONNECTOR_RATE_LIMIT_EXCEEDED"

    def test_posting_rule_has_connector_error_code(self):
        rule = get_rate_limit_rule(RateLimitCategory.POSTING)
        assert rule.error_code == "CONNECTOR_RATE_LIMIT_EXCEEDED"

    def test_ai_heavy_rule_has_hourly_window(self):
        rule = get_rate_limit_rule(RateLimitCategory.AI_HEAVY)
        assert rule.window_seconds >= 3600
        assert rule.error_code == "AI_RATE_LIMIT_EXCEEDED"

    def test_document_upload_rule_has_hourly_window(self):
        rule = get_rate_limit_rule(RateLimitCategory.DOCUMENT_UPLOAD)
        assert rule.window_seconds >= 3600

    def test_safe_rule_is_very_permissive(self):
        rule = get_rate_limit_rule(RateLimitCategory.SAFE)
        assert rule.limit >= 1000

    def test_default_rule_is_permissive(self):
        rule = get_rate_limit_rule(RateLimitCategory.DEFAULT)
        assert rule.limit >= 60

    def test_unknown_category_falls_back_to_default(self):
        rule = get_rate_limit_rule("unknown_category_xyz")
        default = get_rate_limit_rule(RateLimitCategory.DEFAULT)
        assert rule.limit == default.limit
        assert rule.window_seconds == default.window_seconds

    def test_rule_is_immutable(self):
        rule = get_rate_limit_rule(RateLimitCategory.AUTH)
        assert isinstance(rule, RateLimitRule)
        with pytest.raises((AttributeError, TypeError)):
            rule.limit = 99999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# L) build_rate_limit_key — no secrets
# ---------------------------------------------------------------------------

class TestBuildRateLimitKey:

    def test_key_includes_category(self):
        key = build_rate_limit_key("t1", "u1", "1.2.3.4", RateLimitCategory.AUTH)
        assert "auth" in key

    def test_key_includes_tenant(self):
        key = build_rate_limit_key("tenant_abc", "user_xyz", "1.2.3.4", RateLimitCategory.AUTH)
        assert "tenant_abc" in key

    def test_key_includes_user_id_when_present(self):
        key = build_rate_limit_key("t1", "user123", "1.2.3.4", RateLimitCategory.AUTH)
        assert "user123" in key

    def test_key_uses_ip_hash_when_no_user(self):
        key = build_rate_limit_key("t1", None, "1.2.3.4", RateLimitCategory.AUTH)
        assert "ip_" in key
        assert "1.2.3.4" not in key  # raw IP must not appear

    def test_key_anon_when_no_tenant(self):
        key = build_rate_limit_key(None, None, "1.2.3.4", RateLimitCategory.AUTH)
        assert "anon" in key

    def test_key_does_not_contain_api_key(self):
        key = build_rate_limit_key("t1", "u1", "1.2.3.4", RateLimitCategory.CREDENTIAL)
        for forbidden in ("api_key", "password", "token", "secret", "encrypted"):
            assert forbidden not in key

    def test_same_ip_produces_same_key(self):
        key1 = build_rate_limit_key(None, None, "10.0.0.1", RateLimitCategory.DEFAULT)
        key2 = build_rate_limit_key(None, None, "10.0.0.1", RateLimitCategory.DEFAULT)
        assert key1 == key2

    def test_different_ips_produce_different_keys(self):
        key1 = build_rate_limit_key(None, None, "10.0.0.1", RateLimitCategory.DEFAULT)
        key2 = build_rate_limit_key(None, None, "10.0.0.2", RateLimitCategory.DEFAULT)
        assert key1 != key2

    def test_different_categories_produce_different_keys(self):
        key1 = build_rate_limit_key("t1", "u1", "1.2.3.4", RateLimitCategory.AUTH)
        key2 = build_rate_limit_key("t1", "u1", "1.2.3.4", RateLimitCategory.CREDENTIAL)
        assert key1 != key2

    def test_key_starts_with_rl_prefix(self):
        key = build_rate_limit_key("t1", "u1", "1.2.3.4", RateLimitCategory.AUTH)
        assert key.startswith("rl:")


# ---------------------------------------------------------------------------
# M) build_rate_limit_error — safe envelope
# ---------------------------------------------------------------------------

class TestBuildRateLimitError:

    def test_error_has_ok_false(self):
        rule = get_rate_limit_rule(RateLimitCategory.AUTH)
        err = build_rate_limit_error(rule, 30)
        assert err["ok"] is False

    def test_error_has_rate_limit_error_code(self):
        rule = get_rate_limit_rule(RateLimitCategory.AUTH)
        err = build_rate_limit_error(rule, 30)
        assert err["error"]["code"] == "AUTH_RATE_LIMIT_EXCEEDED"

    def test_error_has_retry_after_seconds(self):
        rule = get_rate_limit_rule(RateLimitCategory.AI_HEAVY)
        err = build_rate_limit_error(rule, 120)
        assert err["data"]["retry_after_seconds"] == 120

    def test_error_no_secrets(self):
        rule = get_rate_limit_rule(RateLimitCategory.CREDENTIAL)
        err = build_rate_limit_error(rule, 60)
        body_str = str(err)
        for forbidden in ("api_key", "password", "token", "secret", "encrypted_value"):
            assert forbidden not in body_str

    def test_error_data_is_not_null(self):
        rule = get_rate_limit_rule(RateLimitCategory.DEFAULT)
        err = build_rate_limit_error(rule, 45)
        assert err["data"] is not None

    def test_error_message_includes_retry_after(self):
        rule = get_rate_limit_rule(RateLimitCategory.POSTING)
        err = build_rate_limit_error(rule, 47)
        assert "47" in err["message"]

    def test_error_has_ok_field(self):
        rule = get_rate_limit_rule(RateLimitCategory.DEFAULT)
        err = build_rate_limit_error(rule, 10)
        assert "ok" in err

    def test_error_has_error_field_with_code_and_details(self):
        rule = get_rate_limit_rule(RateLimitCategory.CONNECTOR)
        err = build_rate_limit_error(rule, 15)
        assert "code" in err["error"]
        assert "details" in err["error"]
