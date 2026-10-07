"""Controlled, operator-invoked runner for NEXT-04A migration 013.

This module is intentionally absent from application startup and deploy workflows.
The default command is a filesystem-only dry run. Database execution requires two
explicit acknowledgements and a dedicated MIGRATION_DATABASE_URL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2 import sql

MIGRATION_ID = "013_rls_fail_closed_foundation"
MIGRATION_PATH = Path(__file__).resolve().parents[1] / "app/storage/migrations/013_rls_fail_closed_foundation.sql"
EXPECTED_SHA256 = "858583ad8c1c4a0c056be10fe998348d302561e9f040f5b3a0915c3e9281860d"
LOCK_NAMESPACE = "bridge-hub:production:migrations:v1"
ADVISORY_LOCK_KEY = -1839300086051708910
PROTECTED_TABLES = (
    "counterparties", "processed_documents", "journal_drafts", "waybills",
    "tax_invoices", "commercial_invoices", "triangle_matches",
    "document_corrections", "outgoing_invoices",
)
CONTROL_TABLE = "bridgehub_migration_history"


class MigrationBlocked(RuntimeError):
    """A safety gate prevented execution."""


def migration_bytes() -> bytes:
    return MIGRATION_PATH.read_bytes()


def migration_checksum(payload: bytes | None = None) -> str:
    return hashlib.sha256(payload if payload is not None else migration_bytes()).hexdigest()


def validate_artifact(payload: bytes | None = None) -> bytes:
    body = payload if payload is not None else migration_bytes()
    actual = migration_checksum(body)
    if actual != EXPECTED_SHA256:
        raise MigrationBlocked(f"migration checksum mismatch: expected {EXPECTED_SHA256}, got {actual}")
    return body


def _one(cur, sql: str, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def _verify_prerequisites(cur, schema: str) -> tuple[str, str]:
    session_user, current_user, is_super, bypass = _one(
        cur,
        """SELECT session_user, current_user, r.rolsuper, r.rolbypassrls
             FROM pg_roles r WHERE r.rolname = current_user""",
    )
    if is_super or bypass:
        raise MigrationBlocked("migration role must be NOSUPERUSER and NOBYPASSRLS")
    cur.execute(
        """SELECT v.name
             FROM unnest(%s::text[]) AS v(name)
             LEFT JOIN pg_class c ON c.oid = to_regclass(quote_ident(%s) || '.' || quote_ident(v.name))
            WHERE c.oid IS NULL OR pg_get_userbyid(c.relowner) <> current_user""",
        (list(PROTECTED_TABLES), schema),
    )
    missing_or_not_owned = [row[0] for row in cur.fetchall()]
    if missing_or_not_owned:
        raise MigrationBlocked("migration role must own every protected table: " + ", ".join(missing_or_not_owned))
    exists = _one(cur, "SELECT to_regclass(%s)", (f"{schema}.{CONTROL_TABLE}",))[0]
    if exists is None:
        raise MigrationBlocked(f"required control table {schema}.{CONTROL_TABLE} is missing")
    return session_user, current_user


def _verify_result(cur, schema: str) -> None:
    cur.execute(
        """SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                  count(p.polname),
                  count(p.polname) FILTER (WHERE p.polname = 'tenant_fail_closed_' || c.relname)
             FROM pg_class c
             JOIN pg_namespace n ON n.oid = c.relnamespace
             LEFT JOIN pg_policy p ON p.polrelid = c.oid
            WHERE n.nspname = %s AND c.relname = ANY(%s::text[])
            GROUP BY c.relname, c.relrowsecurity, c.relforcerowsecurity""",
        (schema, list(PROTECTED_TABLES)),
    )
    rows = cur.fetchall()
    bad = [name for name, enabled, forced, total_count, expected_count in rows
           if not enabled or not forced or total_count != 1 or expected_count != 1]
    found = {row[0] for row in rows}
    bad.extend(sorted(set(PROTECTED_TABLES) - found))
    if bad:
        raise MigrationBlocked("post-migration RLS verification failed: " + ", ".join(sorted(set(bad))))


def execute(conn, *, operator_identity: str, schema: str = "public", payload: bytes | None = None,
            lock_timeout: str = "5s", statement_timeout: str = "120s",
            inject_failure_before_verify: bool = False) -> dict:
    """Execute one guarded attempt. Intended for the controlled job and disposable tests."""
    body = validate_artifact(payload)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
        raise MigrationBlocked("schema must be a simple PostgreSQL identifier")
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    lock_acquired = False
    session_user = current_user = "unknown"
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SET LOCAL search_path TO {}, pg_catalog").format(sql.Identifier(schema)))
            cur.execute("SELECT set_config('lock_timeout', %s, true)", (lock_timeout,))
            cur.execute("SELECT set_config('statement_timeout', %s, true)", (statement_timeout,))
            lock_acquired = bool(_one(cur, "SELECT pg_try_advisory_xact_lock(%s)", (ADVISORY_LOCK_KEY,))[0])
            if not lock_acquired:
                raise MigrationBlocked("migration advisory lock is already held")
            session_user, current_user = _verify_prerequisites(cur, schema)
            existing = _one(
                cur,
                f"SELECT checksum FROM {schema}.{CONTROL_TABLE} WHERE migration_id=%s AND result='SUCCESS'",
                (MIGRATION_ID,),
            )
            if existing:
                if existing[0] != EXPECTED_SHA256:
                    raise MigrationBlocked("successful migration ID exists with a different checksum")
                conn.rollback()
                return {"migration_id": MIGRATION_ID, "result": "VERIFIED_NO_OP", "checksum": EXPECTED_SHA256}
            cur.execute(
                f"""INSERT INTO {schema}.{CONTROL_TABLE}
                    (run_id, migration_id, checksum, started_at, executor_identity,
                     session_user_name, current_user_name, result, transaction_status,
                     advisory_lock_acquired)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,'RUNNING','IN_TRANSACTION',TRUE)""",
                (run_id, MIGRATION_ID, EXPECTED_SHA256, started_at, operator_identity, session_user, current_user),
            )
            cur.execute(body.decode("utf-8"))
            if inject_failure_before_verify:
                raise RuntimeError("intentional disposable rehearsal failure")
            _verify_result(cur, schema)
            cur.execute(
                f"""UPDATE {schema}.{CONTROL_TABLE}
                       SET ended_at=clock_timestamp(), result='SUCCESS', error=NULL,
                           transaction_status='COMMITTED'
                     WHERE run_id=%s""",
                (run_id,),
            )
        conn.commit()
        return {"migration_id": MIGRATION_ID, "run_id": run_id, "result": "SUCCESS", "checksum": EXPECTED_SHA256}
    except Exception as exc:
        conn.rollback()
        if lock_acquired and current_user != "unknown":
            try:
                with conn.cursor() as audit_cur:
                    audit_cur.execute(
                        sql.SQL("""INSERT INTO {}.{} (
                            run_id, migration_id, checksum, started_at, ended_at,
                            executor_identity, session_user_name, current_user_name,
                            result, error, transaction_status, advisory_lock_acquired)
                            VALUES (%s,%s,%s,%s,clock_timestamp(),%s,%s,%s,
                                    'FAILED',%s,'ROLLED_BACK',TRUE)""").format(
                            sql.Identifier(schema), sql.Identifier(CONTROL_TABLE)
                        ),
                        (run_id, MIGRATION_ID, EXPECTED_SHA256, started_at, operator_identity,
                         session_user, current_user, str(exc)[:1000]),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
        raise


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--authorization", default="")
    parser.add_argument("--operator-identity", default="")
    parser.add_argument("--schema", default="public")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    checksum = migration_checksum()
    validate_artifact()
    if not args.execute:
        print(json.dumps({"migration_id": MIGRATION_ID, "checksum": checksum, "mode": "DRY_RUN", "database_access": False}))
        return 0
    if args.authorization != "MIGRATION_013_APPROVED":
        raise MigrationBlocked("--authorization MIGRATION_013_APPROVED is required")
    if not args.operator_identity:
        raise MigrationBlocked("--operator-identity is required")
    dsn = os.environ.get("MIGRATION_DATABASE_URL")
    if not dsn:
        raise MigrationBlocked("MIGRATION_DATABASE_URL is required; DATABASE_URL is deliberately ignored")
    with psycopg2.connect(dsn) as conn:
        result = execute(conn, operator_identity=args.operator_identity, schema=args.schema)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MigrationBlocked as exc:
        print(json.dumps({"result": "BLOCKED", "error": str(exc)}), file=sys.stderr)
        raise SystemExit(2)
