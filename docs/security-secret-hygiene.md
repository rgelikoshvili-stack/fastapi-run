# Bridge Hub — Security Secret Hygiene and Legacy Script Safety

## 1. Purpose

SEC-1 removes or neutralizes hardcoded credential risks found in legacy scripts.

Eight legacy scripts contained hardcoded production database host IPs, passwords,
and in one case SSH root credentials to a production server.  All have been
replaced with explicit environment variable requirements that fail closed when
not set, and production host guards that refuse to run against known production
IPs.

**SEC-1 is security cleanup only.**

---

## 2. Non-Action Statement

SEC-1 does not:

- Connect to any database.
- Execute any SQL.
- Execute any migration.
- Access the production database.
- Access the Cloud Run database.
- Rotate any credential (see Section 7).
- Activate Balance.ge.
- Enable any feature flag.
- Change any infrastructure.
- Change any runtime posting or approval behavior.

---

## 3. Removed / Neutralized Risks

| Risk | File | Before | After |
|---|---|---|---|
| Hardcoded production DB host | `scripts/run_001_migration.py` | `[production-ip-redacted]` default | `os.getenv("DB_HOST")` — fails if unset |
| Hardcoded production DB host | `scripts/run_002_migration.py` | `[production-ip-redacted]` default | `os.getenv("DB_HOST")` — fails if unset |
| Hardcoded production DB host | `scripts/run_bank_files_migration.py` | literal inline | `os.getenv("DB_HOST")` — fails if unset |
| Hardcoded production DB host | `scripts/run_learning_tenant_migration.py` | `[production-ip-redacted]` default | `os.getenv("DB_HOST")` — fails if unset |
| Hardcoded production DB host | `scripts/run_learning_pattern_upgrade_migration.py` | `[production-ip-redacted]` default | `os.getenv("DB_HOST")` — fails if unset |
| Hardcoded production DB host | `scripts/run_tenant_tables_migration.py` | `[production-ip-redacted]` default | `os.getenv("DB_HOST")` — fails if unset |
| Hardcoded production DB host | `scripts/run_tenant_migration.py` | `[production-ip-redacted]` default | `os.getenv("DB_HOST")` — fails if unset |
| Hardcoded DB password | all above scripts | `"<PLACEHOLDER_ONLY>"` default | `os.getenv("DB_PASSWORD")` — fails if unset |
| Hardcoded DB password in DB URL | `scripts/schema_check.py` | inline in URL string | `os.getenv("DB_URL")` — fails if unset |
| Hardcoded SSH host (production server) | `scripts/schema_check.py` | `[production-ssh-ip-redacted]` literal | `os.getenv("SSH_HOST")` — fails if unset; refuses known production IPs |
| Hardcoded SSH root password | `scripts/schema_check.py` | inline literal | `os.getenv("SSH_PASSWORD")` — fails if unset |
| Hardcoded production API URL | `scripts/audit_check.py` | production IP literal | `os.getenv("AUDIT_BASE_URL")` — fails if unset; refuses known production hosts |
| Hardcoded admin password | `scripts/audit_check.py` | inline literal | `os.getenv("AUDIT_PASSWORD")` — fails if unset |
| No production guard | all scripts above | no guard | `_KNOWN_PRODUCTION_HOSTS` set blocks execution against known production IPs |

---

## 4. Removed / Neutralized Risks — Summary

- Hardcoded DB host values replaced with env vars: **8 scripts**
- Hardcoded password-like values replaced with env vars: **8 scripts**
- Unsafe script defaults removed — scripts now fail closed without explicit env vars: **all 9 scripts**
- Production host detection added to all affected scripts
- SSH root credential risk neutralized in `schema_check.py`

---

## 5. Placeholder Policy

The following placeholders are the only allowed substitutes for real credential values in documentation, example configs, and code comments:

| Placeholder | Meaning |
|---|---|
| `<NON_PROD_DB_HOST>` | Non-production database host (localhost or approved test host) |
| `<NON_PROD_DB_PORT>` | Non-production database port |
| `<NON_PROD_DB_USER>` | Non-production database user |
| `<NON_PROD_DB_PASSWORD>` | Non-production database password |
| `<DISPOSABLE_DB>` | Name of a disposable/test database |
| `<PLACEHOLDER_ONLY>` | Generic placeholder — value must never be a real credential |
| `<NON_PROD_SSH_HOST>` | Non-production SSH host |
| `<NON_PROD_SSH_USER>` | Non-production SSH user |
| `<NON_PROD_SSH_PASSWORD>` | Non-production SSH password |

Example (docs only):
```
export DATABASE_URL=postgresql://<NON_PROD_DB_USER>:<NON_PROD_DB_PASSWORD>@<NON_PROD_DB_HOST>:<NON_PROD_DB_PORT>/<DISPOSABLE_DB>
```

---

## 6. Legacy Script Safety Rules

All legacy scripts in `scripts/` must follow these rules:

- **No default production hosts** — `os.getenv("DB_HOST")` with no default; fail closed if unset.
- **No default passwords** — `os.getenv("DB_PASSWORD")` with no default; fail closed if unset.
- **No embedded tokens or API keys** — all auth values must come from environment variables.
- **No automatic production DB target** — scripts must never fall back to a production host.
- **Require explicit env vars** — every required value must come from the environment.
- **Fail closed if env vars missing** — print a clear error and `sys.exit(1)`; never proceed.
- **Refuse known production IPs** — maintain a `_KNOWN_PRODUCTION_HOSTS` set and abort if matched.
- **Print target classification** — print the DB host being targeted before any connection.
- **Non-production contexts only** — scripts are for local, disposable, or staging use only.

---

## 7. Rotation Recommendation

If any real credential was ever committed or exposed in this repository's git
history, it must be rotated outside this PR through the relevant provider or
admin console.

**This PR removes the repo exposure of those credentials.  It does not rotate
the credentials themselves.**

Credentials that may require rotation if they were ever live:

- The DB password previously used as a hardcoded default in legacy scripts.
- The SSH root password for the server referenced in `scripts/schema_check.py`.
- The admin password previously hardcoded in `scripts/audit_check.py`.
- Any API key if it appears in git history.

Rotation must be performed by the engineer or admin who controls those accounts,
outside this PR, using the provider's credential management interface.

---

## 8. Verification Commands

Read-only scan to confirm no forbidden literals remain:

```bash
# Scan for forbidden credential patterns
# (Pattern list is defined in tests/unit/test_secret_hygiene_contract.py to avoid
# re-embedding raw forbidden literals in documentation.)
# Run the contract tests — they include the exhaustive scan:

# Run SEC-1 contract tests
JWT_SECRET=test-secret TEST_MODE=1 DATABASE_URL="" POSTED_LEDGER_REPORTS_ENABLED="" \
  python -m pytest tests/unit/test_secret_hygiene_contract.py -v

# Run full unit suite
JWT_SECRET=test-secret TEST_MODE=1 DATABASE_URL="" POSTED_LEDGER_REPORTS_ENABLED="" \
  python -m pytest tests/unit/ --tb=short -q
```

---

## 9. Non-Goals

SEC-1 does **not**:

- Connect to any database.
- Execute any SQL or migration.
- Change production database or Cloud Run configuration.
- Activate any ERP connector or Balance.ge.
- Enable any feature flag.
- Change any infrastructure.
- Change any runtime application business logic.
- Rotate credentials (see Section 7).

---

## 10. Next Task

Only after PR merge, deploy, and live verification:

**Option A: ENC-1 — Georgian Encoding / Mojibake Cleanup**

**Option B: 11C-H24 — Disposable DB Setup Dry-Run Execution**
Only with explicit human approval for DB creation.
