"""
Bridge Hub management commands.

Usage:
    python manage.py migrate          — run DB migrations (schema changes only, safe to re-run)
    python manage.py migrate --check  — dry-run: verify DB connection, print migration count
"""
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("manage")


def cmd_migrate(args):
    dry_run = "--check" in args
    if dry_run:
        log.info("migrate --check: verifying DB connection...")
    else:
        log.info("Running DB migrations...")

    from app.startup.migrations import run_db_migrations
    try:
        if not dry_run:
            run_db_migrations()
            log.info("Migrations complete.")
        else:
            from app.api.db import get_db_sync
            conn = get_db_sync()
            conn.cursor().execute("SELECT 1")
            conn.close()
            log.info("DB connection OK — migrations would run on next deploy.")
    except Exception as exc:
        log.error("Migration failed: %s", exc)
        sys.exit(1)


COMMANDS = {
    "migrate": cmd_migrate,
}

if __name__ == "__main__":
    argv = sys.argv[1:]
    if not argv or argv[0] not in COMMANDS:
        print(__doc__)
        print("Available commands:", ", ".join(COMMANDS))
        sys.exit(0)
    COMMANDS[argv[0]](argv[1:])
