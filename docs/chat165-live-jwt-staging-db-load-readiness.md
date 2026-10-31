# Bridge Hub — Chat165: access JWT live-check staging-readiness and DB workload

**Date:** 2026-10-27. Draft PR #154 only. **No live Staging or Production deployment, database connection, migration, flag update or cloud billing change was made.**

## What has and has not been proved

| Property | Verification source | Status |
|---|---|---|
| Live JWT membership logic against real PostgreSQL | Chat164 disposable PostgreSQL 15/16 | PASS in synthetic CI |
| `users` schema matches app's own DDL | Chat165 `app.api.models.user.create_users_table()` on isolated PG 15/16 | CI test; see Checks |
| Two companies, same email but separate user IDs | Chat165 model-backed integration | CI test; see Checks |
| Disabled / role-changed user rejected with guard enabled | Chat165 model-backed integration | CI test; see Checks |
| Connection tenant context resets after request | Chat165 model-backed integration | CI test; see Checks |
| 60 sequential / 80 concurrent synthetic membership reads | Chat165 local disposable DB diagnostic | Metric output in workflow logs; **NOT** Cloud SQL SLA |
| Real staging service + isolated DB (persistent) | No confirmed infrastructure evidence | **UNKNOWN / not provisioned** |
| Real Production schema/roles, RLS and customer legacy tokens | No Production DB query performed | **UNVERIFIED** |
| Real Cloud Run multi-replica / Cloud SQL proxy latency | No cloud load test performed | **UNVERIFIED** |
| Production setting `ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK=1` | Not authorized or executed | **OFF by default** |

## Completed preparation (Draft code only)
- Added `tests/integration/test_chat165_auth_staging_readiness_postgres.py`: creates a unique disposable test schema, executes the *application's* `create_users_table()`, validates column types/index and two-tenant isolation, verifies HTTP middleware against a synthetic signed JWT and role revocation, and prints structured local PostgreSQL latency metrics for 60 sequential and 80 concurrent authorization DB reads. No actual customer data or credentials.
- The integration suite enforces localhost-only DB host `127.0.0.1`, port `55442`, database `bridge_hub_chat162_test`, user `chat162_test_user`; other hosts raise errors before connection. CI runs PostgreSQL 15 and 16.
- `.github/workflows/chat162-oauth-state-postgres.yml` executes the new model-backed tests and prints the `CHAT165_LOCAL_POSTGRES_AUTH_BENCHMARK` JSON line to job logs. These CI timings are **diagnostics, not go-live performance approval**.
- Fixed the SaaS signup response's `expires_in` field to derive from the same 24-hour `ACCESS_TOKEN_EXPIRE_HOURS` used for signed access JWTs instead of incorrectly reporting 3600 seconds. Does not change actual token lifetime.
- Added `docs/sql/chat165_read_only_auth_staging_preflight.sql`, an explicitly **read-only** SQL report of PostgreSQL major version, `users` and `oauth_login_states` columns, indexes, RLS policies and current DB role rights. This is a procedure for *future approved isolated staging*, **NOT executed** here.

## Required independent staging gate (not done)
1. Owner authorizes staging compute + isolated PostgreSQL project/instance/network and cost. Verify separate GCP project, credentials and traffic isolation from `bridge-hub-db`. Neither local CI nor an unknown Cloud SQL instance qualifies automatically.
2. Create a clean staging database at the correct major version, with current approved schema/migrations and synthetic data, no Production data or production secrets.
3. Execute read-only preflight against staging and save evidence: `docs/sql/chat165_read_only_auth_staging_preflight.sql`. Confirm runtime role can SELECT scoped users, permissions, non-bypassable tenant RLS on sensitive business tables and migration 014 present.
4. Deploy candidate revision to isolated staging with `ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK=1` **only after migration 014**, and verify login, signup, OAuth provider callbacks, refresh, normal UI, WebSocket, downloads, posting/approvals, role changes and DB fail-closed behavior.
5. Conduct an actual Cloud Run/Cloud SQL proxy performance test (representative concurrency, p50/p95/p99 latency, DB connection pool usage, error rate, costs) under a pre-agreed SLO, and record rollback and session re-login behavior. The CI benchmark must not be used as production sizing evidence.
6. Approval is separately required to configure backups/PITR, restore to a new isolated instance, merge a deployment-triggering PR or change Production service variables.

## Outstanding security risks
- Disabling or transferring a user is rechecked per HTTP request **only when the flag is ON**; flag remains OFF by default and no staging activation occurred.
- Password reset/change does not automatically invalidate previously issued access/refresh JWTs when role/email/tenant remain the same. A revocation epoch/session version or equivalent explicit token family invalidation remains a **P0 design gap**.
- Open WebSocket connections recheck at 30-second intervals, not guaranteed instant revocation on broadcasts.
- OAuth state table migration 014 remains unapplied to Production. External Google/Microsoft login E2E has not been tested.
- Proxy-based rate limit, Redis fallback, production data restoration, Git ACL parity and local unresolved merge remain HOLD.

**Release decision:** Technical CI is a prerequisite, not production readiness. **HOLD**, with zero Production changes.
