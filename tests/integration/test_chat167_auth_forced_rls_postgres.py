"""Chat167: isolated PostgreSQL 15/16 nonowner, forced-RLS authentication proof.

Requires ONLY a disposable localhost database with the dedicated synthetic
CHAT162_TEST_DATABASE_URL. No Cloud SQL, Production or external credentials.
The users policy in this test is an intentionally strict hypothetical staging
policy; current Production users RLS policy is NOT established by this test.
The legacy password_reset_tokens table is not tenant-RLS-protected here.
"""
from datetime import datetime
from urllib.parse import urlsplit, parse_qs
from uuid import uuid4

import asyncpg
import pytest
from starlette.requests import Request

from app.api import db, routes_auth, routes_reports, routes_audit_trail, routes_oauth
from app.api.models.user import create_users_table, hash_password, verify_password
from app.api.services import auth_service


_EMAIL = "shared.chat167@example.test"
_OLD_PASSWORD = "Chat167OldPassword123!"
_ROLE_PASSWORD = "chat167-disposable-postgresql-only"


def disposable_dsn():
    import os

    dsn = os.environ.get("CHAT162_TEST_DATABASE_URL", "")
    if not dsn:
        pytest.skip("No disposable localhost PostgreSQL URL")
    u = urlsplit(dsn)
    if (
        u.scheme not in ("postgres", "postgresql")
        or u.hostname != "127.0.0.1" or u.port != 55442
        or u.path != "/bridge_hub_chat162_test"
        or u.username != "chat162_test_user"
    ):
        raise RuntimeError("Refusing Chat167 forced-RLS test outside disposable localhost")
    return dsn


def request(path, ip, headers=None):
    return Request({
        "type": "http", "method": "POST", "scheme": "http",
        "path": path, "raw_path": path.encode("ascii"),
        "query_string": b"", "headers": headers or [],
        "client": (ip, 43167), "server": ("127.0.0.1", 80),
        "http_version": "1.1",
    })


