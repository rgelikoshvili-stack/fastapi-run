# Bridge Hub — H52 Local Docker PostgreSQL Dry-Run Evidence Packet

## Evidence ID: DRY-RUN-EV-2026-H52-001

```json
{
  "evidence_id": "DRY-RUN-EV-2026-H52-001",
  "task": "11C-H52",
  "approval_id": "APPROVAL-2026-H50-001",
  "approved_by": "ROLANDI GELIKOSHVILI",
  "approved_by_email": "r.gelikoshvili@gmail.com",
  "expires_at": "2026-05-25T16:00:00Z",
  "executed_at": "2026-05-18T17:00:00Z",
  "scope": "local_docker_postgres_dry_run_only",

  "docker_context": "desktop-linux",
  "docker_endpoint": "npipe:////./pipe/dockerDesktopLinuxEngine",
  "host_classification": "local_only",
  "remote_context": false,
  "production_risk": false,

  "image": "postgres:16",
  "image_digest": "sha256:b6ccf02e9b47eac0d67b5eaa0ef56fd59163bffa5506f64e96ceb5053130ec86",
  "container_name": "bridge-hub-h52-postgres",
  "volume_name": "bridge-hub-h52-pgdata",
  "port": "127.0.0.1:55432->5432",
  "db_name": "bridge_hub_h52",
  "db_user": "bridge_hub_h52",
  "db_host": "127.0.0.1",
  "db_port": 55432,
  "local_only_proof": "port bound to 127.0.0.1 only; host=127.0.0.1; no external network exposure",

  "migration_path": "app/storage/migrations/011_posted_journal_entries_schema.sql",
  "migration_sha256": "F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA",
  "migration_execution_status": "SUCCESS",
  "tables_created": ["journal_entry_headers", "journal_entry_lines", "journal_entry_sources"],
  "indexes_created": 14,

  "fixture_path": "tests/fixtures/posted_ledger/synthetic_posted_ledger_fixture_pack.json",
  "fixture_sha256": "1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299",
  "fixture_type": "synthetic",
  "production_data": false,
  "fixture_load_status": "SUCCESS",

  "rows_inserted": {
    "journal_entry_headers": 15,
    "journal_entry_lines": 33,
    "journal_entry_sources": 4,
    "total": 52
  },

  "verification": {
    "headers_count": 15,
    "lines_count": 33,
    "sources_count": 4,
    "tenant_alpha_posted": 11,
    "tenant_alpha_correction": 1,
    "tenant_alpha_reversed": 1,
    "tenant_alpha_voided": 1,
    "tenant_beta_posted": 1,
    "trial_balance_tenant_alpha_standard_net_dr": "23945.00",
    "trial_balance_tenant_alpha_standard_net_cr": "23945.00",
    "balanced": true,
    "lines_with_both_dr_cr_positive": 0,
    "zero_amount_lines": 0,
    "empty_tenant_rows": 0,
    "index_count": 14
  },

  "no_secrets_committed": true,
  "no_production_db_url_committed": true,
  "no_real_pii": true,
  "no_real_company_data": true,
  "no_balance_ge_activation": true,
  "no_cloud_run_env_mutation": true,
  "no_posted_ledger_reports_enabled_in_production": true,

  "cleanup_status": "COMPLETE",
  "container_removed": true,
  "volume_removed": true,

  "final_decision": "SUCCESS_LOCAL_DOCKER_POSTGRES_DRY_RUN_COMPLETE"
}
```

---

## Fixture Metadata Confirmation

From `synthetic_posted_ledger_fixture_pack.json`:

| Field | Value |
|---|---|
| description | Synthetic posted-ledger fixture pack for Bridge Hub H25. ALL data is entirely synthetic and fictional. |
| no_pii | true |
| no_real_company | true |
| no_real_tax_id | true |
| no_real_bank_account | true |
| safe_to_commit | true |

---

## DB Target Proof

```sql
SELECT current_database(), current_user;
-- bridge_hub_h52 | bridge_hub_h52
```

- host: 127.0.0.1 (localhost-only bind)
- port: 55432 (H52-specific, avoids local Postgres collision)
- production DATABASE_URL: NOT USED
- Cloud SQL: NOT connected
- Railway/Supabase/remote Postgres: NOT connected

---

## No Secrets Committed Statement

No passwords, API keys, DATABASE_URLs with credentials, or secrets of any kind are committed to git in this task. The disposable local DB password was used only at runtime via env var and is not present in any committed file.
