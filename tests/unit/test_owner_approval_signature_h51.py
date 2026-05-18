"""
Tests for docs/owner-approval-signature-h51.md (H51).

H51 records the engineering owner signature on APPROVAL-2026-H50-001.
Owner: ROLANDI GELIKOSHVILI / r.gelikoshvili@gmail.com
Approval scope: local_docker_postgres_dry_run_only
expires_at: 2026-05-25T16:00:00Z (7 days from approved_at)
H51 approval decision: OWNER_APPROVAL_SIGNED
No Docker run/pull/compose, no DB, no SQL, no migration, no fixture, no runtime APIs.
"""

import os
import pytest

DOC_PATH = "docs/owner-approval-signature-h51.md"

REQUIRED_APPROVAL_FIELDS = [
    "approval_id",
    "approved_by",
    "approved_by_email",
    "requested_by",
    "scope",
    "allowed_operations",
    "forbidden_operations",
    "cleanup_policy",
    "retention_policy",
    "approved_at",
    "expires_at",
    "max_validity_days",
    "approval_status",
]

ALLOWED_APPROVAL_DECISIONS = {
    "OWNER_APPROVAL_SIGNED",
    "OWNER_APPROVAL_PENDING",
    "BLOCKED_SCOPE_UNCLEAR",
    "BLOCKED_EXPIRES_AT_MISSING",
    "BLOCKED_EXPIRES_AT_TOO_LONG",
}


def _read_doc():
    with open(DOC_PATH, "r", encoding="utf-8") as f:
        return f.read()


def validate_approval_signature(packet: dict) -> list:
    """Validate an H51 owner approval signature packet. Returns list of errors."""
    errors = []
    for field in REQUIRED_APPROVAL_FIELDS:
        if field not in packet:
            errors.append(f"missing field: {field}")
    scope = packet.get("scope", "")
    if "local_docker" not in scope and "local" not in scope:
        errors.append(f"scope must be local_docker only, got: {scope!r}")
    if packet.get("max_validity_days", 0) > 7:
        errors.append("max_validity_days exceeds 7-day maximum")
    if packet.get("expires_at_days_from_approval", 0) > 7:
        errors.append("expires_at exceeds 7-day maximum from approved_at")
    return errors


def classify_approval_decision(packet: dict) -> str:
    """Return approval decision string for a given packet state."""
    if not packet.get("scope"):
        return "BLOCKED_SCOPE_UNCLEAR"
    if not packet.get("allowed_operations"):
        return "BLOCKED_SCOPE_UNCLEAR"
    if not packet.get("expires_at"):
        return "BLOCKED_EXPIRES_AT_MISSING"
    if packet.get("expires_at_days_from_approval", 0) > 7:
        return "BLOCKED_EXPIRES_AT_TOO_LONG"
    if packet.get("approval_status") == "approved":
        return "OWNER_APPROVAL_SIGNED"
    return "OWNER_APPROVAL_PENDING"


# --- tests ---

class TestDocumentExists:
    def test_h51_owner_approval_doc_exists(self):
        assert os.path.exists(DOC_PATH), f"Expected {DOC_PATH} to exist"

    def test_h51_doc_not_empty(self):
        text = _read_doc()
        assert len(text) > 500


class TestH50Context:
    def test_h50_context_documented(self):
        text = _read_doc()
        assert "H50" in text
        assert "BLOCKED_OWNER_APPROVAL_PENDING" in text

    def test_h50_live_verified_sha_mentioned(self):
        text = _read_doc()
        assert "1913a73" in text

    def test_g7_blocker_documented(self):
        text = _read_doc()
        assert "G7" in text
        assert "14 of 15" in text or "14/15" in text

    def test_h51_non_action_statements_present(self):
        text = _read_doc()
        assert "does NOT" in text