@pytest.fixture
async def auth_db(monkeypatch):
    dsn = disposable_dsn()
    suffix = uuid4().hex
    schema = "chat167_" + suffix
    role = "chat167_runtime_" + suffix
    admin = await asyncpg.connect(dsn)
    admin_pool = None
    runtime_pool = None
    schema_created = False
    role_created = False
    try:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        schema_created = True
        await admin.execute(
            f'CREATE ROLE "{role}" LOGIN PASSWORD '
            f"'{_ROLE_PASSWORD}' NOSUPERUSER NOBYPASSRLS"
        )
        role_created = True
        admin_pool = await asyncpg.create_pool(
            dsn, min_size=1, max_size=3, server_settings={"search_path": schema},
        )

        async def admin_pool_getter():
            return admin_pool

        monkeypatch.setattr(db, "get_pool", admin_pool_getter)
        await create_users_table()
        migration = __import__("pathlib").Path(
            "app/storage/migrations/015_user_auth_version.sql"
        ).read_text(encoding="utf-8")
        async with admin_pool.acquire() as conn:
            await conn.execute(migration)
            await conn.execute(migration)
            reset_migration = __import__("pathlib").Path(
                "app/storage/migrations/016_password_reset_tokens.sql"
            ).read_text(encoding="utf-8")
            await conn.execute(reset_migration)
            await conn.execute(reset_migration)  # idempotent privileged migration
            oauth_migration = __import__("pathlib").Path(
                "app/storage/migrations/014_durable_oauth_login_states.sql"
            ).read_text(encoding="utf-8")
            await conn.execute(oauth_migration)
            await conn.execute(oauth_migration)  # pre-provision, no runtime DDL
            old_hash = hash_password(_OLD_PASSWORD)
            alpha = await conn.fetchval(
                "INSERT INTO users(email,password_hash,tenant_id,role,is_active)"
                "VALUES($1,$2,'t_alpha','accountant',TRUE) RETURNING id",
                _EMAIL, old_hash,
            )
            beta = await conn.fetchval(
                "INSERT INTO users(email,password_hash,tenant_id,role,is_active)"
                "VALUES($1,$2,'t_beta','accountant',TRUE) RETURNING id",
                _EMAIL, old_hash,
            )
            await conn.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
            await conn.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")
            await conn.execute("""
                CREATE POLICY chat167_strict_users_tenant ON users FOR ALL
                USING (
                    nullif(current_setting('app.current_tenant_id',true),'')
                    IS NOT NULL
                    AND tenant_id = current_setting('app.current_tenant_id',true)
                )
                WITH CHECK (
                    nullif(current_setting('app.current_tenant_id',true),'')
                    IS NOT NULL
                    AND tenant_id = current_setting('app.current_tenant_id',true)
                )
            """)
            await conn.execute(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"')
            await conn.execute(
                f'GRANT SELECT,INSERT,UPDATE,DELETE '
                f'ON ALL TABLES IN SCHEMA "{schema}" TO "{role}"'
            )
            await conn.execute(
                f'GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA "{schema}" '
                f'TO "{role}"'
            )

        runtime_pool = await asyncpg.create_pool(
            host="127.0.0.1", port=55442, database="bridge_hub_chat162_test",
            user=role, password=_ROLE_PASSWORD, min_size=1, max_size=8,
            server_settings={"search_path": schema},
        )

        async def runtime_pool_getter():
            return runtime_pool

        monkeypatch.setattr(db, "get_pool", runtime_pool_getter)
        monkeypatch.setenv("JWT_SESSION_VERSION_ENABLED", "1")
        monkeypatch.delenv("ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK", raising=False)
        monkeypatch.setattr(
            auth_service, "_get_secret_key",
            lambda: "chat167-ephemeral-test-signing-key-only-not-real",
        )
        yield {
            "runtime": runtime_pool, "admin": admin_pool,
            "schema": schema, "role": role,
            "alpha": alpha, "beta": beta,
        }
    finally:
        if runtime_pool is not None:
            await runtime_pool.close()
        if admin_pool is not None:
            await admin_pool.close()
        try:
            if schema_created:
                await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
            if role_created:
                await admin.execute(f'DROP ROLE "{role}"')
        finally:
            await admin.close()


@pytest.mark.asyncio
async def test_nonowner_forced_rls_fails_closed_without_tenant(auth_db):
    async with auth_db["runtime"].acquire() as conn:
        identity = await conn.fetchrow(
            "SELECT current_user AS role, row_security_active('users') AS active"
        )
        assert identity["role"] == auth_db["role"]
        assert identity["active"] is True
        flags = await conn.fetchrow(
            "SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user"
        )
        assert flags["rolsuper"] is False
        assert flags["rolbypassrls"] is False
        # The running service role must NOT require CREATE to issue reset links.
        assert await conn.fetchval(
            "SELECT has_schema_privilege(current_user,current_schema(),'CREATE')"
        ) is False
        owner = await conn.fetchval(
            "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='users'::regclass"
        )
        assert owner != auth_db["role"]
        assert await conn.fetchval("SELECT count(*) FROM users") == 0
    async with db.tenant_db_context("t_alpha"):
        async with db.get_conn() as conn:
            assert await conn.fetchval("SELECT count(*) FROM users") == 1
            assert await conn.fetchval(
                "SELECT count(*) FROM users WHERE tenant_id='t_beta'"
            ) == 0
    async with auth_db["runtime"].acquire() as conn:
        assert await conn.fetchval(
            "SELECT current_setting('app.current_tenant_id',true)"
        ) in (None, "")


@pytest.mark.asyncio
async def test_password_login_and_refresh_use_nonowner_tenant_scope(auth_db):
    result = await auth_service.login(_EMAIL, _OLD_PASSWORD, "t_alpha")
    assert result["ok"] is True
    access_claims = auth_service.verify_token(result["access_token"])
    assert access_claims["auth_version"] == 1
    assert access_claims["tenant_id"] == "t_alpha"
    assert await auth_service.verify_live_access_membership(access_claims)
    refreshed = await auth_service.refresh_token(result["refresh_token"])
    assert refreshed and refreshed["access_token"]
    async with db.tenant_db_context("t_alpha"):
        async with db.get_conn() as conn:
            assert await conn.fetchval(
                "SELECT last_login IS NOT NULL FROM users WHERE id=$1",
                auth_db["alpha"],
            ) is True


@pytest.mark.asyncio
async def test_password_change_revokes_only_own_tenant_under_forced_rls(auth_db):
    from app.api.routes_auth import ChangePasswordRequest

    a = await auth_service.login(_EMAIL, _OLD_PASSWORD, "t_alpha")
    b = await auth_service.login(_EMAIL, _OLD_PASSWORD, "t_beta")
    assert a["ok"] and b["ok"]
    changed = await routes_auth.auth_change_password(
        ChangePasswordRequest(
            current_password=_OLD_PASSWORD,
            new_password="Chat167ChangedAlphaPassword!",
        ),
        request("/auth/change-password", "127.0.0.167"),
        "Bearer " + a["access_token"],
    )
    assert changed["ok"] is True
    assert not await auth_service.verify_live_access_membership(
        auth_service.verify_token(a["access_token"])
    )
    assert await auth_service.refresh_token(a["refresh_token"]) is None
    assert await auth_service.verify_live_access_membership(
        auth_service.verify_token(b["access_token"])
    )
    assert await auth_service.refresh_token(b["refresh_token"])
    assert (await auth_service.login(
        _EMAIL, "Chat167ChangedAlphaPassword!", "t_alpha"
    ))["ok"] is True


@pytest.mark.asyncio
async def test_forgot_and_reset_nonowner_forced_rls_preserves_other_tenant(auth_db, monkeypatch):
    from app.api.routes_auth import ForgotPasswordRequest, ResetPasswordRequest

    sent = []
    monkeypatch.setenv("APP_BASE_URL", "https://bridge.example.test")
    monkeypatch.delenv("PASSWORD_RESET_BASE_URL", raising=False)
    monkeypatch.setattr(
        routes_auth, "_send_reset_email", lambda email, link: sent.append((email, link))
    )
    forgot = await routes_auth.auth_forgot_password(
        ForgotPasswordRequest(email=_EMAIL, tenant_id="t_alpha"),
        request("/auth/forgot-password", "127.0.0.168", headers=[
            (b"host", b"reset-link-attacker.example"),
            (b"x-forwarded-host", b"reset-link-attacker.example"),
        ]),
    )
    assert forgot["ok"] is True
    assert len(sent) == 1
    link = urlsplit(sent[0][1])
    assert (link.scheme, link.netloc, link.path) == (
        "https", "bridge.example.test", "/static/reset_password.html"
    )
    assert "reset-link-attacker" not in sent[0][1]
    assert link.query == ""  # secret is not sent to the HTTP server
    token = parse_qs(link.fragment)["token"][0]
    assert parse_qs(link.fragment)["tenant_id"] == ["t_alpha"]
    async with auth_db["admin"].acquire() as conn:
        stored = await conn.fetchval(
            "SELECT token FROM password_reset_tokens "
            "WHERE email=$1 AND tenant_id='t_alpha'",
            _EMAIL,
        )
        assert stored == routes_auth._reset_token_storage_key(token)
        assert stored.startswith("sha256:") and token not in stored
    # A leaked database digest cannot be replayed as the raw reset code.
    digest_replay = await routes_auth.auth_reset_password(
        ResetPasswordRequest(
            token=stored, new_password="MustNotChangeWithDigest123!"
        ),
        request("/auth/reset-password", "127.0.0.170"),
    )
    assert digest_replay["ok"] is False
    assert digest_replay["error"]["code"] == "INVALID_TOKEN"
    a = await auth_service.login(_EMAIL, _OLD_PASSWORD, "t_alpha")
    b = await auth_service.login(_EMAIL, _OLD_PASSWORD, "t_beta")
    reset = await routes_auth.auth_reset_password(
        ResetPasswordRequest(token=token, new_password="Chat167ResetAlphaPassword!"),
        request("/auth/reset-password", "127.0.0.169"),
    )
    assert reset["ok"] is True
    assert await auth_service.refresh_token(a["refresh_token"]) is None
    assert await auth_service.refresh_token(b["refresh_token"])
    replay = await routes_auth.auth_reset_password(
        ResetPasswordRequest(token=token, new_password="IllegalReplayPassword!"),
        request("/auth/reset-password", "127.0.0.169"),
    )
    assert replay["ok"] is False
    assert replay["error"]["code"] == "TOKEN_USED"
    async with auth_db["admin"].acquire() as conn:
        rows = await conn.fetch(
            "SELECT id,auth_version,password_hash FROM users ORDER BY id"
        )
        assert len(rows) == 2
        by_id = {row["id"]: row for row in rows}
        assert by_id[auth_db["alpha"]]["auth_version"] == 2
        assert verify_password(
            "Chat167ResetAlphaPassword!", by_id[auth_db["alpha"]]["password_hash"]
        )
        assert by_id[auth_db["beta"]]["auth_version"] == 1
        assert verify_password(
            _OLD_PASSWORD, by_id[auth_db["beta"]]["password_hash"]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("tenant", ["t_alpha", "t_beta"])
async def test_oauth_callback_nonowner_forced_users_rls_resolves_exact_tenant(
    auth_db, monkeypatch, tenant
):
    """Provider-bound, one-use state scopes membership without role bypass.

    There are two synthetic active users with the same email in two tenants.
    Both provider requests are mocked: NO Google/Microsoft network traffic.
    """
    from unittest.mock import MagicMock

    class FakeProviderResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    monkeypatch.setenv("APP_BASE_URL", "https://bridge.example.test")
    monkeypatch.delenv("OAUTH_REDIRECT_BASE_URL", raising=False)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "synthetic-chat174-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "synthetic-chat174-secret")
    token_call = MagicMock(
        return_value=FakeProviderResponse({"access_token": "synthetic-provider-token"})
    )
    info_call = MagicMock(return_value=FakeProviderResponse({
        "email": _EMAIL, "email_verified": True, "name": "Synthetic Chat174",
    }))
    monkeypatch.setattr(routes_oauth._http, "post", token_call)
    monkeypatch.setattr(routes_oauth._http, "get", info_call)
    access = MagicMock(return_value="synthetic-access-chat174")
    refresh = MagicMock(return_value="synthetic-refresh-chat174")
    monkeypatch.setattr(routes_oauth, "create_access_token", access)
    monkeypatch.setattr(routes_oauth, "create_refresh_token", refresh)

    state = await routes_oauth._issue_state(tenant, "google")
    result = await routes_oauth.oauth_callback(
        "google",
        request("/auth/oauth/google/callback", "127.0.0.174"),
        code="synthetic-provider-code", state=state,
    )
    assert result.status_code == 200
    expected_id = auth_db["alpha" if tenant == "t_alpha" else "beta"]
    expected_claims = {
        "sub": str(expected_id), "tenant_id": tenant, "role": "accountant",
        "email": _EMAIL, "auth_version": 1,
    }
    access.assert_called_once_with(expected_claims)
    refresh.assert_called_once_with(expected_claims)
    assert token_call.call_args.kwargs["data"]["redirect_uri"] == (
        "https://bridge.example.test/auth/oauth/google/callback"
    )
    assert info_call.call_count == 1
    # Each provider-bound state is consumed once, even under forced RLS.
    replay = await routes_oauth.oauth_callback(
        "google",
        request("/auth/oauth/google/callback", "127.0.0.175"),
        code="synthetic-provider-code", state=state,
    )
    assert replay.status_code == 400
    assert b"OAUTH_STATE_INVALID" in replay.body
    async with auth_db["runtime"].acquire() as conn:
        assert await conn.fetchval(
            "SELECT current_setting('app.current_tenant_id', true)"
        ) in (None, "")
        assert await conn.fetchval("SELECT count(*) FROM users") == 0


@pytest.mark.asyncio
async def test_oauth_no_membership_cannot_join_another_tenant_under_forced_rls(
    auth_db, monkeypatch
):
    """Unknown company scope cannot inherit same-email membership elsewhere."""
    from unittest.mock import MagicMock

    class FakeProviderResponse:
        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self.data

    monkeypatch.setenv("APP_BASE_URL", "https://bridge.example.test")
    monkeypatch.delenv("OAUTH_REDIRECT_BASE_URL", raising=False)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "synthetic-chat174-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "synthetic-chat174-secret")
    monkeypatch.setattr(
        routes_oauth._http, "post",
        lambda *args, **kwargs: FakeProviderResponse({
            "access_token": "synthetic-provider-token"
        }),
    )
    monkeypatch.setattr(
        routes_oauth._http, "get",
        lambda *args, **kwargs: FakeProviderResponse({
            "email": _EMAIL, "email_verified": True,
        }),
    )
    mint = MagicMock(side_effect=AssertionError("must not grant access"))
    monkeypatch.setattr(routes_oauth, "create_access_token", mint)
    state = await routes_oauth._issue_state("t_gamma", "google")
    response = await routes_oauth.oauth_callback(
        "google",
        request("/auth/oauth/google/callback", "127.0.0.176"),
        code="synthetic-provider-code", state=state,
    )
    assert response.status_code == 403
    assert b"OAUTH_MEMBERSHIP_REQUIRED" in response.body
    mint.assert_not_called()



@pytest.mark.asyncio
async def test_chat175_signature_stamp_and_financial_audit_forced_rls(auth_db):
    """Actual nonowner runtime role with two tenants, forced RLS on every table.

    No real financial/Production data. The same signed tenant must bind RBAC,
    request state, PostgreSQL SET LOCAL and explicit query filters.
    """
    from app.api.routes_auth import SignatureRequest, StampRequest
    from fastapi import HTTPException

    png = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8"
        "AAwMCAO+hU2cAAAAASUVORK5CYII="
    )
    async with auth_db["admin"].acquire() as conn:
        await conn.execute("""
            CREATE TABLE tenants (
                tenant_id TEXT PRIMARY KEY, signature_b64 TEXT, stamp_b64 TEXT
            )
        """)
        await conn.execute("""
            INSERT INTO tenants(tenant_id,signature_b64,stamp_b64)
            VALUES ('t_alpha',NULL,NULL), ('t_beta','beta-original','beta-stamp')
        """)
        await conn.execute("""
            CREATE TABLE pipeline_runs (
                run_id TEXT PRIMARY KEY, filename TEXT, state TEXT,
                created_at TIMESTAMPTZ NOT NULL, tenant_id TEXT NOT NULL
            )
        """)
        await conn.execute("""
            INSERT INTO pipeline_runs(run_id,filename,state,created_at,tenant_id)
            VALUES ('alpha-run','alpha-secret.csv','APPROVED',
                    '2023-08-01'::timestamptz,'t_alpha'),
                   ('beta-run','beta-private.csv','REJECTED',
                    '2024-09-01'::timestamptz,'t_beta')
        """)
        await conn.execute("""
            CREATE TABLE audit_log (
                id BIGSERIAL PRIMARY KEY, tenant_id TEXT NOT NULL,
                actor TEXT, action TEXT, resource TEXT, resource_id TEXT,
                old_value TEXT, new_value TEXT, details TEXT,
                created_at TIMESTAMPTZ DEFAULT now()
            )
        """)
        await conn.execute("""
            INSERT INTO audit_log(tenant_id,actor,action,resource,resource_id,
                                  old_value,new_value,details)
            VALUES ('t_alpha','alice','UPDATE','expenses','77',NULL,
                    '{"amount":11}','alpha-only'),
                   ('t_beta','bob','UPDATE','expenses','77',NULL,
                    '{"amount":99999}','beta-only')
        """)
        for table in ("tenants", "pipeline_runs", "audit_log"):
            await conn.execute(
                f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"
            )
            await conn.execute(
                f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"
            )
            await conn.execute(f"""
                CREATE POLICY chat175_exact_tenant ON {table}
                FOR ALL
                USING (tenant_id = current_setting('app.current_tenant_id',true))
                WITH CHECK (
                    tenant_id = current_setting('app.current_tenant_id',true)
                )
            """)
            await conn.execute(
                f'GRANT SELECT,UPDATE ON {table} TO "{auth_db["role"]}"'
            )

    def signed_req(tenant="t_alpha", visible=None, role="admin"):
        r = request("/auth/signature", "127.0.0.175")
        r.state.authenticated = True
        r.state.role = role
        r.state.auth_tenant_id = tenant
        r.state.tenant_id = visible if visible is not None else tenant
        r.state.user_id = auth_db["alpha" if tenant == "t_alpha" else "beta"]
        return r

    # No signed DB scope: denial precedes all SQL.
    with pytest.raises(HTTPException) as no_scope:
        await routes_auth.get_signature(signed_req())
    assert no_scope.value.status_code == 403
    with db.authenticated_tenant_context("t_alpha"):
        alpha_req = signed_req()
        assert (await routes_auth.save_signature(
            SignatureRequest(signature_b64=png), alpha_req
        ))["ok"] is True
        assert (await routes_auth.save_stamp(
            StampRequest(stamp_b64=png), alpha_req
        ))["ok"] is True
        assert (await routes_auth.get_signature(alpha_req))["data"]["signature_b64"] == png
        assert (await routes_auth.get_stamp(alpha_req))["data"]["stamp_b64"] == png

        yearly = await routes_reports.annual_report(alpha_req)
        assert len(yearly["data"]["annual_reports"]) == 1
        assert int(yearly["data"]["annual_reports"][0]["year"]) == 2023
        trail = await routes_reports.audit_trail(alpha_req)
        assert [x["filename"] for x in trail["data"]["pipeline_runs"]] == [
            "alpha-secret.csv"
        ]
        recent = await routes_audit_trail.recent_changes(
            alpha_req, entity_type=None, actor=None, limit=20,
        )
        assert [x["details"] for x in recent["data"]["events"]] == ["alpha-only"]
        history = await routes_audit_trail.get_history(
            "expenses", 77, alpha_req, limit=20,
        )
        assert [x["details"] for x in history["data"]["history"]] == ["alpha-only"]

        # Forged X-Tenant-ID / request state cannot re-scope a signed JWT.
        with pytest.raises(HTTPException) as forged:
            await routes_auth.get_stamp(signed_req(visible="t_beta"))
        assert forged.value.status_code == 403
        with pytest.raises(HTTPException) as wrong_role:
            await routes_auth.get_signature(signed_req(role="viewer"))
        assert wrong_role.value.status_code == 403

    async with auth_db["admin"].acquire() as conn:
        beta = await conn.fetchrow(
            "SELECT signature_b64,stamp_b64 FROM tenants WHERE tenant_id='t_beta'"
        )
        assert beta["signature_b64"] == "beta-original"
        assert beta["stamp_b64"] == "beta-stamp"

    with db.authenticated_tenant_context("t_beta"):
        beta_req = signed_req(tenant="t_beta")
        assert (await routes_auth.get_signature(beta_req))["data"][
            "signature_b64"
        ] == "beta-original"
        beta_year = await routes_reports.annual_report(beta_req)
        assert int(beta_year["data"]["annual_reports"][0]["year"]) == 2024
        beta_recent = await routes_audit_trail.recent_changes(
            beta_req, entity_type=None, actor=None, limit=20,
        )
        assert [x["details"] for x in beta_recent["data"]["events"]] == [
            "beta-only"
        ]

    async with auth_db["runtime"].acquire() as conn:
        assert await conn.fetchval(
            "SELECT current_setting('app.current_tenant_id',true)"
        ) in (None, "")
        assert await conn.fetchval("SELECT count(*) FROM tenants") == 0
        assert await conn.fetchval("SELECT count(*) FROM pipeline_runs") == 0
        assert await conn.fetchval("SELECT count(*) FROM audit_log") == 0



@pytest.mark.asyncio
async def test_chat176_ai_finance_parity_nonowner_force_rls(auth_db, monkeypatch):
    """Actual PG15/16 nonowner: AI P&L equals report for each tenant.

    Approved-only but unposted draft and another tenant's posted entries
    must not enter either report or AI context. No external AI/provider calls.
    """
    import json
    from app.api.services import chat_context_service, financial_statements_service

    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "0")
    async with auth_db["admin"].acquire() as conn:
        await conn.execute("""
            CREATE TABLE journal_drafts (
                id BIGSERIAL PRIMARY KEY, tenant_id TEXT NOT NULL,
                description TEXT, amount NUMERIC, partner TEXT, account_code TEXT,
                status TEXT NOT NULL, confidence NUMERIC,
                journal_entries JSONB NOT NULL, created_at TIMESTAMPTZ DEFAULT now(),
                date TEXT
            )
        """)
        entries = [
            ("t_alpha", "posted", [
                {"cr": "6110", "amount": 1000},
                {"dr": "7210", "amount": 300},
            ]),
            ("t_alpha", "approved", [
                {"cr": "6110", "amount": 99999},
            ]),
            ("t_beta", "posted", [
                {"cr": "6110", "amount": 9000},
                {"dr": "7210", "amount": 100},
            ]),
        ]
        for tenant, status, payload in entries:
            await conn.execute("""
                INSERT INTO journal_drafts(
                    tenant_id, description, amount, partner, account_code,
                    status, confidence, journal_entries, date
                ) VALUES ($1,'Synthetic Chat176',1,'No real partner','6110',
                          $2,0.8,$3::jsonb,'2026-10-01')
            """, tenant, status, json.dumps(payload))

        await conn.execute("ALTER TABLE journal_drafts ENABLE ROW LEVEL SECURITY")
        await conn.execute("ALTER TABLE journal_drafts FORCE ROW LEVEL SECURITY")
        await conn.execute("""
            CREATE POLICY chat176_tenant_ledger ON journal_drafts FOR ALL
            USING (tenant_id = current_setting('app.current_tenant_id', true))
            WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))
        """)
        await conn.execute(
            f'GRANT SELECT ON journal_drafts TO "{auth_db["role"]}"'
        )

    async def check(tenant, expected_revenue, expected_expense):
        with db.authenticated_tenant_context(tenant):
            canonical = await financial_statements_service.build_profit_and_loss(tenant)
            ctx = await chat_context_service.build_chat_context(
                tenant, "ფინანსური ანგარიში P&L"
            )
        assert canonical["ok"] is True, canonical.get("error")
        assert ctx["reports_unavailable"] is False
        amounts = ctx["reports_summary"]
        assert amounts["source"] == "posted_drafts"
        assert amounts["revenue"] == canonical["data"]["revenue"]["total"]
        assert amounts["expenses"] == (
            canonical["data"]["cogs"]["total"] + canonical["data"]["opex"]["total"]
        )
        assert amounts["profit"] == canonical["data"]["ebit"]
        assert amounts["revenue"] == expected_revenue
        assert amounts["expenses"] == expected_expense

    await check("t_alpha", 1000.0, 300.0)
    await check("t_beta", 9000.0, 100.0)
    # Unprivileged pooled role has no tenant scope outside transaction.
    async with auth_db["runtime"].acquire() as conn:
        assert await conn.fetchval(
            "SELECT current_setting('app.current_tenant_id', true)"
        ) in (None, "")
        assert await conn.fetchval("SELECT count(*) FROM journal_drafts") == 0



