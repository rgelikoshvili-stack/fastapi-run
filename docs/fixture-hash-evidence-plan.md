# Bridge Hub - H46 Fixture Hash Evidence Plan

## 1. Title

H46 Fixture Hash Evidence Plan

## 2. Purpose

H46 defines how to record SHA-256 evidence for the synthetic posted ledger fixture before any future local Docker PostgreSQL provisioning execution.

Expected current decision: `READY_FOR_FIXTURE_HASH_CAPTURE`.

## 3. Fixture Target

Fixture target:

`tests/fixtures/posted_ledger/synthetic_posted_ledger_fixture_pack.json`

This is the only fixture allowed for the planned local disposable provisioning path.

## 4. Non-action Statement

H46 does not modify the fixture.
H46 does not load the fixture.
H46 does not create DB.
H46 does not connect to DB.
H46 does not run SQL.
H46 does not run migrations.
H46 does not run Docker.
H46 does not call runtime APIs.

## 5. Future Hash Command Template

PowerShell future template:

```powershell
Get-FileHash tests/fixtures/posted_ledger/synthetic_posted_ledger_fixture_pack.json -Algorithm SHA256
```

Bash future template:

```bash
sha256sum tests/fixtures/posted_ledger/synthetic_posted_ledger_fixture_pack.json
```

These templates are not executed in H46 unless a future task explicitly allows a purely local non-mutating hash capture. H46 itself records the plan only.

## 6. Hash Evidence Packet

Future hash evidence packet fields:
- `fixture_path`
- `algorithm`
- `sha256`
- `generated_at`
- `generated_by`
- `safe_to_use`

The evidence packet must state whether the fixture is safe to use and must not include production or customer data.

## 7. No-Go Blockers

No-go blockers:
- fixture missing
- hash missing
- file modified unexpectedly
- fixture path is not the synthetic posted ledger fixture
- production/customer data detected

## 8. Decision Outputs

Allowed decision outputs:
- `READY_FOR_FIXTURE_HASH_CAPTURE`
- `BLOCKED_FIXTURE_MISSING`
- `BLOCKED_HASH_NOT_CAPTURED`

Current H46 decision: `READY_FOR_FIXTURE_HASH_CAPTURE`.

## 9. Next Task

H49 or H50 depending on Docker state.
