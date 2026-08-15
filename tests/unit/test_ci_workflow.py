from pathlib import Path

import yaml


WORKFLOW = Path(".github/workflows/deploy.yml")


def test_deploy_workflow_has_compile_step_and_strong_test_secret():
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = data["jobs"]["test"]["steps"]
    step_names = [step["name"] for step in steps]
    assert "Compile Python modules" in step_names

    compile_step = next(step for step in steps if step["name"] == "Compile Python modules")
    assert compile_step["run"] == "python -m compileall -q app tests main.py"

    unit_test_step = next(step for step in steps if step["name"] == "Run unit tests")
    jwt_secret = unit_test_step["env"]["JWT_SECRET"]
    assert len(jwt_secret.encode("utf-8")) >= 32

    integration_step = next(step for step in steps if step["name"] == "Run integration smoke tests")
    assert "tests/integration/test_invoice_ocr_fallback.py" in integration_step["run"]

    deploy_steps = data["jobs"]["deploy"]["steps"]
    metadata_step = next(step for step in deploy_steps if step["name"] == "Prepare deployment metadata")
    assert "COMMIT_SHA=${{ github.sha }}" in metadata_step["run"]
    assert "BUILD_TIME=" in metadata_step["run"]
    assert "ENVIRONMENT=production" in metadata_step["run"]

    deploy_step = next(step for step in deploy_steps if step["name"] == "Deploy to Cloud Run")
    assert "--set-env-vars" in deploy_step["run"]
    assert "--update-env-vars" not in deploy_step["run"]
    assert "--set-secrets" in deploy_step["run"]
    assert "--update-secrets" not in deploy_step["run"]
    assert "COMMIT_SHA=${COMMIT_SHA}" in deploy_step["run"]
    assert "BUILD_TIME=${BUILD_TIME}" in deploy_step["run"]
    assert "ENVIRONMENT=${ENVIRONMENT}" in deploy_step["run"]

    version_step = next(step for step in deploy_steps if step["name"] == "Smoke test - version check")
    assert "/version" in version_step["run"]
    assert "commit_sha" in version_step["run"]
    assert "build_time" in version_step["run"]


def test_deploy_workflow_has_no_mojibake_markers():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "â" not in text