class TestApprovalPacketFields:
    def test_approval_packet_fields_documented(self):
        text = _read_doc()
        for field in REQUIRED_APPROVAL_FIELDS:
            assert field in text, f"Field {field!r} not documented in approval packet"

    def test_approval_id_documented(self):
        text = _read_doc()
        assert "APPROVAL-2026-H50-001" in text

    def test_approved_by_documented(self):
        text = _read_doc()
        assert "ROLANDI GELIKOSHVILI" in text

    def test_approved_by_email_documented(self):
        text = _read_doc()
        assert "r.gelikoshvili@gmail.com" in text

    def test_approved_at_documented(self):
        text = _read_doc()
        assert "2026-05-18" in text

    def test_expires_at_documented(self):
        text = _read_doc()
        assert "2026-05-25" in text


class TestAllowedScope:
    def test_allowed_scope_documented(self):
        text = _read_doc()
        assert "Allowed Scope" in text or "allowed_scope" in text or "allowed_operations" in text

    def test_local_docker_in_scope(self):
        text = _read_doc()
        assert "local_docker_postgres_dry_run_only" in text

    def test_synthetic_fixture_in_allowed_scope(self):
        text = _read_doc()
        assert "synthetic" in text.lower()
        assert "fixture" in text.lower()

    def test_cleanup_in_allowed_scope(self):
        text = _read_doc()
        assert "cleanup" in text.lower()


class TestForbiddenScope:
    def test_forbidden_scope_documented(self):
        text = _read_doc()
        assert "Forbidden" in text or "forbidden_operations" in text

    def test_production_db_forbidden(self):
        text = _read_doc()
        assert "production" in text.lower()
        assert "DB" in text or "db" in text.lower()

    def test_cloud_run_mutation_forbidden(self):
        text = _read_doc()
        assert "Cloud Run" in text or "cloud_run" in text
        assert "mutate" in text.lower() or "forbidden" in text.lower()

    def test_feature_flag_production_forbidden(self):
        text = _read_doc()
        assert "POSTED_LEDGER_REPORTS_ENABLED" in text

    def test_balance_ge_live_forbidden(self):
        text = _read_doc()
        assert "Balance.ge" in text or "balance_ge" in text


class TestCleanupCommitment:
    def test_cleanup_commitment_documented(self):
        text = _read_doc()
        assert "Cleanup" in text or "cleanup" in text.lower()

    def test_container_remove_documented(self):
        text = _read_doc()
        assert "container_remove" in text or "docker stop" in text.lower() or "docker rm" in text.lower()

    def test_volume_remove_documented(self):
        text = _read_doc()
        assert "volume rm" in text.lower() or "volume remove" in text.lower() or "volume_rm" in text.lower()

    def test_no_secrets_retained_documented(self):
        text = _read_doc()
        assert "secret" in text.lower()
        assert "no secret" in text.lower() or "not retained" in text.lower() or "No secrets" in text


class TestApprovalDecisionOutputs:
    def test_approval_decision_outputs_documented(self):
        text = _read_doc()
        assert "OWNER_APPROVAL_SIGNED" in text

    def test_owner_approval_signed_decision_present(self):
        text = _read_doc()
        assert "OWNER_APPROVAL_SIGNED" in text

    def test_owner_approval_pending_decision_present(self):
        text = _read_doc()
        assert "OWNER_APPROVAL_PENDING" in text

    def test_expires_at_decisions_documented(self):
        text = _read_doc()
        assert "BLOCKED_EXPIRES_AT_MISSING" in text
        assert "BLOCKED_EXPIRES_AT_TOO_LONG" in text

    def test_current_decision_is_signed(self):
        text = _read_doc()
        assert "OWNER_APPROVAL_SIGNED" in text
        assert "approval_status" in text
        assert "approved" in text