@pytest.mark.asyncio
async def test_chat178_migration011_posted_ledger_tenant_line_integrity(
    auth_db, monkeypatch
):
    """Real disposable PG15/16 with unprivileged role and migration 011.

    A header/line tenant mismatch is intentionally injected by the
    synthetic schema OWNER to prove report SQL will not ingest another
    tenant's line even if line RLS policy is mistakenly permissive.
    Never run this fixture against a real tenant database.
    """
    from pathlib import Path
    from datetime import date
    from app.api.services import financial_statements_service as finance
    from app.api.services import chat_context_service as chat

    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1")
    migration = Path(
        "app/storage/migrations/011_posted_journal_entries_schema.sql"
    ).read_text(encoding="utf-8")
    async with auth_db["admin"].acquire() as conn:
        await conn.execute(migration)
        await conn.execute(migration)  # additive/idempotent on disposable DB

        async def add_entry(tenant, status, debit_code, debit_type,
                            credit_code, credit_type, amount):
            row_id = uuid4()
            await conn.execute("""
                INSERT INTO journal_entry_headers(
                    id,tenant_id,entry_date,period,status,source_type,
                    total_debit,total_credit
                ) VALUES ($1,$2,$3,'2026-10',$4,'synthetic-test',$5,$5)
            """, row_id, tenant, date(2026, 10, 15), status, amount)
            for i, code, acct_type, debit, credit in (
                (1, debit_code, debit_type, amount, 0),
                (2, credit_code, credit_type, 0, amount),
            ):
                await conn.execute("""
                    INSERT INTO journal_entry_lines(
                        id,tenant_id,journal_entry_id,line_no,
                        account_code,account_type,debit,credit,description
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'synthetic-only')
                """, uuid4(), tenant, row_id, i, code, acct_type, debit, credit)
            return row_id

        alpha_revenue = await add_entry(
            "t_alpha", "posted", "1120", "asset", "6110", "income", 1000,
        )
        await add_entry(
            "t_alpha", "posted", "7210", "expense", "1120", "asset", 400,
        )
        await add_entry(
            "t_alpha", "reversed", "1120", "asset", "6110", "income", 5000,
        )
        await add_entry(
            "t_beta", "posted", "1120", "asset", "6110", "income", 9000,
        )
        await add_entry(
            "t_beta", "posted", "7210", "expense", "1120", "asset", 200,
        )
        # Malicious/inconsistent line: links alpha header, claims beta tenant.
        # Migration 011 documents this invariant as application-enforced;
        # this fixture probes what happens if such a row ever exists.
        await conn.execute("""
            INSERT INTO journal_entry_lines(
                id,tenant_id,journal_entry_id,line_no,
                account_code,account_type,debit,credit,description
            ) VALUES ($1,'t_beta',$2,3,'6110','income',0,99999,'injected-leak')
        """, uuid4(), alpha_revenue)

        for table in ("journal_entry_headers", "journal_entry_lines"):
            await conn.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            await conn.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            await conn.execute(
                f'GRANT SELECT ON {table} TO "{auth_db["role"]}"'
            )
        await conn.execute("""
            CREATE POLICY chat178_header_scope ON journal_entry_headers
            FOR SELECT USING (
                tenant_id = current_setting('app.current_tenant_id', true)
            )
        """)
        # Deliberately broad line policy: SQL join must still fail closed.
        await conn.execute("""
            CREATE POLICY chat178_line_broad ON journal_entry_lines
            FOR SELECT USING (true)
        """)

    async def assert_ledger(tenant, revenue, expenses):
        with db.authenticated_tenant_context(tenant):
            official = await finance.build_profit_and_loss(tenant)
            ai = await chat.build_chat_context(tenant, "P&L")
            trial = await finance._get_posted_trial_balance_as_of(tenant, None)
        assert official["ok"] is True, official.get("error")
        assert official["data"]["source"] == "posted_ledger"
        assert official["data"]["revenue"]["total"] == revenue
        assert official["data"]["opex"]["total"] == expenses
        assert official["data"]["ebit"] == revenue - expenses
        assert ai["reports_unavailable"] is False
        assert ai["reports_summary"]["source"] == "posted_ledger"
        assert ai["reports_summary"]["revenue"] == revenue
        assert ai["reports_summary"]["expenses"] == expenses
        assert ai["reports_summary"]["profit"] == revenue - expenses
        assert trial["6110"] == -revenue

    await assert_ledger("t_alpha", 1000.0, 400.0)
    await assert_ledger("t_beta", 9000.0, 200.0)

    # Now restore strict line policy for a second real-DB verification.
    async with auth_db["admin"].acquire() as conn:
        await conn.execute("DROP POLICY chat178_line_broad ON journal_entry_lines")
        await conn.execute("""
            CREATE POLICY chat178_line_strict ON journal_entry_lines
            FOR SELECT USING (
                tenant_id = current_setting('app.current_tenant_id', true)
            )
        """)
    await assert_ledger("t_alpha", 1000.0, 400.0)
    await assert_ledger("t_beta", 9000.0, 200.0)

    # No tenant identity must bleed into a pooled, unprivileged connection.
    async with auth_db["runtime"].acquire() as conn:
        assert await conn.fetchval(
            "SELECT current_setting('app.current_tenant_id', true)"
        ) in (None, "")
        assert await conn.fetchval("SELECT count(*) FROM journal_entry_headers") == 0
        assert await conn.fetchval("SELECT count(*) FROM journal_entry_lines") == 0


