"""
Tests for docs/staging-promotion-decision-h56.md (H56).
No Docker, no DB, no network — pure doc content verification.
"""
import os
import pytest

DOC_PATH = "docs/staging-promotion-decision-h56.md"


def _read():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


class TestDocumentExists:
    def test_h56_doc_exists(self):
        assert os.path.exists(DOC_PATH)

    def test_h56_doc_not_empty(self):
        assert len(_read()) > 500

    def test_h56_purpose_documented(self):
        assert "Purpose" in _read()


class TestNonActionStatement:
    def test_non_action_confirmed(self):
        assert "does NOT" in _read()

    def test_no_production_db(self):
        text = _read()
        assert "production" in text.lower()

    def test_no_feature_flag_enable(self):
        assert "POSTED_LEDGER_REPORTS_ENABLED" in _read()

    def test_no_cloud_run_mutation(self):
        text = _read()
        assert "Cloud Run" in text


class TestLocalEvidenceSummary:
    def test_h49_decision_documented(self):
        assert "DOCKER_EVIDENCE_CAPTURED" in _read()

    def test_h52_decision_documented(self):
        assert "SUCCESS_LOCAL_DOCKER_POSTGRES_DRY_RUN_COMPLETE" in _read()

    def test_h53_decision_documented(self):
        assert "SUCCESS_LOCAL_REPORT_SNAPSHOT_COMPARISON_PASS" in _read()

    def test_h54_decision_documented(self):
        assert "ACCOUNTANT_REVIEW_READY" in _read()

    def test_h55_decision_documented(self):
        assert "FINAL_LOCAL_EVIDENCE_READY" in _read()

    def test_all_prior_pass(self):
        text = _read()
        assert "PASS" in text or "✅" in text


class TestPromotionOptions:
    def test_options_documented(self):
        text = _read()
        assert "Option" in text or "option" in text.lower()

    def test_staging_option_documented(self):
        text = _read()
        assert "staging" in text.lower() or "Staging" in text

    def test_production_switch_option_documented(self):
        text = _read()
        assert "production" in text.lower()

    def test_local_option_documented(self):
        text = _read()
        assert "local" in text.lower()


class TestStagingConditions:
    def test_staging_conditions_documented(self):
        text = _read()
        assert "Staging" in text

    def test_additive_migration_documented(self):
        text = _read()
        assert "additive" in text.lower()

    def test_no_staging_env_referenced(self):
        text = _read()
        assert "no staging" in text.lower() or "not confirmed" in text.lower() or "not referenced" in text.lower()


class TestProductionSwitchConditions:
    def test_conditions_documented(self):
        text = _read()
        assert "Condition" in text or "condition" in text.lower()

    def test_fixture_hash_condition(self):
        text = _read()
        assert "SHA-256" in text or "hash" in text.lower()

    def test_cleanup_condition(self):
        text = _read()
        assert "cleanup" in text.lower() or "Cleanup" in text

    def test_feature_flag_off_condition(self):
        assert "POSTED_LEDGER_REPORTS_ENABLED" in _read()

    def test_demo_mode_condition(self):
        assert "demo_mode" in _read()

    def test_rollback_condition(self):
        text = _read()
        assert "rollback" in text.lower() or "Rollback" in text


class TestNoGoBlockers:
    def test_blockers_documented(self):
        text = _read()
        assert "Blocker" in text or "blocker" in text.lower()

    def test_no_blockers_present(self):
        text = _read()
        assert "no no-go" in text.lower() or "No no-go" in text or "no ✅" in text.lower()

    def test_tenant_leakage_blocker(self):
        text = _read()
        assert "leakage" in text.lower()

    def test_unbalanced_totals_blocker(self):
        text = _read()
        assert "Unbalanced" in text or "unbalanced" in text.lower()


class TestRecommendation:
    def test_recommendation_documented(self):
        text = _read()
        assert "Recommendation" in text or "recommendation" in text.lower()

    def test_h57_recommended(self):
        assert "H57" in _read()

    def test_proceed_to_switch_prep(self):
        text = _read()
        assert "production switch" in text.lower()


class TestFinalDecision:
    def test_decision_documented(self):
        assert "READY_FOR_PRODUCTION_SWITCH_PREPARATION_PLAN" in _read()

    def test_h57_next_documented(self):
        assert "H57" in _read()


class TestNoForbiddenImports:
    def test_no_forbidden_imports(self):
        with open(__file__, encoding="utf-8") as f:
            lines = f.readlines()
        forbidden = [
            "import " + "psycopg", "import " + "sqlalchemy",
            "import " + "requests", "import " + "httpx",
            "import " + "socket", "import " + "subprocess",
            "from " + "app.", "from docker" + " import",
        ]
        for line in lines:
            s = line.strip()
            if s.startswith("#"): continue
            for imp in forbidden:
                assert imp not in s, f"Forbidden import: {s}"
