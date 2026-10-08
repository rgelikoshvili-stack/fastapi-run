from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "deploy.yml"


def test_production_deploy_and_smoke_target_canonical_us_service():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "REGION: us-central1" in text
    assert "SERVICE_URL: https://fastapi-run-oobzrmikna-uc.a.run.app" in text
    assert "--region ${{ env.REGION }}" in text
    assert "europe-west1" not in text


def test_deploy_stamps_and_checks_revision_provenance():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert '--update-labels "bridgehub-commit-sha=${COMMIT_SHA},bridgehub-workflow-run=${GITHUB_RUN_ID}"' in text
    assert '.metadata.labels["bridgehub-commit-sha"]' in text
    assert '.metadata.labels["bridgehub-workflow-run"]' in text
    assert "status.imageDigest" in text
    assert "traffic_percent=100" in text


def test_normal_deploy_preserves_database_auth_and_provider_secret_configuration():
    text = WORKFLOW.read_text(encoding="utf-8")
    deploy = text.split("- name: Deploy to Cloud Run", 1)[1].split(
        "- name: Verify deployed revision provenance and traffic", 1
    )[0]
    assert "--update-secrets" in deploy
    assert "DATABASE_URL=" not in deploy
    assert "JWT_SECRET=" not in deploy
    assert "ANTHROPIC_API_KEY=" not in deploy
    assert "OPENROUTER_API_KEY=" not in deploy
    assert "VAULT_ENCRYPTION_KEY=" in deploy
    assert "SMTP_PASS=" in deploy
    assert "IMAP_PASS=" in deploy