async def _chat179_prepare_ledger(auth_db):
    """Migration 011 + intentionally strict synthetic policies, not live RLS."""
    from pathlib import Path

    async with auth_db["admin"].acquire() as conn:
        await conn.execute(Path(
            "app/storage/migrations/011_posted_journal_entries_schema.sql"
        ).read_text(encoding="utf-8"))
        for table in ("journal_entry_headers", "journal_entry_lines", "journal_entry_sources"):
            await conn.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            await conn.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            await conn.execute(f'GRANT SELECT,INSERT,UPDATE ON {table} TO "{auth_db["role"]}"')
            await conn.execute(f"""
                CREATE POLICY chat179_exact_tenant ON {table} FOR ALL
                USING (tenant_id = current_setting('app.current_tenant_id', true))
                WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))
            """)


@pytest.mark.asyncio
async def test_chat179_actual_writer_to_reports_and_ai_parity(auth_db, monkeypatch):
    """Actual writer SQL -> forced-RLS PG -> reports and both AI readers."""
    from pathlib import Path
    from app.api.services import financial_statements_service as finance
    from app.api.services import chat_context_service as chat
    from app.api.services.ai_tool_registry import run_tool
    from app.api.services.posting_service import _write_ledger_entries

    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1")
    await _chat179_prepare_ledger(auth_db)
    candidate = Path("docs/sql/chat179_posted_ledger_tenant_constraints_DRAFT.sql").read_text()
    async with auth_db["admin"].acquire() as conn:
        await conn.execute(candidate)
        await conn.execute(candidate)
        await conn.execute("""
            CREATE TABLE journal_drafts (
                id SERIAL PRIMARY KEY, tenant_id TEXT, status TEXT,
                confidence NUMERIC, amount NUMERIC
            );
            CREATE TABLE bank_accounts (
                tenant_id TEXT, name TEXT, balance NUMERIC, currency TEXT
            );
            INSERT INTO journal_drafts(tenant_id,status,confidence,amount)
                VALUES ('t_alpha','approved',1,999999), ('t_beta','approved',1,888888);
        """)
        for table in ("journal_drafts", "bank_accounts"):
            await conn.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            await conn.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            await conn.execute(f'GRANT SELECT ON {table} TO "{auth_db["role"]}"')
            await conn.execute(f"""CREATE POLICY chat179_exact_tenant ON {table}
                USING (tenant_id = current_setting('app.current_tenant_id', true))""")

    for tenant, revenue, expense in (("t_alpha", 1000, 400), ("t_beta", 9000, 200)):
        with db.authenticated_tenant_context(tenant):
            for debit, credit, amount in (("1120", "6110", revenue), ("7210", "1120", expense)):
                draft = {"id": str(uuid4()), "date": "2026-10-15", "currency": "GEL",
                         "lines": [{"account_code": debit, "debit": amount, "credit": 0},
                                   {"account_code": credit, "debit": 0, "credit": amount}]}
                async with db.get_conn() as conn:
                    await _write_ledger_entries(conn, draft, {}, tenant, "synthetic", "test-hash")
                    # Existing-source retry remains a no-op on the same real connection.
                    await _write_ledger_entries(conn, draft, {}, tenant, "synthetic", "test-hash")
            pnl = await finance.build_profit_and_loss(tenant)
            balance = await finance.build_balance_sheet(tenant)
            cashflow = await finance.build_cashflow_statement(tenant)
            trial = await finance._get_posted_trial_balance_as_of(tenant, None)
            context = await chat.build_chat_context(tenant, "P&L")
            tool = await run_tool("financial_summary", {}, tenant)
            assert pnl["ok"] is True, pnl
            assert pnl["data"]["revenue"]["total"] == revenue
            assert pnl["data"]["opex"]["total"] == expense
            assert pnl["data"]["ebit"] == revenue - expense
            assert balance["ok"] is True and balance["data"]["assets"]["total"] == revenue - expense
            assert cashflow["ok"] is True and cashflow["data"]["net_change_in_cash"] == revenue - expense
            assert trial["6110"] == -revenue and trial["7210"] == expense
            assert trial["1120"] == revenue - expense
            assert context["reports_summary"]["profit"] == revenue - expense
            assert tool["preview"]["accounting_basis"] == "posted_ledger", tool
            assert tool["preview"]["revenue"] == f"{revenue:,.2f} GEL"
            assert tool["preview"]["expenses"] == f"{expense:,.2f} GEL"
            assert tool["preview"]["profit"] == f"{revenue - expense:,.2f} GEL"
            async with db.get_conn() as conn:
                assert await conn.fetchval("SELECT count(*) FROM journal_entry_headers") == 2
                assert await conn.fetchval("SELECT count(*) FROM journal_entry_lines") == 4
                assert await conn.fetchval("SELECT count(*) FROM journal_entry_sources") == 2
                assert await conn.fetchval("SELECT count(*) FROM journal_entry_lines WHERE account_type IS NULL") == 0
    async with auth_db["runtime"].acquire() as conn:
        assert await conn.fetchval("SELECT current_setting('app.current_tenant_id',true)") in (None, "")
        assert await conn.fetchval("SELECT count(*) FROM journal_entry_headers") == 0
        assert await conn.fetchval("SELECT count(*) FROM journal_entry_lines") == 0
        assert await conn.fetchval("SELECT count(*) FROM journal_entry_sources") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("table", ["journal_entry_lines", "journal_entry_sources"])
