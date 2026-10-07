"""NEXT-04A RLS proofs against an explicitly disposable PostgreSQL 16 DB."""

import asyncio
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool
from psycopg2.errors import InsufficientPrivilege
import pytest

from app.api import db
from app.api.services import worker_client
from app.api.services import ocr_callback_receipts
from app.startup.background import run_autopilot_tenant_work, run_email_tenant_work
from app.startup.migrations_indexes import run_index_migrations


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
                cur.execute(
                    "INSERT INTO journal_drafts (tenant_id) "
                    "VALUES ('tenant-a'), ('tenant-b')"
                )

                migration = Path("app/storage/migrations/013_rls_fail_closed_foundation.sql")
                cur.execute(migration.read_text(encoding="utf-8"))
                # Reapplying the forward migration must remain deterministic.
                cur.execute(migration.read_text(encoding="utf-8"))
                cur.execute(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"')

                migration = Path("app/storage/migrations/014_ocr_callback_receipts.sql")
                cur.execute(migration.read_text(encoding="utf-8"))
                cur.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "{schema}" TO "{role}"')
                cur.execute(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA "{schema}" TO "{role}"')
                cur.execute(
                    "ALTER TABLE processed_documents ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'processing'"
                )
                cur.execute("ALTER TABLE processed_documents ADD COLUMN IF NOT EXISTS gcs_path TEXT")
                cur.execute("INSERT INTO processed_documents (tenant_id, file_hash, file_name, gcs_path) "
                            "VALUES ('tenant-a', 'synthetic-ocr-a', 'a.pdf', 'gs://synthetic/a.pdf') RETURNING id")
                doc_a = cur.fetchone()[0]
                cur.execute("INSERT INTO processed_documents (tenant_id, file_hash, file_name, gcs_path) "
                            "VALUES ('tenant-b', 'synthetic-ocr-b', 'b.pdf', 'gs://synthetic/b.pdf') RETURNING id")
                doc_b = cur.fetchone()[0]
        app_pool = pool.ThreadedConnectionPool(4, 4, dsn)
        initialized_connections = []
        for _ in range(4):
            pooled_conn = app_pool.getconn()
            with pooled_conn:
                with pooled_conn.cursor() as cur:
                    cur.execute(f'SET search_path TO "{schema}"')
                    cur.execute(f'SET ROLE "{role}"')
            initialized_connections.append(pooled_conn)
        for pooled_conn in initialized_connections:
            app_pool.putconn(pooled_conn)
        yield {"pool": app_pool, "schema": schema, "role": role, "doc_a": doc_a, "doc_b": doc_b}
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


def _read_counterparty_tenants():
    conn = db.get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT tenant_id FROM counterparties ORDER BY tenant_id")
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def _read_draft_tenants():
    conn = db.get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT tenant_id FROM journal_drafts ORDER BY tenant_id")
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def _bind_runtime_pool(monkeypatch, rls_db):
    monkeypatch.setattr(db, "_get_sync_pool", lambda: rls_db["pool"])


class _AsyncPsycopgAdapter:
    """Async-shaped adapter; every statement still executes on disposable PostgreSQL."""
    def __init__(self, conn):
        self.conn = conn

    @staticmethod
    def _sql(statement):
        return re.sub(r"\$\d+", "%s", statement)

    def _fetchrow(self, statement, args):
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(self._sql(statement), args)
            row = cur.fetchone()
            return dict(row) if row else None

    async def fetchrow(self, statement, *args):
        return await asyncio.to_thread(self._fetchrow, statement, args)

    def _execute(self, statement, args):
        with self.conn.cursor() as cur:
            cur.execute(self._sql(statement), args)
            return f"{cur.statusmessage} {cur.rowcount}"

    async def execute(self, statement, *args):
        return await asyncio.to_thread(self._execute, statement, args)


@asynccontextmanager
async def _async_db_context():
    conn = db.get_db()
    try:
        yield _AsyncPsycopgAdapter(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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


def test_index_startup_is_safe_with_fail_closed_rls_and_missing_context(rls_db):
    """Startup schema/index work cannot read or mutate protected tenant rows."""
    conn = _acquire(rls_db)
    try:
        with conn.cursor() as cur:
            # The fixture uses the non-owner, NOSUPERUSER, NOBYPASSRLS role and
            # migration 013 is active. No tenant GUC is set for this startup.
            cur.execute("SELECT count(*) FROM journal_drafts")
            before = cur.fetchone()[0]
            assert before == 0

            run_index_migrations(cur)

            cur.execute("SELECT count(*) FROM journal_drafts")
            assert cur.fetchone()[0] == 0
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


@pytest.mark.asyncio
async def test_email_worker_context_scopes_each_tenant_and_resets_between_iterations(
    rls_db, monkeypatch
):
    _bind_runtime_pool(monkeypatch, rls_db)

    async def mocked_collect(tenant_id):
        return tenant_id, _read_counterparty_tenants()

    assert await run_email_tenant_work("tenant-a", mocked_collect) == (
        "tenant-a", ["tenant-a"]
    )
    assert db._current_tenant_id.get() is None
    assert await run_email_tenant_work("tenant-b", mocked_collect) == (
        "tenant-b", ["tenant-b"]
    )
    assert db._current_tenant_id.get() is None


@pytest.mark.asyncio
async def test_failed_email_tenant_work_cannot_leak_context_to_next_tenant(
    rls_db, monkeypatch
):
    _bind_runtime_pool(monkeypatch, rls_db)

    async def fail_after_scoped_read(_tenant_id):
        assert _read_counterparty_tenants() == ["tenant-a"]
        raise RuntimeError("synthetic tenant worker failure")

    with pytest.raises(RuntimeError, match="synthetic tenant worker failure"):
        await run_email_tenant_work("tenant-a", fail_after_scoped_read)
    assert db._current_tenant_id.get() is None

    async def read_scoped(tenant_id):
        return tenant_id, _read_counterparty_tenants()

    assert await run_email_tenant_work("tenant-b", read_scoped) == (
        "tenant-b", ["tenant-b"]
    )


@pytest.mark.asyncio
async def test_autopilot_executor_is_scoped_and_cannot_update_other_tenant_draft(
    rls_db, monkeypatch
):
    _bind_runtime_pool(monkeypatch, rls_db)

    def synthetic_autopilot(tenant_id):
        conn = db.get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT tenant_id FROM journal_drafts ORDER BY tenant_id")
                visible = [row[0] for row in cur.fetchall()]
                cur.execute(
                    "UPDATE journal_drafts SET document_number = 'blocked' "
                    "WHERE tenant_id = %s",
                    ("tenant-b",),
                )
                return visible, cur.rowcount
        finally:
            conn.close()

    visible, changed = await run_autopilot_tenant_work("tenant-a", synthetic_autopilot)
    assert visible == ["tenant-a"]
    assert changed == 0
    assert db._current_tenant_id.get() is None


def test_unscoped_admin_or_background_draft_lookup_fails_closed(rls_db, monkeypatch):
    _bind_runtime_pool(monkeypatch, rls_db)
    assert db._current_tenant_id.get() is None
    assert _read_counterparty_tenants() == []
    assert _read_draft_tenants() == []


@pytest.mark.asyncio
async def test_scheduled_report_context_and_pool_reuse_are_tenant_scoped(
    rls_db, monkeypatch
):
    _bind_runtime_pool(monkeypatch, rls_db)
    first = await db.run_in_tenant_executor("tenant-a", _read_counterparty_tenants)
    second = await db.run_in_tenant_executor("tenant-b", _read_counterparty_tenants)
    assert first == ["tenant-a"]
    assert second == ["tenant-b"]
    assert db._current_tenant_id.get() is None


@pytest.mark.asyncio
async def test_ocr_callback_body_hint_cannot_establish_arbitrary_tenant_context(
    rls_db, monkeypatch
):
    _bind_runtime_pool(monkeypatch, rls_db)
    monkeypatch.setattr(
        worker_client,
        "verify_callback_token",
        lambda token: {
            "tenant_id": "tenant-a", "doc_id": 17, "job_type": "ocr", "job_id": "job-a"
        } if token == "server-signed-a" else None,
    )
    forged = {
        "callback_token": "server-signed-a",
        "tenant_id": "tenant-b",
        "doc_id": 17,
        "job_type": "ocr",
        "job_id": "job-a",
    }
    assert worker_client.authorize_callback_payload(forged) is None
    assert db._current_tenant_id.get() is None
    assert _read_counterparty_tenants() == []

    assert worker_client.authorize_callback_payload(
        {**forged, "tenant_id": "tenant-a", "job_id": "job-b"}
    ) is None
    assert worker_client.authorize_callback_payload(
        {key: value for key, value in forged.items() if key != "job_id"}
    ) is None
    assert db._current_tenant_id.get() is None

    valid = {**forged, "tenant_id": "tenant-a"}
    claims = worker_client.authorize_callback_payload(valid)
    assert claims["tenant_id"] == "tenant-a"
    async with db.tenant_db_context(claims["tenant_id"]):
        assert _read_counterparty_tenants() == ["tenant-a"]


def _receipt_counts():
    conn = db.get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM ocr_callback_receipts")
            return cur.fetchone()[0]
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_ocr_callback_receipts_are_durable_tenant_scoped_and_idempotent(
    rls_db, monkeypatch
):
    _bind_runtime_pool(monkeypatch, rls_db)
    monkeypatch.setattr(ocr_callback_receipts, "get_conn", _async_db_context)

    async def accept(job_id, doc_id, raw_text="synthetic OCR result"):
        async with db.tenant_db_context("tenant-a"):
            return await ocr_callback_receipts.accept_callback_result(
                tenant_id="tenant-a", job_id=job_id, doc_id=doc_id,
                job_type="ocr", status="ok", raw_text=raw_text,
                method="synthetic_worker",
            )

    async def register(job_id, doc_id):
        async with db.tenant_db_context("tenant-a"):
            return await ocr_callback_receipts.register_dispatch(
                tenant_id="tenant-a", doc_id=doc_id, job_id=job_id
            )

    assert _receipt_counts() == 0  # missing context fails closed
    with pytest.raises(ValueError, match="tenant DB context"):
        await ocr_callback_receipts.accept_callback_result(
            tenant_id="tenant-a", job_id="no-context", doc_id=rls_db["doc_a"],
            job_type="ocr", status="ok", raw_text="x", method="test",
        )

    assert (await register("job-first", rls_db["doc_a"]))["send"] is True
    assert await accept("job-first", rls_db["doc_a"]) == "accepted"
    assert await accept("job-first", rls_db["doc_a"]) == "duplicate"
    assert await accept("job-first", rls_db["doc_a"], "conflicting text") == "conflict"
    assert _receipt_counts() == 0  # no-context visibility never widens to global rows

    def inspect_accepted_state():
        with db.tenant_db_context_sync("tenant-a"):
            conn = db.get_db("tenant-a")
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT raw_text FROM processed_documents WHERE id=%s AND tenant_id=%s",
                        (rls_db["doc_a"], "tenant-a"),
                    )
                    raw_text = cur.fetchone()[0]
                    cur.execute(
                        "SELECT duplicate_attempts, conflict_attempts FROM ocr_callback_receipts "
                        "WHERE tenant_id=%s AND job_id=%s",
                        ("tenant-a", "job-first"),
                    )
                    counters = cur.fetchone()
                    return raw_text, counters
            finally:
                conn.close()

    raw_text, counters = inspect_accepted_state()
    assert raw_text == "synthetic OCR result"
    assert counters == (1, 1)

    async with db.tenant_db_context("tenant-a"):
        await ocr_callback_receipts.complete_callback("tenant-a", "job-first")
    # Simulate a callback retry after a process restart/new DB checkout.
    assert await accept("job-first", rls_db["doc_a"]) == "duplicate"

    assert (await register("job-concurrent", rls_db["doc_a"]))["send"] is True
    outcomes = await asyncio.gather(
        accept("job-concurrent", rls_db["doc_a"]),
        accept("job-concurrent", rls_db["doc_a"]),
    )
    assert sorted(outcomes) == ["accepted", "duplicate"]

    # A tenant-A dispatcher cannot create a receipt for tenant B's document;
    # an unregistered callback hint also cannot update it.
    assert await register("cross-tenant", rls_db["doc_b"]) is None
    assert await accept("cross-tenant", rls_db["doc_b"]) == "conflict"

    def inspect_receipt_absence():
        with db.tenant_db_context_sync("tenant-a"):
            conn = db.get_db("tenant-a")
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT count(*) FROM ocr_callback_receipts "
                        "WHERE tenant_id=%s AND job_id=%s",
                        ("tenant-a", "cross-tenant"),
                    )
                    return cur.fetchone()[0]
            finally:
                conn.close()

    assert inspect_receipt_absence() == 0  # failed document update rolled receipt back

    # Force a failure after the receipt row is locked/updated: the transaction
    # must roll that provisional receipt update back rather than leave a
    # partially accepted callback behind.
    with db.tenant_db_context_sync("tenant-a"):
        conn = db.get_db("tenant-a")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO processed_documents "
                    "(tenant_id, file_hash, file_name, gcs_path, status) "
                    "VALUES ('tenant-a', 'synthetic-ocr-rollback', 'rollback.pdf', "
                    "'gs://synthetic/rollback.pdf', 'processing') RETURNING id"
                )
                rollback_doc = cur.fetchone()[0]
            conn.commit()
        finally:
            conn.close()
    assert (await register("job-rollback", rollback_doc))["send"] is True
    with db.tenant_db_context_sync("tenant-a"):
        conn = db.get_db("tenant-a")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM processed_documents WHERE id=%s AND tenant_id='tenant-a'",
                    (rollback_doc,),
                )
            conn.commit()
        finally:
            conn.close()
    with pytest.raises(LookupError):
        await accept("job-rollback", rollback_doc)

    def inspect_rollback_receipt():
        with db.tenant_db_context_sync("tenant-a"):
            conn = db.get_db("tenant-a")
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT state, result_sha256 FROM ocr_callback_receipts "
                        "WHERE tenant_id='tenant-a' AND job_id='job-rollback'"
                    )
                    return cur.fetchone()
            finally:
                conn.close()

    assert inspect_rollback_receipt() == ("dispatched", None)


def test_ocr_callback_receipts_have_forced_fail_closed_rls(rls_db):
    conn = _acquire(rls_db)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT c.relrowsecurity, c.relforcerowsecurity, p.cmd, p.qual, p.with_check "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "JOIN pg_policies p ON p.schemaname=n.nspname AND p.tablename=c.relname "
                    "WHERE n.nspname=%s AND c.relname='ocr_callback_receipts'",
                    (rls_db["schema"],),
                )
                row = cur.fetchone()
                assert row[0:3] == (True, True, "ALL")
                assert "app.current_tenant_id" in row[3]
                assert "app.current_tenant_id" in row[4]
    finally:
        _release(rls_db, conn)


@pytest.mark.asyncio
async def test_background_context_rollback_and_pool_return_clear_tenant_scope(
    rls_db, monkeypatch
):
    _bind_runtime_pool(monkeypatch, rls_db)
    async with db.tenant_db_context("tenant-a"):
        conn = db.get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT tenant_id FROM counterparties")
            assert [row[0] for row in cur.fetchall()] == ["tenant-a"]
        conn.rollback()
        conn.close()
    assert db._current_tenant_id.get() is None
    assert _read_counterparty_tenants() == []
