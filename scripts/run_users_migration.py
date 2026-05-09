"""Quarantined legacy users migration.

This script previously dropped and recreated the users table. It is retained
only as a traceable placeholder so accidental manual execution cannot destroy
auth data. User/auth schema changes must be handled by reviewed, additive
migrations instead.
"""

from __future__ import annotations

import sys


ARCHIVED_DANGEROUS_SQL = """
-- Archived historical behavior. Do not execute.
-- DROP TABLE IF EXISTS users;
-- CREATE TABLE users (...);
"""


def main() -> int:
    sys.stderr.write(
        "scripts/run_users_migration.py is quarantined and must not be executed. "
        "Use a reviewed additive auth schema migration instead.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
