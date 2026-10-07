"""NEXT-04A RLS proofs against an explicitly disposable PostgreSQL 16 DB."""

import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import psycopg2
from psycopg2 import pool
from psycopg2.errors import InsufficientPrivilege
import pytest


EXPECTED_HOST = "127.0.0.1"
EXPECTED_PORT = 55438
EXPECTED_DATABASE = "bridge_hub_next04a_test"
TABLES = (
    "counterparties",
    "processed_documents",
    "journal_drafts",
    "waybills",
    "tax_invoices",
    "commercial_invoices",
    "triangle_matches",
    "document_corrections",
    "outgoing_invoices",
)


def _disposable_dsn() -> str:
    dsn = os.environ.get("NEXT04A_TEST_DATABASE_URL", "")
    if not dsn:
        pytest.skip("NEXT04A_TEST_DATABASE_URL is not configured for disposable PostgreSQL")
    parsed = urlparse(dsn)
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or parsed.hostname != EXPECTED_HOST
        or parsed.port != EXPECTED_PORT
        or parsed.path.lstrip("/") != EXPECTED_DATABASE
    ):
        raise ValueError(
            "Refusing database target; NEXT-04A tests require only "
            f"{EXPECTED_HOST}:{EXPECTED_PORT}/{EXPECTED_DATABASE}."
        )
    return dsn