async def test_chat179_candidate_fk_rejects_cross_tenant_writes_and_updates(auth_db, table):
    from pathlib import Path

    await _chat179_prepare_ledger(auth_db)
    alpha, beta = uuid4(), uuid4()
    if table == "journal_entry_lines":
        insert = """INSERT INTO journal_entry_lines
            (id,tenant_id,journal_entry_id,line_no,account_code,debit)
            VALUES ($1,'t_alpha',$2,1,'1120',10)"""
    else:
        insert = """INSERT INTO journal_entry_sources
            (id,tenant_id,journal_entry_id,source_type,source_id)
            VALUES ($1,'t_alpha',$2,'synthetic','synthetic-source')"""
    async with auth_db["admin"].acquire() as conn:
        for entry, tenant in ((alpha, "t_alpha"), (beta, "t_beta")):
            await conn.execute("""INSERT INTO journal_entry_headers
                (id,tenant_id,entry_date,period,status,source_type)
                VALUES ($1,$2,'2026-10-15','2026-10','posted','synthetic')""", entry, tenant)
        # Show migration 011 alone permits a mismatched parent; rollback only this probe.
        probe = conn.transaction()
        await probe.start()
        await conn.execute(insert, uuid4(), beta)
        await probe.rollback()
        candidate = Path("docs/sql/chat179_posted_ledger_tenant_constraints_DRAFT.sql").read_text()
        await conn.execute(candidate)
        await conn.execute(candidate)

    row = uuid4()
    with db.authenticated_tenant_context("t_alpha"):
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            async with db.get_conn() as conn:
                await conn.execute(insert, uuid4(), beta)
        async with db.get_conn() as conn:
            await conn.execute(insert, row, alpha)
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            async with db.get_conn() as conn:
                await conn.execute(f"UPDATE {table} SET journal_entry_id=$1 WHERE id=$2", beta, row)
    async with auth_db["admin"].acquire() as conn:
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await conn.execute("UPDATE journal_entry_headers SET tenant_id='t_other' WHERE id=$1", alpha)
        assert await conn.fetchval(f"SELECT journal_entry_id FROM {table} WHERE id=$1", row) == alpha


