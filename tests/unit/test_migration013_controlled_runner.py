import json

import pytest

from scripts import run_migration_013_controlled as runner


def test_checksum_is_pinned_to_reviewed_migration():
    assert runner.migration_checksum() == runner.EXPECTED_SHA256
    assert runner.validate_artifact().startswith(b"-- NEXT-04A")


def test_modified_artifact_is_rejected():
    with pytest.raises(runner.MigrationBlocked, match="checksum mismatch"):
        runner.validate_artifact(runner.migration_bytes() + b"\n-- modified")


def test_default_cli_is_filesystem_only_dry_run(capsys, monkeypatch):
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)
    assert runner.main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "migration_id": runner.MIGRATION_ID,
        "checksum": runner.EXPECTED_SHA256,
        "mode": "DRY_RUN",
        "database_access": False,
    }


def test_execute_requires_both_acknowledgements(monkeypatch):
    monkeypatch.setenv("MIGRATION_DATABASE_URL", "must-not-be-used")
    with pytest.raises(runner.MigrationBlocked, match="authorization"):
        runner.main(["--execute", "--operator-identity", "change/test"])
    with pytest.raises(runner.MigrationBlocked, match="operator-identity"):
        runner.main(["--execute", "--authorization", "MIGRATION_013_APPROVED"])


def test_runtime_database_url_is_deliberately_ignored(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "must-not-be-used")
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)
    with pytest.raises(runner.MigrationBlocked, match="MIGRATION_DATABASE_URL"):
        runner.main([
            "--execute", "--authorization", "MIGRATION_013_APPROVED",
            "--operator-identity", "change/test",
        ])