@pytest.fixture(scope="module")
def rls_db():
    dsn = _disposable_dsn()
    suffix = uuid4().hex[:12]
    schema = f"next04a_rls_{suffix}"
    role = f"next04a_runtime_{suffix}"
    admin = psycopg2.connect(dsn)
    app_pool = None
    try:
        with admin:
            with admin.cursor() as cur:
                cur.execute(f'CREATE SCHEMA "{schema}"')
                cur.execute(f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS')
                cur.execute(f'SET search_path TO "{schema}"')
                # Minimal pre-existing application tables required by the real
                # 001–004 schema chain. All tenant data and schema are disposable.
                cur.execute("CREATE TABLE tenants (tenant_id TEXT PRIMARY KEY)")
                cur.execute(
                    "CREATE TABLE journal_drafts ("
                    "id SERIAL PRIMARY KEY, tenant_id TEXT NOT NULL, "
                    "document_series TEXT, document_number TEXT)"
                )
                for migration_name in (
                    "001_multi_tenant_schema.sql",
                    "002_row_level_security.sql",
                    "003_triangle_schema.sql",
                    "004_outgoing_invoices.sql",
                ):
                    migration_path = Path("app/storage/migrations") / migration_name
                    cur.execute(migration_path.read_text(encoding="utf-8"))

                # Seed matched-looking rows after the historical migrations.
                cur.execute(
                    "INSERT INTO counterparties (tenant_id, inn, name) VALUES "
                    "('tenant-a', 'same-looking-inn', 'Synthetic A'), "
                    "('tenant-b', 'same-looking-inn', 'Synthetic B')"
                )

                migration = Path("app/storage/migrations/013_rls_fail_closed_foundation.sql")
                cur.execute(migration.read_text(encoding="utf-8"))
                # Reapplying the forward migration must remain deterministic.
                cur.execute(migration.read_text(encoding="utf-8"))
                cur.execute(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"')
                cur.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "{schema}" TO "{role}"')
                cur.execute(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA "{schema}" TO "{role}"')

        app_pool = pool.ThreadedConnectionPool(1, 1, dsn)
        pooled_conn = app_pool.getconn()
        with pooled_conn:
            with pooled_conn.cursor() as cur:
                cur.execute(f'SET search_path TO "{schema}"')
                cur.execute(f'SET ROLE "{role}"')
        app_pool.putconn(pooled_conn)
        yield {"pool": app_pool, "schema": schema, "role": role}
    finally:
        if app_pool is not None:
            app_pool.closeall()
        try:
            with admin:
                with admin.cursor() as cur:
                    cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                    cur.execute(f'DROP ROLE IF EXISTS "{role}"')
        finally:
            admin.close()


def _acquire(db):
    return db["pool"].getconn()


def _release(db, conn):
    db["pool"].putconn(conn)


def _set_local(cur, tenant_id):
    cur.execute("SELECT set_config('app.current_tenant_id', %s, true)", (tenant_id,))


def test_rls_allows_tenant_to_read_own_row(rls_db):
    conn = _acquire(rls_db)
    try:
        with conn:
            with conn.cursor() as cur:
                _set_local(cur, "tenant-a")
                cur.execute("SELECT tenant_id FROM counterparties WHERE tenant_id = 'tenant-a'")
                assert cur.fetchone() == ("tenant-a",)
    finally:
        _release(rls_db, conn)


def test_rls_tenant_a_cannot_read_tenant_b_row(rls_db):
    conn = _acquire(rls_db)
    try:
        with conn:
            with conn.cursor() as cur:
                _set_local(cur, "tenant-a")
                cur.execute("SELECT 1 FROM counterparties WHERE tenant_id = 'tenant-b'")
                assert cur.fetchone() is None
    finally:
        _release(rls_db, conn)


def test_rls_tenant_a_cannot_update_or_delete_tenant_b_row(rls_db):
    conn = _acquire(rls_db)
    try:
        with conn:
            with conn.cursor() as cur:
                _set_local(cur, "tenant-a")
                cur.execute("UPDATE counterparties SET name = 'attempted' WHERE tenant_id = 'tenant-b'")
                assert cur.rowcount == 0
                cur.execute("DELETE FROM counterparties WHERE tenant_id = 'tenant-b'")
                assert cur.rowcount == 0
    finally:
        _release(rls_db, conn)


def test_rls_with_check_rejects_cross_tenant_insert_and_update(rls_db):
    conn = _acquire(rls_db)
    try:
        with pytest.raises(InsufficientPrivilege):
            with conn:
                with conn.cursor() as cur:
                    _set_local(cur, "tenant-a")
                    cur.execute(
                        "INSERT INTO counterparties (tenant_id, inn, name) "
                        "VALUES ('tenant-b', 'forged', 'Forged')"
                    )

        with pytest.raises(InsufficientPrivilege):
            with conn:
                with conn.cursor() as cur:
                    _set_local(cur, "tenant-a")
                    cur.execute(
                        "UPDATE counterparties SET tenant_id = 'tenant-b' "
                        "WHERE tenant_id = 'tenant-a'"
                    )
    finally:
        _release(rls_db, conn)


@pytest.mark.parametrize("empty_context", [False, True], ids=["missing", "empty"])
def test_missing_or_empty_context_fails_closed(rls_db, empty_context):
    conn = _acquire(rls_db)
    try:
        with conn:
            with conn.cursor() as cur:
                if empty_context:
                    _set_local(cur, "")
                cur.execute("SELECT count(*) FROM counterparties")
                assert cur.fetchone() == (0,)
    finally:
        _release(rls_db, conn)


@pytest.mark.parametrize("rollback", [False, True], ids=["commit", "rollback"])
def test_transaction_end_clears_local_tenant_context(rls_db, rollback):
    conn = _acquire(rls_db)
    try:
        with conn.cursor() as cur:
            _set_local(cur, "tenant-a")
            cur.execute("SELECT current_setting('app.current_tenant_id', true)")
            assert cur.fetchone() == ("tenant-a",)
        conn.rollback() if rollback else conn.commit()
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM counterparties")
                assert cur.fetchone() == (0,)
    finally:
        _release(rls_db, conn)


def test_same_pooled_connection_reuse_cannot_leak_tenant_context(rls_db):
    first = _acquire(rls_db)
    with first:
            with first.cursor() as cur:
                _set_local(cur, "tenant-a")
                cur.execute("SELECT count(*) FROM counterparties")
                assert cur.fetchone() == (1,)
    _release(rls_db, first)

    second = _acquire(rls_db)
    try:
        assert second is first
        with second:
            with second.cursor() as cur:
                _set_local(cur, "tenant-b")
                cur.execute("SELECT tenant_id FROM counterparties WHERE tenant_id = 'tenant-a'")
                assert cur.fetchone() is None
                cur.execute("SELECT count(*) FROM counterparties")
                assert cur.fetchone() == (1,)
        with second:
            with second.cursor() as cur:
                cur.execute("SELECT count(*) FROM counterparties")
                assert cur.fetchone() == (0,)
    finally:
        _release(rls_db, second)


def test_nine_tables_have_single_forced_all_command_policy(rls_db):
    conn = _acquire(rls_db)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
                )
                assert cur.fetchone() == (rls_db["role"], False, False)
                for table in TABLES:
                    cur.execute(
                        "SELECT c.relrowsecurity, c.relforcerowsecurity, count(p.policyname), "
                        "bool_and(p.cmd = 'ALL'), bool_and(p.qual IS NOT NULL), "
                        "bool_and(p.with_check IS NOT NULL) "
                        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "LEFT JOIN pg_policies p ON p.schemaname = n.nspname AND p.tablename = c.relname "
                        "WHERE n.nspname = %s AND c.relname = %s "
                        "GROUP BY c.relrowsecurity, c.relforcerowsecurity",
                        (rls_db["schema"], table),
                    )
                    assert cur.fetchone() == (True, True, 1, True, True, True), table
    finally:
        _release(rls_db, conn)
