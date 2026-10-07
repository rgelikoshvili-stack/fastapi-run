"""Disposable PostgreSQL 16 rehearsal for the controlled migration 013 runner."""
import os
import uuid
from urllib.parse import urlparse

import psycopg2
import pytest
from psycopg2 import sql

from scripts import run_migration_013_controlled as runner


def _admin_url():
    value = os.getenv("NEXT04A_TEST_DATABASE_URL")
    if not value:
        pytest.skip("NEXT04A_TEST_DATABASE_URL is required for disposable PostgreSQL proof")
    parsed = urlparse(value)
    assert parsed.hostname in {"127.0.0.1", "localhost", "::1", "postgres"}
    return value, parsed


@pytest.fixture
def rehearsal_db():
    admin_url, parsed = _admin_url()
    suffix = uuid.uuid4().hex[:10]
    schema = f"n04a11_{suffix}"
    role = f"n04a11_role_{suffix}"
    password = f"synthetic_{suffix}"
    with psycopg2.connect(admin_url) as admin:
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE").format(sql.Identifier(role)), (password,))
            cur.execute(sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(sql.Identifier(schema), sql.Identifier(role)))
            for table in runner.PROTECTED_TABLES:
                cur.execute(sql.SQL("CREATE TABLE {}.{} (id bigint PRIMARY KEY, tenant_id text NOT NULL, payload text)").format(sql.Identifier(schema), sql.Identifier(table)))
                cur.execute(sql.SQL("ALTER TABLE {}.{} OWNER TO {}").format(sql.Identifier(schema), sql.Identifier(table), sql.Identifier(role)))
                cur.execute(sql.SQL("ALTER TABLE {}.{} ENABLE ROW LEVEL SECURITY").format(sql.Identifier(schema), sql.Identifier(table)))
                cur.execute(sql.SQL("CREATE POLICY legacy_allow_all ON {}.{} USING (true) WITH CHECK (true)").format(sql.Identifier(schema), sql.Identifier(table)))
            cur.execute(sql.SQL("""CREATE TABLE {}.{} (
                run_id uuid PRIMARY KEY, migration_id text NOT NULL, checksum text NOT NULL,
                started_at timestamptz NOT NULL, ended_at timestamptz,
                executor_identity text NOT NULL, session_user_name text NOT NULL,
                current_user_name text NOT NULL, result text NOT NULL, error text,
                transaction_status text NOT NULL, advisory_lock_acquired boolean NOT NULL)""").format(sql.Identifier(schema), sql.Identifier(runner.CONTROL_TABLE)))
            cur.execute(sql.SQL("ALTER TABLE {}.{} OWNER TO {}").format(sql.Identifier(schema), sql.Identifier(runner.CONTROL_TABLE), sql.Identifier(role)))
            cur.execute(sql.SQL("CREATE UNIQUE INDEX {} ON {}.{} (migration_id) WHERE result='SUCCESS'").format(sql.Identifier(f"one_success_{suffix}"), sql.Identifier(schema), sql.Identifier(runner.CONTROL_TABLE)))
    kwargs = dict(host=parsed.hostname, port=parsed.port or 5432, dbname=parsed.path.lstrip("/"), user=role, password=password)
    with psycopg2.connect(**kwargs) as seed:
        with seed.cursor() as cur:
            cur.execute(sql.SQL("INSERT INTO {}.counterparties VALUES (1,'tenant-a','A'),(2,'tenant-b','B')").format(sql.Identifier(schema)))
    try:
        yield admin_url, kwargs, schema
    finally:
        with psycopg2.connect(admin_url) as admin:
            admin.autocommit = True
            with admin.cursor() as cur:
                cur.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
                cur.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_success_duplicate_isolation_and_force_rls(rehearsal_db):
    _, kwargs, schema = rehearsal_db
    with psycopg2.connect(**kwargs) as conn:
        result = runner.execute(conn, operator_identity="disposable/test", schema=schema)
        assert result["result"] == "SUCCESS"
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.current_tenant_id','tenant-a',true)")
            cur.execute(sql.SQL("SELECT id FROM {}.counterparties ORDER BY id").format(sql.Identifier(schema)))
            assert cur.fetchall() == [(1,)]
            cur.execute(sql.SQL("UPDATE {}.counterparties SET payload='forged' WHERE id=2").format(sql.Identifier(schema)))
            assert cur.rowcount == 0
            conn.rollback()
            cur.execute(sql.SQL("SELECT id FROM {}.counterparties").format(sql.Identifier(schema)))
            assert cur.fetchall() == []
            conn.rollback()
        assert runner.execute(conn, operator_identity="disposable/test", schema=schema)["result"] == "VERIFIED_NO_OP"


def test_lock_contention_stops_second_runner(rehearsal_db):
    _, kwargs, schema = rehearsal_db
    with psycopg2.connect(**kwargs) as holder, psycopg2.connect(**kwargs) as contender:
        with holder.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (runner.ADVISORY_LOCK_KEY,))
        with pytest.raises(runner.MigrationBlocked, match="already held"):
            runner.execute(contender, operator_identity="disposable/contender", schema=schema)
        with holder.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(%s)", (runner.ADVISORY_LOCK_KEY,))


def test_intentional_failure_rolls_back_all_policy_changes(rehearsal_db):
    _, kwargs, schema = rehearsal_db
    with psycopg2.connect(**kwargs) as conn:
        with pytest.raises(RuntimeError, match="intentional"):
            runner.execute(conn, operator_identity="disposable/failure", schema=schema, inject_failure_before_verify=True)
        with conn.cursor() as cur:
            cur.execute("""SELECT count(*) FROM pg_policies
                            WHERE schemaname=%s AND policyname LIKE 'tenant_fail_closed_%%'""", (schema,))
            assert cur.fetchone()[0] == 0
            cur.execute("SELECT count(*) FROM pg_policies WHERE schemaname=%s AND policyname='legacy_allow_all'", (schema,))
            assert cur.fetchone()[0] == len(runner.PROTECTED_TABLES)
            cur.execute(sql.SQL("SELECT result, transaction_status FROM {}.{} ORDER BY started_at").format(sql.Identifier(schema), sql.Identifier(runner.CONTROL_TABLE)))
            assert cur.fetchall() == [("FAILED", "ROLLED_BACK")]