@pytest.mark.asyncio
async def test_chat179_candidate_refuses_bad_legacy_rows_without_repair(auth_db):
    from pathlib import Path

    await _chat179_prepare_ledger(auth_db)
    header, line = uuid4(), uuid4()
    async with auth_db["admin"].acquire() as conn:
        await conn.execute("""INSERT INTO journal_entry_headers
            (id,tenant_id,entry_date,period,status,source_type)
            VALUES ($1,'t_alpha','2026-10-15','2026-10','posted','synthetic')""", header)
        await conn.execute("""INSERT INTO journal_entry_lines
            (id,tenant_id,journal_entry_id,line_no,account_code,debit)
            VALUES ($1,'t_beta',$2,1,'1120',10)""", line, header)
        try:
            with pytest.raises(asyncpg.RaiseError, match="LEDGER_TENANT_INTEGRITY_PREFLIGHT_FAILED"):
                await conn.execute(Path(
                    "docs/sql/chat179_posted_ledger_tenant_constraints_DRAFT.sql"
                ).read_text())
        finally:
            await conn.execute("ROLLBACK")
        assert await conn.fetchval("SELECT tenant_id FROM journal_entry_lines WHERE id=$1", line) == "t_beta"
        assert await conn.fetchval("""SELECT count(*) FROM pg_constraint
            WHERE conrelid='journal_entry_headers'::regclass AND conname='uq_chat179_jeh_id_tenant'""") == 0