class TestApprovalScopeLimited:
    def test_approval_scope_limited_to_local_docker(self):
        packet = {
            "approval_id": "APPROVAL-2026-H50-001",
            "approved_by": "ROLANDI GELIKOSHVILI",
            "approved_by_email": "r.gelikoshvili@gmail.com",
            "requested_by": "Bridge Hub AI",
            "scope": "local_docker_postgres_dry_run_only",
            "allowed_operations": ["docker_pull_postgres_16", "cleanup_container_and_volume"],
            "forbidden_operations": ["connect_to_production_db"],
            "cleanup_policy": "container_remove",
            "retention_policy": "synthetic data only",
            "approved_at": "2026-05-18T16:00:00Z",
            "expires_at": "2026-05-25T16:00:00Z",
            "max_validity_days": 7,
            "approval_status": "approved",
        }
        errors = validate_approval_signature(packet)
        assert errors == []

    def test_approval_does_not_allow_production(self):
        packet = {
            "approval_id": "APPROVAL-2026-H50-001",
            "approved_by": "ROLANDI GELIKOSHVILI",
            "approved_by_email": "r.gelikoshvili@gmail.com",
            "requested_by": "Bridge Hub AI",
            "scope": "production_db",
            "allowed_operations": [],
            "forbidden_operations": [],
            "cleanup_policy": "container_remove",
            "retention_policy": "synthetic data only",
            "approved_at": "2026-05-18T16:00:00Z",
            "expires_at": "2026-05-25T16:00:00Z",
            "max_validity_days": 7,
            "approval_status": "pending",
        }
        errors = validate_approval_signature(packet)
        assert any("scope" in e for e in errors)

    def test_classifier_signed_returns_signed(self):
        result = classify_approval_decision({
            "scope": "local_docker_postgres_dry_run_only",
            "allowed_operations": ["docker_pull_postgres_16"],
            "expires_at": "2026-05-25T16:00:00Z",
            "expires_at_days_from_approval": 7,
            "approval_status": "approved",
        })
        assert result == "OWNER_APPROVAL_SIGNED"

    def test_classifier_pending_returns_pending(self):
        result = classify_approval_decision({
            "scope": "local_docker_postgres_dry_run_only",
            "allowed_operations": ["docker_pull_postgres_16"],
            "expires_at": "2026-05-25T16:00:00Z",
            "expires_at_days_from_approval": 7,
            "approval_status": "pending",
        })
        assert result == "OWNER_APPROVAL_PENDING"

    def test_classifier_missing_expires_at_blocked(self):
        result = classify_approval_decision({
            "scope": "local_docker_postgres_dry_run_only",
            "allowed_operations": ["docker_pull_postgres_16"],
            "expires_at": None,
            "approval_status": "approved",
        })
        assert result == "BLOCKED_EXPIRES_AT_MISSING"

    def test_classifier_expires_at_too_long_blocked(self):
        result = classify_approval_decision({
            "scope": "local_docker_postgres_dry_run_only",
            "allowed_operations": ["docker_pull_postgres_16"],
            "expires_at": "2026-06-18T16:00:00Z",
            "expires_at_days_from_approval": 31,
            "approval_status": "approved",
        })
        assert result == "BLOCKED_EXPIRES_AT_TOO_LONG"


class TestExpiresAtMaxRule:
    def test_expires_at_max_7_days_rule_documented(self):
        text = _read_doc()
        assert "7" in text
        assert "day" in text.lower() or "expires" in text.lower()

    def test_max_validity_days_is_7(self):
        packet = {
            "approval_id": "APPROVAL-2026-H50-001",
            "approved_by": "ROLANDI GELIKOSHVILI",
            "approved_by_email": "r.gelikoshvili@gmail.com",
            "requested_by": "Bridge Hub AI",
            "scope": "local_docker_postgres_dry_run_only",
            "allowed_operations": ["docker_pull_postgres_16"],
            "forbidden_operations": [],
            "cleanup_policy": "container_remove",
            "retention_policy": "synthetic data only",
            "approved_at": "2026-05-18T16:00:00Z",
            "expires_at": "2026-05-25T16:00:00Z",
            "max_validity_days": 8,
            "approval_status": "approved",
        }
        errors = validate_approval_signature(packet)
        assert any("max_validity_days" in e for e in errors)


class TestNoForbiddenImports:
    def test_no_db_docker_execution_imports(self):
        with open(__file__, "r", encoding="utf-8") as f:
            lines = f.readlines()
        _forbidden = [
            "import " + "psycopg",
            "import " + "sqlalchemy",
            "import " + "requests",
            "import " + "httpx",
            "import " + "socket",
            "import " + "subprocess",
            "from " + "app.",
            "from docker" + " import",
        ]
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for imp in _forbidden:
                assert imp not in stripped, f"Forbidden import: {stripped}"
