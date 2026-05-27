#!/usr/bin/env python3
"""scripts/migrate.py — Standalone DDL migration runner for CI/CD pre-deploy step.

Usage:
  DATABASE_URL="postgresql://..." python scripts/migrate.py          # live run
  python scripts/migrate.py --dry-run                               # validate imports, print plan
"""
import argparse
import logging
import os
import sys

# Ensure project root is on sys.path so app.* imports resolve
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MIGRATION_GROUPS = [
    "outgoing_invoices: sent_at, seller/buyer detail columns",
    "tenants: party_resolver columns + submit_token population",
    "tenant_id type normalisation (UUID→TEXT) on expenses/invoices/contracts/customers",
    "processed_documents: gcs_path, status, approved_by, approved_at, source_document_id",
    "journal_drafts: autopilot/DIE/learning columns",
    "learning_patterns: weighted scoring columns",
    "customers + customer_interactions CREATE IF NOT EXISTS",
    "contracts + contract_milestones CREATE IF NOT EXISTS",
    "run_table_migrations (expenses, invoices, collaboration, chat, idempotency, bank, pipeline)",
    "run_index_migrations (indexes, FX columns, constraints, data backfills)",
    "run_vault_migrations (credential_vault_credentials, audit_events)",
    "ensure_tenant_settings_table",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bridge Hub DDL migration runner")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate imports and print migration plan; make no DB changes",
    )
    return p.parse_args()


def dry_run() -> None:
    log.info("dry-run: validating migration module imports...")
    from app.startup.migrations import run_db_migrations            # noqa: F401
    from app.startup.migrations_tables import run_table_migrations   # noqa: F401
    from app.startup.migrations_indexes import run_index_migrations  # noqa: F401
    log.info("dry-run: all imports OK")
    log.info("dry-run: %d migration groups would execute:", len(MIGRATION_GROUPS))
    for i, group in enumerate(MIGRATION_GROUPS, 1):
        log.info("  [%02d] %s", i, group)
    log.info("dry-run: complete — no database changes made")


def live_run() -> None:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        log.error("DATABASE_URL env var is not set — cannot run migrations")
        sys.exit(1)

    # Log host only (never log credentials)
    host_hint = db_url.split("@")[-1] if "@" in db_url else "<host>"
    log.info("running DDL migrations against %s...", host_hint)

    from app.startup.migrations import run_db_migrations
    run_db_migrations()
    log.info("action=migrate_ok")


def main() -> None:
    args = parse_args()
    if args.dry_run:
        dry_run()
    else:
        live_run()


if __name__ == "__main__":
    main()
