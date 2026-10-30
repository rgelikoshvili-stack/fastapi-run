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
    from app.api.services import ledger_service as ledger

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
            routed_trial = await ledger.get_trial_balance(tenant, "2026-10-01", "2026-10-31")
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
        assert "error" not in routed_trial, routed_trial
        assert routed_trial["total_debit"] == revenue + expenses
        assert routed_trial["total_credit"] == revenue + expenses
        assert next(a for a in routed_trial["accounts"] if a["account_code"] == "6110")["closing_balance"] == -revenue

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


@pytest.mark.asyncio
async def test_chat180_actual_writer_stored_cents_precision_and_invalid_rollback(auth_db):
    from decimal import Decimal
    from app.api.services.posting_service import _write_ledger_entries

    await _chat179_prepare_ledger(auth_db)
    with db.authenticated_tenant_context("t_alpha"):
        async with db.get_conn() as conn:
            for lines in (
                [{"account_code": "", "debit": 10}, {"account_code": "6110", "credit": 10}],
                [{"account_code": "1120", "debit": ".005"},
                 {"account_code": "1130", "debit": ".005"},
                 {"account_code": "6110", "credit": ".01"}],
                [{"account_code": "1120", "debit": "invalid"},
                 {"account_code": "6110", "credit": 10}],
            ):
                invalid = {"id": str(uuid4()), "date": "2026-10-29", "currency": "GEL", "lines": lines}
                with pytest.raises(ValueError):
                    await _write_ledger_entries(conn, invalid, {}, "t_alpha", "test", "hash")
            assert await conn.fetchval("SELECT count(*) FROM journal_entry_headers") == 0
            assert await conn.fetchval("SELECT count(*) FROM journal_entry_lines") == 0
            assert await conn.fetchval("SELECT count(*) FROM journal_entry_sources") == 0

            for amount in (".005", "9007199254740993.01"):
                valid = {"id": str(uuid4()), "date": "2026-10-29", "currency": "GEL",
                         "lines": [{"account_code": "1120", "debit": amount},
                                   {"account_code": "6110", "credit": amount}]}
                await _write_ledger_entries(conn, valid, {}, "t_alpha", "test", "hash")
            rows = await conn.fetch("""SELECT h.total_debit,h.total_credit,
                       sum(l.debit) AS line_debit,sum(l.credit) AS line_credit,
                       max(l.amount_gel) AS gel
                FROM journal_entry_headers h JOIN journal_entry_lines l
                  ON l.journal_entry_id=h.id AND l.tenant_id=h.tenant_id
                GROUP BY h.id ORDER BY h.total_debit""")
            assert len(rows) == 2
            assert rows[0]["total_debit"] == Decimal(".01")
            assert rows[1]["total_debit"] == Decimal("9007199254740993.01")
            for row in rows:
                assert row["total_debit"] == row["total_credit"] == row["line_debit"] == row["line_credit"] == row["gel"]
    with db.authenticated_tenant_context("t_beta"):
        async with db.get_conn() as conn:
            assert await conn.fetchval("SELECT count(*) FROM journal_entry_headers") == 0


@pytest.mark.asyncio
async def test_chat180_concurrent_writers_share_one_tenant_source(auth_db, monkeypatch):
    import asyncio
    from app.api.services import posting_service as posting

    await _chat179_prepare_ledger(auth_db)
    monkeypatch.setattr(posting, "log_event", lambda *args, **kwargs: None)
    barrier = asyncio.Barrier(8)
    shared_id = "same-synthetic-draft-id-across-two-tenants"
    async def worker(tenant):
        with db.authenticated_tenant_context(tenant):
            async with db.get_conn() as conn:
                await barrier.wait()
                await posting._write_ledger_entries(conn, {
                    "id": shared_id, "date": "2026-10-29", "currency": "GEL",
                    "lines": [{"account_code": "1120", "debit": "100.01"},
                              {"account_code": "6110", "credit": "100.01"}],
                }, {}, tenant, "synthetic", "hash")
    await asyncio.wait_for(asyncio.gather(*[
        worker(tenant) for tenant in ("t_alpha", "t_beta") for _ in range(4)
    ]), timeout=20)
    for tenant in ("t_alpha", "t_beta"):
        with db.authenticated_tenant_context(tenant):
            async with db.get_conn() as conn:
                assert await conn.fetchval("SELECT count(*) FROM journal_entry_headers") == 1
                assert await conn.fetchval("SELECT count(*) FROM journal_entry_lines") == 2
                assert await conn.fetchval("SELECT count(*) FROM journal_entry_sources") == 1


@pytest.mark.asyncio
async def test_chat180_ledger_transaction_rollback_releases_lock_and_rows(auth_db):
    from app.api.services.posting_service import _write_ledger_entries

    await _chat179_prepare_ledger(auth_db)
    data = {"id": "retry-after-rollback", "date": "2026-10-29", "currency": "GEL",
            "lines": [{"account_code": "1120", "debit": 50},
                      {"account_code": "6110", "credit": 50}]}
    with db.authenticated_tenant_context("t_alpha"):
        with pytest.raises(RuntimeError, match="synthetic caller failure"):
            async with db.get_conn() as conn:
                await _write_ledger_entries(conn, data, {}, "t_alpha", "synthetic", "hash")
                raise RuntimeError("synthetic caller failure")
        async with db.get_conn() as conn:
            assert await conn.fetchval("SELECT count(*) FROM journal_entry_headers") == 0
            assert await conn.fetchval("SELECT count(*) FROM journal_entry_lines") == 0
            assert await conn.fetchval("SELECT count(*) FROM journal_entry_sources") == 0
            await _write_ledger_entries(conn, data, {}, "t_alpha", "synthetic", "hash")
            assert await conn.fetchval("SELECT count(*) FROM journal_entry_headers") == 1
    async with auth_db["runtime"].acquire() as conn:
        assert conn.is_in_transaction() is False
        with pytest.raises(ValueError, match="LEDGER_TRANSACTION_REQUIRED"):
            await _write_ledger_entries(conn, data, {}, "t_alpha", "synthetic", "hash")


@pytest.mark.asyncio
@pytest.mark.parametrize("isolation", ["repeatable_read", "serializable"])
async def test_chat180_ledger_stale_snapshot_isolation_fails_before_writes(auth_db, isolation):
    from app.api.services.posting_service import _write_ledger_entries

    await _chat179_prepare_ledger(auth_db)
    async with auth_db["runtime"].acquire() as conn:
        async with conn.transaction(isolation=isolation):
            await conn.execute("SELECT set_config('app.current_tenant_id','t_alpha',true)")
            data = {"id": "unsupported-isolation", "date": "2026-10-29", "currency": "GEL",
                    "lines": [{"account_code": "1120", "debit": 50},
                              {"account_code": "6110", "credit": 50}]}
            with pytest.raises(ValueError, match="LEDGER_ISOLATION_UNSUPPORTED"):
                await _write_ledger_entries(conn, data, {}, "t_alpha", "synthetic", "hash")
            assert await conn.fetchval("SELECT count(*) FROM journal_entry_headers") == 0
            assert await conn.fetchval("SELECT count(*) FROM journal_entry_sources") == 0


@pytest.mark.asyncio
async def test_chat180_erp_memory_routes_import_classifier_nonowner_force_rls(auth_db, monkeypatch):
    """Actual sync DB helper and services, synthetic tenant schema only."""
    import psycopg2
    from app.api import routes_erp_memory, routes_erp_import
    from app.api.services import erp_memory_service

    async with auth_db["admin"].acquire() as conn:
        await conn.execute("""
            CREATE TABLE erp_posting_memory (
                id BIGSERIAL PRIMARY KEY, tenant_id TEXT NOT NULL,
                source_system TEXT, external_entry_id TEXT, external_doc_id TEXT,
                doc_type TEXT, description TEXT, normalized_description TEXT,
                partner TEXT, normalized_partner TEXT, amount NUMERIC(18,2),
                currency TEXT, debit_account TEXT, credit_account TEXT,
                account_code TEXT, direction TEXT, posting_date DATE,
                evidence_count INTEGER NOT NULL DEFAULT 1,
                confidence NUMERIC NOT NULL DEFAULT 0.90,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            INSERT INTO erp_posting_memory(tenant_id, description, account_code)
                VALUES ('default', 'legacy retained unclaimed', '9999');
            ALTER TABLE erp_posting_memory ENABLE ROW LEVEL SECURITY;
            ALTER TABLE erp_posting_memory FORCE ROW LEVEL SECURITY;
            CREATE POLICY chat180_strict_erp_memory_tenant ON erp_posting_memory
                USING (tenant_id = nullif(current_setting('app.current_tenant_id',true),''))
                WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id',true),''));
        """)
        await conn.execute(f'GRANT SELECT,INSERT,UPDATE ON erp_posting_memory TO "{auth_db["role"]}"')
        await conn.execute(f'GRANT USAGE,SELECT ON erp_posting_memory_id_seq TO "{auth_db["role"]}"')

    class DisposableSyncPool:
        opened = 0
        returned = 0

        def getconn(self):
            self.opened += 1
            return psycopg2.connect(
                host="127.0.0.1", port=55442, dbname="bridge_hub_chat162_test",
                user=auth_db["role"], password=_ROLE_PASSWORD,
                options="-c search_path=" + auth_db["schema"],
            )

        def putconn(self, conn, close=False):
            self.returned += 1
            conn.close()

    pool = DisposableSyncPool()
    monkeypatch.setattr(db, "_get_sync_pool", lambda: pool)

    def scoped_request(tenant, role="accountant"):
        result = request("/erp-memory/import/json", "127.0.0.1")
        result.state.authenticated = True
        result.state.role = role
        result.state.tenant_id = tenant
        result.state.auth_tenant_id = tenant
        return result

    ids = {}
    for tenant, account in [("t_alpha", "1110"), ("t_beta", "2110")]:
        r = scoped_request(tenant)
        data = routes_erp_import.ErpImportRequest(items=[routes_erp_import.ErpHistoryItem(
            external_entry_id="same-external-id", description="shared invoice",
            partner="shared partner", account_code=account, amount=12,
        )])
        with db.authenticated_tenant_context(tenant):
            imported = routes_erp_import.import_erp_history_json(data, r)
            assert imported["ok"] and imported["data"]["inserted_or_updated"] == 1
            assert imported["data"]["authoritative"] is False
            updated = routes_erp_memory.upsert_memory(routes_erp_memory.ErpMemoryUpsertRequest(
                external_entry_id="same-external-id", description="shared invoice",
                partner="shared partner", account_code=account, amount=34,
            ), r)
            assert updated["ok"] and updated["data"]["memory"]["evidence_count"] == 2
            own = routes_erp_memory.list_memory(scoped_request(tenant, "viewer"), limit=100)
            assert own["ok"] and own["data"]["count"] == 1
            row = own["data"]["items"][0]
            assert row["tenant_id"] == tenant and row["account_code"] == account
            ids[tenant] = row["id"]
            match = erp_memory_service.find_erp_memory_match(
                description="shared invoice", partner="shared partner", tenant_id=tenant,
            )
            assert match["id"] == row["id"] and match["account_code"] == account
            assert match["tenant_id"] == tenant
            # A real SQL error is redacted and the failed connection is returned.
            bad = routes_erp_memory.upsert_memory(routes_erp_memory.ErpMemoryUpsertRequest(
                external_entry_id="invalid-date", account_code=account, posting_date="not-a-date",
            ), r)
            assert not bad["ok"] and bad["error"]["details"] is None
    assert ids["t_alpha"] != ids["t_beta"]
    assert pool.opened == pool.returned == 10
    before = pool.opened
    with db.authenticated_tenant_context("t_alpha"):
        with pytest.raises(ValueError):
            erp_memory_service.list_erp_posting_memory(tenant_id="t_beta")
        with pytest.raises(__import__("fastapi").HTTPException):
            routes_erp_memory.list_memory(scoped_request("t_beta"))
    assert pool.opened == before
    async with auth_db["admin"].acquire() as conn:
        rows = await conn.fetch("SELECT tenant_id, count(*) AS n FROM erp_posting_memory GROUP BY tenant_id")
        assert {row["tenant_id"]: row["n"] for row in rows} == {"default": 1, "t_alpha": 1, "t_beta": 1}
    async with auth_db["runtime"].acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM erp_posting_memory") == 0


async def _chat181_report_inputs(auth_db):
    """Small synthetic ancillary tables for actual AI readers, tenant RLS enabled."""
    async with auth_db["admin"].acquire() as conn:
        await conn.execute("""CREATE TABLE journal_drafts (
            id SERIAL PRIMARY KEY, tenant_id TEXT, status TEXT, confidence NUMERIC, amount NUMERIC);
            CREATE TABLE bank_accounts (tenant_id TEXT, name TEXT, balance NUMERIC, currency TEXT);
        """)
        for table in ("journal_drafts", "bank_accounts"):
            await conn.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            await conn.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            await conn.execute(f'GRANT SELECT ON {table} TO "{auth_db["role"]}"')
            await conn.execute(f"CREATE POLICY chat181_exact ON {table} USING (tenant_id=current_setting('app.current_tenant_id',true))")


@pytest.mark.asyncio
async def test_chat181_actual_mixed_currency_writer_reports_ai_and_cfo(auth_db, monkeypatch):
    from app.api.services import financial_statements_service as finance, ledger_service as ledger
    from app.api.services import chat_context_service as chat, cfo_dashboard_service as cfo
    from app.api.services.ai_tool_registry import run_tool
    from app.api.services.posting_service import _write_ledger_entries
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1")
    await _chat179_prepare_ledger(auth_db)
    await _chat181_report_inputs(auth_db)
    entries = [("t_alpha", "2026-09-30", "GEL", "1", "1120", "6110", "7"),
               ("t_alpha", "2026-10-10", "USD", "2.5", "1120", "6110", "100"),
               ("t_alpha", "2026-10-20", "EUR", "3", "1120", "6110", "20"),
               ("t_alpha", "2026-10-25", "GEL", "1", "7210", "1120", "10"),
               ("t_beta", "2026-10-10", "USD", "4", "1120", "6110", "9000")]
    for tenant, day, currency, rate, dr, cr, amount in entries:
        with db.authenticated_tenant_context(tenant):
            async with db.get_conn() as conn:
                await _write_ledger_entries(conn, {"id": str(uuid4()), "date": day, "currency": currency,
                    "lines": [{"account_code": dr, "debit": amount}, {"account_code": cr, "credit": amount}]},
                    {"exchange_rate": rate}, tenant, "synthetic", "fin05")
    with db.authenticated_tenant_context("t_alpha"):
        pnl = await finance.build_profit_and_loss("t_alpha", "2026-10-01", "2026-10-31")
        assert pnl["ok"] is True, pnl
        assert pnl["data"]["currency"] == "GEL"
        assert pnl["data"]["revenue"]["total"] == 310  # 100USD*2.5 + 20EUR*3
        assert pnl["data"]["opex"]["total"] == 10 and pnl["data"]["ebit"] == 300
        balance = await finance.build_balance_sheet("t_alpha", "2026-10-31")
        assert balance["ok"] and balance["data"]["assets"]["total"] == 307
        cashflow = await finance.build_cashflow_statement("t_alpha", "2026-10-01", "2026-10-31")
        assert cashflow["ok"] and cashflow["data"]["net_change_in_cash"] == 300
        trial = await ledger.get_trial_balance("t_alpha", "2026-10-01", "2026-10-31")
        assert "error" not in trial and trial["total_debit"] == trial["total_credit"] == 320
        ending = await finance._get_posted_trial_balance_as_of("t_alpha", "2026-10-31")
        assert ending["1120"] == 307 and ending["6110"] == -317 and ending["7210"] == 10
        dashboard = await cfo.build_cfo_dashboard("t_alpha", date_from="2026-10-01", date_to="2026-10-31")
        assert dashboard["cash_position"]["total_liquid"] == 307
        assert dashboard["cash_position"]["net_cashflow"] == 300
        context = await chat.build_chat_context("t_alpha", "P&L")
        assert context["reports_summary"]["revenue"] == 317
        assert context["reports_summary"]["profit"] == 307
        tool = await run_tool("financial_summary", {}, "t_alpha")
        assert tool["preview"]["revenue"] == "317.00 GEL" and tool["preview"]["profit"] == "307.00 GEL"
    with db.authenticated_tenant_context("t_beta"):
        pnl = await finance.build_profit_and_loss("t_beta")
        assert pnl["ok"] and pnl["data"]["revenue"]["total"] == 36000
    async with auth_db["runtime"].acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM journal_entry_lines") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["zero_gel", "zero_rate", "nan_rate", "currency_mismatch", "rounded_imbalance"])
async def test_chat181_legacy_invalid_fx_never_becomes_official_gel(auth_db, monkeypatch, bad):
    from app.api.services import financial_statements_service as finance, ledger_service as ledger
    from app.api.services import cfo_dashboard_service as cfo
    from app.api.services.posting_service import _write_ledger_entries
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1")
    await _chat179_prepare_ledger(auth_db)
    with db.authenticated_tenant_context("t_alpha"):
        async with db.get_conn() as conn:
            await _write_ledger_entries(conn, {"id": str(uuid4()), "date": "2026-10-29", "currency": "USD",
                "lines": [{"account_code": "1120", "debit": "100"}, {"account_code": "6110", "credit": "100"}]},
                {"exchange_rate": "2.5"}, "t_alpha", "synthetic", "fin05")
    async with auth_db["admin"].acquire() as conn:
        if bad == "zero_gel":
            await conn.execute("UPDATE journal_entry_lines SET amount_gel=0")
        elif bad == "zero_rate":
            await conn.execute("UPDATE journal_entry_lines SET exchange_rate=0")
        elif bad == "nan_rate":
            await conn.execute("UPDATE journal_entry_lines SET exchange_rate='NaN'::numeric")
        elif bad == "currency_mismatch":
            await conn.execute("UPDATE journal_entry_lines SET currency='EUR'")
        else:
            # Historic raw-balanced journal with valid per-line FX rounding, but
            # functional debit=.01 and functional credit=.02. Synthetic only.
            header = uuid4()
            await conn.execute("""INSERT INTO journal_entry_headers
                (id,tenant_id,entry_date,period,status,source_type,currency,exchange_rate,total_debit,total_credit)
                VALUES ($1,'t_alpha','2026-10-29','2026-10','posted','synthetic','USD',.5,.02,.02)""", header)
            for n, code, typ, debit, credit in [(1,"1120","asset",".02","0"),(2,"6110","income","0",".01"),(3,"6120","income","0",".01")]:
                from decimal import Decimal
                await conn.execute("""INSERT INTO journal_entry_lines
                    (id,tenant_id,journal_entry_id,line_no,account_code,account_type,debit,credit,currency,exchange_rate,amount_gel)
                    VALUES ($1,'t_alpha',$2,$3,$4,$5,$6,$7,'USD',.5,.01)""", uuid4(),header,n,code,typ,Decimal(debit),Decimal(credit))
    with db.authenticated_tenant_context("t_alpha"):
        for build in (finance.build_profit_and_loss, finance.build_balance_sheet, finance.build_cashflow_statement):
            response = await build("t_alpha")
            assert response["ok"] is False and response["error"]["code"] == "POSTED_LEDGER_FX_INVALID", response
        trial = await ledger.get_trial_balance("t_alpha")
        assert trial["error"] == "POSTED_LEDGER_FX_INVALID"
        with pytest.raises(ValueError, match="POSTED_LEDGER_FX_INVALID"):
            await finance._get_posted_trial_balance_as_of("t_alpha", None)
        dashboard = await cfo.build_cfo_dashboard("t_alpha")
        assert dashboard["cash_position"]["available"] is False
        assert dashboard["cash_position"]["net_cashflow"] is None
        assert dashboard["profitability"]["available"] is False
        assert dashboard["profitability"]["revenue"] is None


@pytest.mark.asyncio
async def test_chat181_actual_writer_rejects_functional_rounding_imbalance_without_rows(auth_db):
    from app.api.services.posting_service import _write_ledger_entries
    await _chat179_prepare_ledger(auth_db)
    with db.authenticated_tenant_context("t_alpha"):
        with pytest.raises(ValueError, match="LEDGER_FUNCTIONAL_UNBALANCED"):
            async with db.get_conn() as conn:
                await _write_ledger_entries(conn, {"id": str(uuid4()), "date": "2026-10-29", "currency": "USD",
                    "lines": [{"account_code": "1120", "debit": ".02"}, {"account_code": "6110", "credit": ".01"}, {"account_code": "6120", "credit": ".01"}]},
                    {"exchange_rate": ".5"}, "t_alpha", "synthetic", "fin05")
        async with db.get_conn() as conn:
            for table in ("journal_entry_headers", "journal_entry_lines", "journal_entry_sources"):
                assert await conn.fetchval(f"SELECT count(*) FROM {table}") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign_at", ["header", "line"])
async def test_chat181_legacy_currency_guard_preserves_raw_journal_and_own_gel(auth_db, monkeypatch, foreign_at):
    import json
    from app.api.services import financial_statements_service as finance, ledger_service as ledger
    monkeypatch.delenv("POSTED_LEDGER_REPORTS_ENABLED", raising=False)
    async with auth_db["admin"].acquire() as conn:
        await conn.execute("""CREATE TABLE journal_drafts (
            id SERIAL PRIMARY KEY, tenant_id TEXT, status TEXT, date TEXT,
            created_at TIMESTAMPTZ DEFAULT now(), description TEXT, partner TEXT,
            counterparty_inn TEXT, counterparty_name TEXT, amount NUMERIC,
            account_code TEXT, debit_account TEXT, credit_account TEXT, reason TEXT,
            currency TEXT, journal_entries JSONB);
            ALTER TABLE journal_drafts ENABLE ROW LEVEL SECURITY;
            ALTER TABLE journal_drafts FORCE ROW LEVEL SECURITY;
            CREATE POLICY chat181_legacy_tenant ON journal_drafts
                USING (tenant_id=current_setting('app.current_tenant_id',true));
        """)
        await conn.execute(f'GRANT SELECT ON journal_drafts TO "{auth_db["role"]}"')
        for tenant, currency, debit, amount in [("t_alpha", "USD" if foreign_at == "header" else "GEL", "7210",100), ("t_beta","GEL","1120",1000)]:
            entries=[{"dr":debit,"amount":amount},{"cr":"1120" if tenant=="t_alpha" else "6110","amount":amount}]
            if tenant=="t_alpha" and foreign_at=="line":
                for entry in entries:entry["currency"]="USD"
            await conn.execute("""INSERT INTO journal_drafts
                (tenant_id,status,date,description,counterparty_inn,amount,account_code,currency,journal_entries)
                VALUES($1,'posted','2026-10-15','synthetic','test-inn',$2,$3,$4,$5::jsonb)""",
                tenant,amount,debit,currency,json.dumps(entries))
    with db.authenticated_tenant_context("t_alpha"):
        for build in (finance.build_profit_and_loss,finance.build_balance_sheet):
            result=await build("t_alpha")
            assert not result["ok"] and result["error"]["code"]=="LEGACY_FX_UNAVAILABLE"
        results=[await ledger.get_trial_balance("t_alpha"), await ledger.get_account_ledger("t_alpha","1120"),
                 await ledger.get_account_ledger("t_alpha","1120","2026-11-01","2026-11-30"),
                 await ledger.get_counterparty_ledger("t_alpha","test-inn"),await ledger.get_payroll_ledger("t_alpha")]
        assert all(r["error"]=="LEGACY_FX_UNAVAILABLE" for r in results)
        raw=await ledger.get_journal_entries("t_alpha")
        assert raw["source"]=="posted_drafts" and raw["items"][0]["amount"]==100
        assert raw["items"][0]["currency"]==("USD" if foreign_at=="header" else "GEL")
    with db.authenticated_tenant_context("t_beta"):
        result=await finance.build_profit_and_loss("t_beta")
        assert result["ok"] and result["data"]["revenue"]["total"]==1000
        trial=await ledger.get_trial_balance("t_beta")
        assert "error" not in trial and trial["total_debit"]==trial["total_credit"]==1000
        assert len(trial["accounts"]) == 2  # no phantom null-account aggregates
        opening=await ledger.get_trial_balance("t_beta","2026-11-01","2026-11-30")
        assert "error" not in opening and opening["total_debit"]==opening["total_credit"]==0
        bank=next(row for row in opening["accounts"] if row["account_code"]=="1120")
        assert bank["opening_balance"]==bank["closing_balance"]==1000
        async with auth_db["admin"].acquire() as conn:
            await conn.execute("UPDATE journal_drafts SET journal_entries=jsonb_set(journal_entries,'{1,cr}',$1::jsonb) WHERE tenant_id='t_beta'",json.dumps("CUSTOM_UNKNOWN"))
        unmapped=await finance.build_profit_and_loss("t_beta")
        assert not unmapped["ok"] and unmapped["error"]["code"]=="LEDGER_CLASSIFICATION_INCOMPLETE"



@pytest.mark.asyncio
async def test_chat181_stored_posting_rate_no_estimate_native_date_and_exact_writer(auth_db, monkeypatch):
    from decimal import Decimal
    from app.api.services import currency_service as currency
    from app.api.services import posting_service as posting
    await _chat179_prepare_ledger(auth_db)
    async with auth_db["admin"].acquire() as conn:
        # Legacy latest snapshot is intentionally UNTRUSTED for financial posting.
        await conn.execute("""CREATE TABLE exchange_rates (
            currency TEXT PRIMARY KEY,from_code TEXT,to_code TEXT,rate NUMERIC,
            fetched_at TIMESTAMPTZ,updated_at TIMESTAMPTZ);
            INSERT INTO exchange_rates VALUES
            ('USD','USD','GEL',2.99999999,'2026-10-10T12:00:00Z','2026-10-10T12:00:00Z');
        """)
        from pathlib import Path
        quote_schema = Path("docs/sql/chat184_verified_fx_quotes_DRAFT.sql").read_text(encoding="utf-8")
        await conn.execute(quote_schema)
        await conn.execute(quote_schema)
        await conn.execute("""
            INSERT INTO fx_verified_quotes (
                currency, base_currency, source_provider, source_revision,
                source_payload_sha256, published_date, effective_date, retrieved_at,
                approved_by, approved_at, raw_rate, quantity, rate_to_gel
            ) VALUES (
                'USD', 'GEL', 'NBG', 'synthetic-pub-20261014',
                repeat('a',64), '2026-10-13', '2026-10-14',
                '2026-10-14T08:00:00Z', 'independent-reviewer',
                '2026-10-14T09:00:00Z', 2.12345678, 1, 2.12345678
            )
        """)
        await conn.execute(f'GRANT SELECT ON exchange_rates TO "{auth_db["role"]}"')
        await conn.execute(f'GRANT SELECT ON fx_verified_quotes TO "{auth_db["role"]}"')
    with db.authenticated_tenant_context("t_alpha"):
        rate=await currency.get_rate_async("USD","GEL","2026-10-15",allow_fallback=False)
        assert rate==Decimal("2.12345678")
        draft={"id":str(uuid4()),"date":"2026-10-15","currency":"USD","amount":"100",
               "lines":[{"account_code":"1120","debit":"100"},{"account_code":"6110","credit":"100"}]}
        payload=await posting._draft_to_posting_payload(draft)
        assert payload["exchange_rate_exact"]=="2.12345678" and payload["amount_gel"]==212.35
        # An old six-decimal connector representation cannot alter booked FX.
        payload["exchange_rate"]=2.123457
        async with db.get_conn() as conn:
            await posting._write_ledger_entries(conn,draft,payload,"t_alpha","synthetic","fx181")
            assert await conn.fetchval("SELECT exchange_rate FROM journal_entry_headers")==rate
            assert await conn.fetchval("SELECT max(amount_gel) FROM journal_entry_lines")==Decimal("212.35")
        with pytest.raises(currency.CurrencyRateNotFound):
            await currency.get_rate_async("USD","GEL","2026-10-09",allow_fallback=False)
        for pair in [("EUR","GEL"),("GEL","EUR"),("USD","EUR")]:
            with pytest.raises(currency.CurrencyRateNotFound):
                await currency.get_rate_async(*pair,"2026-10-15",allow_fallback=False)
        with pytest.raises(posting.FxRateMissingError):
            await posting._draft_to_posting_payload(dict(draft,currency="EUR"))
        # Existing estimates remain available to the explicitly separate helper.
        assert await currency.get_rate_async("EUR","GEL","2026-10-15")==Decimal(str(currency._DEFAULT_RATES["EUR"]))
    # A second effective-day revision is ambiguous; don't guess which quote.
    async with auth_db["admin"].acquire() as conn:
        await conn.execute("""
            INSERT INTO fx_verified_quotes (
                currency, base_currency, source_provider, source_revision,
                source_payload_sha256, published_date, effective_date, retrieved_at,
                approved_by, approved_at, raw_rate, quantity, rate_to_gel
            ) VALUES (
                'USD', 'GEL', 'NBG', 'another-synthetic-revision',
                repeat('b',64), '2026-10-13', '2026-10-14',
                '2026-10-14T08:00:00Z', 'independent-reviewer',
                '2026-10-14T09:00:00Z', 2.12345679, 1, 2.12345679
            )
        """)
        with pytest.raises(asyncpg.PostgresError, match="FX_VERIFIED_QUOTES_IMMUTABLE"):
            await conn.execute("DELETE FROM fx_verified_quotes")
    with db.authenticated_tenant_context("t_alpha"):
        with pytest.raises(posting.FxRateMissingError):
            await posting._draft_to_posting_payload(draft)


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata",["missing","aliases","typed_custom"])
async def test_chat181_historical_classification_resolves_without_rewriting_rows(auth_db,monkeypatch,metadata):
    from app.api.services import financial_statements_service as finance,chat_context_service as chat
    from app.api.services.posting_service import _write_ledger_entries
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED","1")
    await _chat179_prepare_ledger(auth_db);await _chat181_report_inputs(auth_db)
    for tenant,amount in [("t_alpha",100),("t_beta",9000)]:
        with db.authenticated_tenant_context(tenant):
            async with db.get_conn() as conn:
                await _write_ledger_entries(conn,{"id":str(uuid4()),"date":"2026-10-15","currency":"GEL",
                    "lines":[{"account_code":"1120","debit":amount},{"account_code":"6110","credit":amount}]},
                    {},tenant,"synthetic","coa181")
    async with auth_db["admin"].acquire() as conn:
        if metadata=="missing":await conn.execute("UPDATE journal_entry_lines SET account_type=NULL WHERE tenant_id='t_alpha'")
        elif metadata=="aliases":await conn.execute("UPDATE journal_entry_lines SET account_type='revenue' WHERE tenant_id='t_alpha' AND account_code='6110'")
        else:await conn.execute("UPDATE journal_entry_lines SET account_code='CUSTOM_REV' WHERE tenant_id='t_alpha' AND account_code='6110'")
        before=[tuple(r) for r in await conn.fetch("SELECT id,account_code,account_type FROM journal_entry_lines ORDER BY id")]
    for tenant,amount in [("t_alpha",100),("t_beta",9000)]:
        with db.authenticated_tenant_context(tenant):
            pnl=await finance.build_profit_and_loss(tenant)
            assert pnl["ok"] and pnl["data"]["revenue"]["total"]==amount,pnl
            balance=await finance.build_balance_sheet(tenant)
            assert balance["ok"] and balance["data"]["assets"]["total"]==amount
            cash=await finance.build_cashflow_statement(tenant)
            # Typed custom revenue lacks an IAS7 counterpart policy; keep that
            # independent cashflow gate rather than inventing a category.
            if metadata!="typed_custom" or tenant=="t_beta":assert cash["ok"] and cash["data"]["net_change_in_cash"]==amount
            context=await chat.build_chat_context(tenant,"P&L")
            assert context["reports_summary"]["revenue"]==amount
    async with auth_db["admin"].acquire() as conn:
        after=[tuple(r) for r in await conn.fetch("SELECT id,account_code,account_type FROM journal_entry_lines ORDER BY id")]
        assert after==before  # runtime interpretation, no historical backfill


@pytest.mark.asyncio
@pytest.mark.parametrize("bad",["unmapped_null","unknown_type","contradictory_type"])
async def test_chat181_incomplete_classification_refuses_reports_and_ai(auth_db,monkeypatch,bad):
    from app.api.services import financial_statements_service as finance,ledger_service as ledger
    from app.api.services import chat_context_service as chat,cfo_dashboard_service as cfo
    from app.api.services.ai_tool_registry import run_tool
    from app.api.services.posting_service import _write_ledger_entries
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED","1")
    await _chat179_prepare_ledger(auth_db);await _chat181_report_inputs(auth_db)
    with db.authenticated_tenant_context("t_alpha"):
        async with db.get_conn() as conn:
            await _write_ledger_entries(conn,{"id":str(uuid4()),"date":"2026-10-15","currency":"GEL",
                "lines":[{"account_code":"1120","debit":100},{"account_code":"6110","credit":100}]},
                {},"t_alpha","synthetic","coa181")
    async with auth_db["admin"].acquire() as conn:
        if bad=="unmapped_null":await conn.execute("UPDATE journal_entry_lines SET account_code='CUSTOM_UNKNOWN',account_type=NULL WHERE account_code='6110'")
        elif bad=="unknown_type":await conn.execute("UPDATE journal_entry_lines SET account_type='unclassified' WHERE account_code='6110'")
        else:await conn.execute("UPDATE journal_entry_lines SET account_code='3410',account_type='income' WHERE account_code='6110'")
    with db.authenticated_tenant_context("t_alpha"):
        for build in (finance.build_profit_and_loss,finance.build_balance_sheet,finance.build_cashflow_statement):
            result=await build("t_alpha")
            assert not result["ok"] and result["error"]["code"]=="LEDGER_CLASSIFICATION_INCOMPLETE",result
        trial=await ledger.get_trial_balance("t_alpha");assert trial["error"]=="LEDGER_CLASSIFICATION_INCOMPLETE"
        with pytest.raises(ValueError,match="LEDGER_CLASSIFICATION_INCOMPLETE"):
            await finance._get_posted_trial_balance_as_of("t_alpha",None)
        dashboard=await cfo.build_cfo_dashboard("t_alpha")
        assert dashboard["cash_position"]["available"] is False and dashboard["profitability"]["revenue"] is None
        context=await chat.build_chat_context("t_alpha","P&L");assert context["reports_unavailable"] is True
        tool=await run_tool("financial_summary",{},"t_alpha")
        assert tool["preview"]["accounting_basis"]=="unavailable" and "revenue" not in tool["preview"]


@pytest.mark.asyncio
async def test_chat185_direct_sql_uniqueness_immutability_and_deferred_totals(auth_db):
    """Synthetic PG15/16 only: application lock is not a DB unique constraint."""
    from pathlib import Path
    from app.api.services.posting_service import _write_ledger_entries
    await _chat179_prepare_ledger(auth_db)
    async with auth_db["admin"].acquire() as conn:
        old = Path("docs/sql/chat179_posted_ledger_tenant_constraints_DRAFT.sql").read_text()
        await conn.execute(old)
        candidate = Path("docs/sql/chat185_posted_ledger_integrity_DRAFT.sql").read_text()
        await conn.execute(candidate)
        await conn.execute(candidate)  # idempotent in disposable schema

    source = "chat185-shared-across-tenants"
    data = {"id": source, "date": "2026-10-30", "currency": "GEL",
            "lines": [{"account_code": "1120", "debit": "100.01"},
                      {"account_code": "6110", "credit": "100.01"}]}

    for tenant in ("t_alpha", "t_beta"):
        with db.authenticated_tenant_context(tenant):
            async with db.get_conn() as conn:
                await _write_ledger_entries(conn, data, {}, tenant, "synthetic", "chat185")
            async with db.get_conn() as conn:
                assert await conn.fetchval(
                    "SELECT count(*) FROM journal_entry_headers WHERE tenant_id=$1", tenant
                ) == 1
                hdr = await conn.fetchval(
                    "SELECT id FROM journal_entry_headers WHERE tenant_id=$1", tenant
                )
            # Direct SQL duplicates fail even though they do not use the
            # cooperative application lock.
            with pytest.raises(asyncpg.UniqueViolationError):
                async with db.get_conn() as conn:
                    await conn.execute("""
                        INSERT INTO journal_entry_sources
                            (tenant_id,journal_entry_id,source_type,source_id)
                        VALUES ($1,$2,'journal_draft',$3)
                    """, tenant, hdr, source)
            with pytest.raises(asyncpg.RaiseError, match="LEDGER_IMMUTABLE"):
                async with db.get_conn() as conn:
                    await conn.execute("""
                        UPDATE journal_entry_lines SET amount_gel=amount_gel+1
                        WHERE tenant_id=$1 AND journal_entry_id=$2
                    """, tenant, hdr)

    async with auth_db["admin"].acquire() as conn:
        with pytest.raises(asyncpg.RaiseError, match="LEDGER_IMMUTABLE"):
            await conn.execute("DELETE FROM journal_entry_headers")
        with pytest.raises(asyncpg.RaiseError, match="LEDGER_IMMUTABLE"):
            await conn.execute("UPDATE journal_entry_sources SET source_id='tampered'")

    invalid_header = uuid4()
    with db.authenticated_tenant_context("t_alpha"):
        with pytest.raises(asyncpg.RaiseError, match="LEDGER_HEADER_TOTAL_MISMATCH"):
            async with db.get_conn() as conn:
                await conn.execute("""
                    INSERT INTO journal_entry_headers
                        (id,tenant_id,entry_date,period,status,source_type,total_debit,total_credit)
                    VALUES ($1,'t_alpha','2026-10-30','2026-10','posted','test',100,100)
                """, invalid_header)
                await conn.execute("""
                    INSERT INTO journal_entry_lines
                        (tenant_id,journal_entry_id,line_no,account_code,debit,credit,amount_gel)
                    VALUES ('t_alpha',$1,1,'1120',100,0,100),
                           ('t_alpha',$1,2,'6110',0,90,90)
                """, invalid_header)
                await conn.execute("""
                    INSERT INTO journal_entry_sources
                        (tenant_id,journal_entry_id,source_type,source_id)
                    VALUES ('t_alpha',$1,'journal_draft','chat185-invalid-header')
                """, invalid_header)
        async with db.get_conn() as conn:
            assert await conn.fetchval(
                "SELECT count(*) FROM journal_entry_headers WHERE id=$1", invalid_header
            ) == 0
            assert await conn.fetchval(
                "SELECT count(*) FROM journal_entry_headers"
            ) == 1


@pytest.mark.asyncio
async def test_chat185_candidate_refuses_duplicate_historical_sources_without_repair(auth_db):
    """Never silently certify an RLS-filtered subset or delete past duplicates."""
    from pathlib import Path
    await _chat179_prepare_ledger(auth_db)
    old = Path("docs/sql/chat179_posted_ledger_tenant_constraints_DRAFT.sql").read_text()
    new = Path("docs/sql/chat185_posted_ledger_integrity_DRAFT.sql").read_text()
    async with auth_db["admin"].acquire() as conn:
        await conn.execute(old)
        h = uuid4()
        await conn.execute("""
            INSERT INTO journal_entry_headers
                (id,tenant_id,entry_date,period,status,source_type,total_debit,total_credit)
            VALUES ($1,'t_alpha','2026-10-30','2026-10','posted','test',10,10)
        """, h)
        await conn.execute("""
            INSERT INTO journal_entry_lines
                (tenant_id,journal_entry_id,line_no,account_code,debit,credit,amount_gel)
            VALUES ('t_alpha',$1,1,'1120',10,0,10),
                   ('t_alpha',$1,2,'6110',0,10,10)
        """, h)
        await conn.execute("""
            INSERT INTO journal_entry_sources
                (tenant_id,journal_entry_id,source_type,source_id)
            VALUES ('t_alpha',$1,'journal_draft','historical-duplicate'),
                   ('t_alpha',$1,'journal_draft','historical-duplicate')
        """, h)
        with pytest.raises(asyncpg.RaiseError, match="LEDGER_SOURCE_DUPLICATE_PREFLIGHT_FAILED"):
            await conn.execute(new)
        await conn.execute("ROLLBACK")
        assert await conn.fetchval(
            "SELECT count(*) FROM journal_entry_sources WHERE source_id='historical-duplicate'"
        ) == 2
        assert await conn.fetchval("""
            SELECT count(*) FROM pg_indexes
            WHERE tablename='journal_entry_sources'
              AND indexname='uq_chat185_posted_source_identity'
        """) == 0


@pytest.mark.asyncio
async def test_chat185_candidate_refuses_legacy_unbalanced_header_without_repair(auth_db):
    from pathlib import Path
    await _chat179_prepare_ledger(auth_db)
    async with auth_db["admin"].acquire() as conn:
        await conn.execute(Path(
            "docs/sql/chat179_posted_ledger_tenant_constraints_DRAFT.sql"
        ).read_text())
        h = uuid4()
        await conn.execute("""
            INSERT INTO journal_entry_headers
                (id,tenant_id,entry_date,period,status,source_type,total_debit,total_credit)
            VALUES ($1,'t_alpha','2026-10-30','2026-10','posted','test',10,10)
        """, h)
        await conn.execute("""
            INSERT INTO journal_entry_lines
                (tenant_id,journal_entry_id,line_no,account_code,debit,credit,amount_gel)
            VALUES ('t_alpha',$1,1,'1120',10,0,10),
                   ('t_alpha',$1,2,'6110',0,5,5)
        """, h)
        await conn.execute("""
            INSERT INTO journal_entry_sources
                (tenant_id,journal_entry_id,source_type,source_id)
            VALUES ('t_alpha',$1,'journal_draft','bad-historical')
        """, h)
        with pytest.raises(asyncpg.RaiseError, match="LEDGER_INTEGRITY_PREFLIGHT_FAILED"):
            await conn.execute(Path(
                "docs/sql/chat185_posted_ledger_integrity_DRAFT.sql"
            ).read_text())
        await conn.execute("ROLLBACK")
        assert await conn.fetchval(
            "SELECT count(*) FROM journal_entry_lines WHERE journal_entry_id=$1", h
        ) == 2


@pytest.mark.asyncio
async def test_chat186_posting_outbox_durable_intent_tenant_dedup_and_unknown_hold(auth_db):
    """Disposable PG15/16 nonowner FORCE-RLS, NO connector invocation."""
    from pathlib import Path
    import uuid
    from app.api.services.posting_outbox_intent_service import (
        prepare_posting_intent, delivery_decision, PostingOutboxUnavailable,
    )

    sql = Path("docs/sql/chat186_posting_outbox_DRAFT.sql").read_text(encoding="utf-8")
    async with auth_db["admin"].acquire() as conn:
        await conn.execute(sql)
        await conn.execute(sql)
        await conn.execute(f'GRANT SELECT,INSERT ON posting_outbox_intents TO "{auth_db["role"]}"')
        await conn.execute(f'GRANT SELECT ON posting_outbox_receipts TO "{auth_db["role"]}"')

    ids={}
    for tenant in ("t_alpha","t_beta"):
        with db.authenticated_tenant_context(tenant):
            async with db.get_conn() as conn:
                first=await prepare_posting_intent(conn,tenant_id=tenant,source_id="draft17",
                    target_system="balance",payload={"tenant_id":tenant,"amount":"100.01","currency":"GEL"})
                second=await prepare_posting_intent(conn,tenant_id=tenant,source_id="draft17",
                    target_system="balance",payload={"currency":"GEL","amount":"100.01","tenant_id":tenant})
                assert first==second and first["dispatch_allowed"] is False
                assert delivery_decision(first["state"]) == "VENDOR_IDEMPOTENCY_APPROVAL_REQUIRED"
                ids[tenant]=first["intent_id"]
                assert await conn.fetchval(
                    "SELECT count(*) FROM posting_outbox_intents"
                ) == 1
            with pytest.raises(PostingOutboxUnavailable,match="OUTBOX_INTENT_CONFLICT"):
                async with db.get_conn() as conn:
                    await prepare_posting_intent(conn,tenant_id=tenant,source_id="draft17",
                        target_system="balance",payload={"tenant_id":tenant,"amount":"999.99"})
    assert ids["t_alpha"]!=ids["t_beta"]

    with db.authenticated_tenant_context("t_alpha"):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with db.get_conn() as conn:
                await conn.execute("""
                    INSERT INTO posting_outbox_intents
                        (tenant_id,source_id,target_system,idempotency_key,payload_sha256,payload_json)
                    VALUES ('t_beta','forged','balance',$1,$2,'{}'::jsonb)
                """, 'a'*64, 'b'*64)

    async with auth_db["admin"].acquire() as conn:
        await conn.execute(
            "UPDATE posting_outbox_intents SET state='unknown' WHERE id=$1",
            uuid.UUID(ids["t_alpha"])
        )
        with pytest.raises(asyncpg.RaiseError,match="FIN12_RECEIPT_OR_INTENT_IMMUTABLE"):
            await conn.execute(
                "UPDATE posting_outbox_intents SET state='in_flight' WHERE id=$1",
                uuid.UUID(ids["t_alpha"])
            )
        with pytest.raises(asyncpg.RaiseError,match="FIN12_RECEIPT_OR_INTENT_IMMUTABLE"):
            await conn.execute("DELETE FROM posting_outbox_intents")

    with db.authenticated_tenant_context("t_alpha"):
        async with db.get_conn() as conn:
            again=await prepare_posting_intent(conn,tenant_id="t_alpha",source_id="draft17",
                target_system="balance",payload={"tenant_id":"t_alpha","amount":"100.01","currency":"GEL"})
            assert again["state"]=="unknown"
            assert delivery_decision(again["state"])=="RECONCILIATION_REQUIRED"
            assert again["dispatch_allowed"] is False
            assert await conn.fetchval("SELECT count(*) FROM posting_outbox_intents")==1

    async with auth_db["admin"].acquire() as conn:
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await conn.execute("""
                INSERT INTO posting_outbox_receipts (
                    outbox_id,tenant_id,outcome
                ) VALUES ($1,'t_beta','unknown')
            """,uuid.UUID(ids["t_alpha"]))


@pytest.mark.asyncio
@pytest.mark.parametrize("close_month,post_month", [(10, 10), (0, 10)])
async def test_chat187_month_or_year_close_serializes_with_active_posting(
    auth_db, close_month, post_month
):
    """Use the real disposable DB, never mock advisory lock serialization."""
    import asyncio
    from datetime import date
    from app.api.services.period_transaction_gate import (
        acquire_posting_gate, acquire_close_gate,
    )
    async with auth_db["admin"].acquire() as conn:
        await conn.execute("""
            CREATE TABLE period_locks (
              tenant_id TEXT NOT NULL,
              period_year INT NOT NULL,
              period_month INT NOT NULL,
              unlocked_at TIMESTAMPTZ,
              PRIMARY KEY(tenant_id,period_year,period_month)
            );
            ALTER TABLE period_locks ENABLE ROW LEVEL SECURITY;
            ALTER TABLE period_locks FORCE ROW LEVEL SECURITY;
            CREATE POLICY chat187_period_tenant ON period_locks
              FOR ALL
              USING(tenant_id = current_setting('app.current_tenant_id',true))
              WITH CHECK(tenant_id = current_setting('app.current_tenant_id',true));
        """)
        await conn.execute(f'GRANT SELECT,INSERT,UPDATE ON period_locks TO "{auth_db["role"]}"')

    posting_entered = asyncio.Event()
    allow_post_commit = asyncio.Event()
    close_attempted = asyncio.Event()
    close_finished = asyncio.Event()
    async def active_post():
        with db.authenticated_tenant_context("t_alpha"):
            async with db.get_conn() as conn:
                await acquire_posting_gate(conn, "t_alpha", date(2026, post_month, 30))
                assert await conn.fetchval("""
                    SELECT 1 FROM period_locks
                    WHERE tenant_id='t_alpha' AND unlocked_at IS NULL
                      AND period_year=2026
                      AND (period_month=0 OR period_month=$1)
                """, post_month) is None
                posting_entered.set()
                await asyncio.wait_for(allow_post_commit.wait(), timeout=10)

    async def close():
        with db.authenticated_tenant_context("t_alpha"):
            async with db.get_conn() as conn:
                close_attempted.set()
                await acquire_close_gate(conn, "t_alpha", 2026, close_month)
                await conn.execute("""
                    INSERT INTO period_locks(tenant_id,period_year,period_month)
                    VALUES ('t_alpha',2026,$1)
                """, close_month)
        close_finished.set()

    posting_task = asyncio.create_task(active_post())
    await asyncio.wait_for(posting_entered.wait(), timeout=10)
    close_task = asyncio.create_task(close())
    await asyncio.wait_for(close_attempted.wait(), timeout=10)
    try:
        # An unrelated tenant must not inherit alpha's lock or its closed rows.
        with db.authenticated_tenant_context("t_beta"):
            async with db.get_conn() as conn:
                await asyncio.wait_for(
                    acquire_posting_gate(conn, "t_beta", date(2026, post_month, 30)),
                    timeout=2,
                )
                assert await conn.fetchval(
                    "SELECT count(*) FROM period_locks"
                ) == 0
        await asyncio.sleep(.075)
        assert not close_finished.is_set(), "close committed ahead of active posting"
    finally:
        allow_post_commit.set()
    await asyncio.wait_for(asyncio.gather(posting_task,close_task), timeout=15)
    assert close_finished.is_set()
    with db.authenticated_tenant_context("t_alpha"):
        async with db.get_conn() as conn:
            await acquire_posting_gate(conn, "t_alpha", date(2026, post_month, 30))
            assert await conn.fetchval("""
                SELECT 1 FROM period_locks
                WHERE tenant_id='t_alpha' AND unlocked_at IS NULL
                  AND period_year=2026
                  AND (period_month=0 OR period_month=$1)
            """, post_month) == 1


@pytest.mark.asyncio
async def test_chat187_missing_period_table_is_not_open_period(auth_db):
    from app.api.services.period_transaction_gate import acquire_posting_gate
    with db.authenticated_tenant_context("t_alpha"):
        with pytest.raises(asyncpg.UndefinedTableError):
            async with db.get_conn() as conn:
                await acquire_posting_gate(conn, "t_alpha", "2026-10-30")
                await conn.fetchval("""
                    SELECT 1 FROM period_locks WHERE tenant_id='t_alpha'
                """)


# Chat189 FIN-11. Entire suite scoped to synthetic disposable Chat162 PG15/16.
async def _chat189_prepare_reversal_drafts(auth_db):
    from pathlib import Path
    async with auth_db["admin"].acquire() as conn:
        await conn.execute("""
            CREATE TABLE journal_drafts (
                id BIGSERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                date DATE NOT NULL,
                description TEXT,
                partner TEXT,
                amount NUMERIC,
                currency TEXT,
                status TEXT NOT NULL,
                lines_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                reversal_of_draft_id BIGINT,
                reversal_reason TEXT,
                entry_type TEXT NOT NULL DEFAULT 'standard'
            );
            CREATE TABLE audit_log (
                id BIGSERIAL PRIMARY KEY,
                actor TEXT NOT NULL, role TEXT, action TEXT NOT NULL,
                resource TEXT, resource_id TEXT,
                old_value JSONB, new_value JSONB, status TEXT,
                details TEXT, tenant_id TEXT NOT NULL
            );
            CREATE TABLE period_locks (
                tenant_id TEXT NOT NULL,
                period_year INT NOT NULL,
                period_month INT NOT NULL,
                unlocked_at TIMESTAMPTZ
            );
            INSERT INTO journal_drafts
                (id, tenant_id, date, description, partner,
                 amount, currency, status, lines_json, entry_type)
            VALUES
                (41,'t_alpha','2026-10-15','synthetic-alpha','',
                 10,'GEL','posted',
                 '[{"account_code":"1120","debit":10,"credit":0},
                   {"account_code":"6110","debit":0,"credit":10}]'::jsonb,'standard'),
                (42,'t_beta','2026-10-15','synthetic-beta','',
                 10,'GEL','posted',
                 '[{"account_code":"1120","debit":10,"credit":0},
                   {"account_code":"6110","debit":0,"credit":10}]'::jsonb,'standard')
        """)
        await conn.execute("""
            ALTER TABLE journal_drafts ENABLE ROW LEVEL SECURITY;
            ALTER TABLE journal_drafts FORCE ROW LEVEL SECURITY;
            CREATE POLICY chat189_tenant_drafts ON journal_drafts FOR ALL
              USING (tenant_id=current_setting('app.current_tenant_id',true))
              WITH CHECK (tenant_id=current_setting('app.current_tenant_id',true));
            ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
            ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;
            CREATE POLICY chat190_tenant_audit ON audit_log FOR ALL
              USING (tenant_id=current_setting('app.current_tenant_id',true))
              WITH CHECK (tenant_id=current_setting('app.current_tenant_id',true));
            ALTER TABLE period_locks ENABLE ROW LEVEL SECURITY;
            ALTER TABLE period_locks FORCE ROW LEVEL SECURITY;
            CREATE POLICY chat189_tenant_period ON period_locks FOR ALL
              USING (tenant_id=current_setting('app.current_tenant_id',true))
              WITH CHECK (tenant_id=current_setting('app.current_tenant_id',true));
        """)
        for table in ("journal_drafts","period_locks","audit_log"):
            await conn.execute(
                f'GRANT SELECT,INSERT,UPDATE ON {table} TO "{auth_db["role"]}"'
            )
        await conn.execute(
            f'GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA "{auth_db["schema"]}"'
            f' TO "{auth_db["role"]}"'
        )


@pytest.mark.asyncio
async def test_chat189_adjustment_does_not_block_reversal_and_duplicate_is_db_unique(
    auth_db, monkeypatch
):
    """Actual reversal service with nonowner FORCE-RLS, index and period locks."""
    from pathlib import Path
    import asyncpg as _asyncpg
    from app.api.services import reversal_service as reversal
    await _chat189_prepare_reversal_drafts(auth_db)
    candidate=Path("docs/sql/chat189_reversal_source_unique_DRAFT.sql").read_text()
    async with auth_db["admin"].acquire() as conn:
        await conn.execute(candidate)
        await conn.execute(candidate)
        await conn.execute("""
            INSERT INTO journal_drafts
              (tenant_id,date,status,entry_type,reversal_of_draft_id)
            VALUES ('t_alpha','2026-10-20','approved','adjustment',41)
        """)
    monkeypatch.setattr(reversal,"log_event",lambda *a,**kw: None)
    with db.authenticated_tenant_context("t_alpha"):
        made=await reversal.create_reversal_draft(
            "t_alpha",41,"2026-10-30","correct synthetic alpha","maker-a"
        )
        assert made["status"]=="pending_approval"
        with pytest.raises(ValueError,match="already exists"):
            await reversal.create_reversal_draft(
                "t_alpha",41,"2026-10-30","duplicate","maker-a"
            )
        async with db.get_conn() as conn:
            entries=await conn.fetch("""
                SELECT entry_type, status, reversal_of_draft_id
                  FROM journal_drafts WHERE reversal_of_draft_id=41
                 ORDER BY id
            """)
            assert [r["entry_type"] for r in entries]==["adjustment","reversal"]
            assert await conn.fetchval("SELECT count(*) FROM journal_drafts") == 3
            with pytest.raises(_asyncpg.UniqueViolationError):
                await conn.execute("""
                    INSERT INTO journal_drafts
                      (tenant_id,date,status,entry_type,reversal_of_draft_id)
                    VALUES ('t_alpha','2026-10-30','pending_approval','reversal',41)
                """)
    with db.authenticated_tenant_context("t_beta"):
        made=await reversal.create_reversal_draft(
            "t_beta",42,"2026-10-30","other tenant","maker-b"
        )
        assert made["reversal_of_draft_id"]==42
        async with db.get_conn() as conn:
            assert await conn.fetchval(
                "SELECT count(*) FROM journal_drafts WHERE tenant_id='t_alpha'"
            ) == 0
            assert await conn.fetchval("SELECT count(*) FROM journal_drafts") == 2


@pytest.mark.asyncio
async def test_chat189_concurrent_reversal_requests_produce_one_intent(
    auth_db, monkeypatch
):
    import asyncio
    from app.api.services import reversal_service as reversal
    from pathlib import Path
    await _chat189_prepare_reversal_drafts(auth_db)
    async with auth_db["admin"].acquire() as conn:
        await conn.execute(Path("docs/sql/chat189_reversal_source_unique_DRAFT.sql").read_text())
    monkeypatch.setattr(reversal,"log_event",lambda *a,**kw: None)
    entered=asyncio.Event()
    release=asyncio.Event()
    original_check=reversal._reversal_already_exists
    gate_count=[0]

    async def holding_check(conn,original_id,tenant):
        gate_count[0]+=1
        if gate_count[0]==1:
            entered.set()
            await asyncio.wait_for(release.wait(),timeout=10)
        return await original_check(conn,original_id,tenant)

    monkeypatch.setattr(reversal,"_reversal_already_exists",holding_check)
    async def attempt(maker):
        with db.authenticated_tenant_context("t_alpha"):
            return await reversal.create_reversal_draft(
                "t_alpha",41,"2026-10-30","synthetic concurrent",maker
            )

    first=asyncio.create_task(attempt("maker-a"))
    try:
        await asyncio.wait_for(entered.wait(),timeout=10)
        second=asyncio.create_task(attempt("maker-b"))
        # The second request MUST wait for the first committed source lock.
        await asyncio.sleep(0.1)
        assert not second.done()
    finally:
        release.set()
    results=await asyncio.wait_for(
        asyncio.gather(first,second,return_exceptions=True),timeout=15
    )
    assert sum(isinstance(x,dict) for x in results)==1
    assert sum(isinstance(x,ValueError) and "already exists" in str(x)
               for x in results)==1
    with db.authenticated_tenant_context("t_alpha"):
        async with db.get_conn() as conn:
            assert await conn.fetchval("""
                SELECT count(*) FROM journal_drafts
                WHERE tenant_id='t_alpha' AND reversal_of_draft_id=41
                  AND entry_type='reversal'
            """)==1


@pytest.mark.asyncio
async def test_chat189_migration_refuses_legacy_duplicate_sources_without_deletion(
    auth_db
):
    """No automatic repair/backfill; safe migration preflight refuses dirty history."""
    from pathlib import Path
    await _chat189_prepare_reversal_drafts(auth_db)
    async with auth_db["admin"].acquire() as conn:
        await conn.execute("""
            INSERT INTO journal_drafts
              (tenant_id,date,status,entry_type,reversal_of_draft_id)
            VALUES ('t_alpha','2026-10-25','pending_approval','reversal',41),
                   ('t_alpha','2026-10-25','approved','reversal',41)
        """)
        with pytest.raises(asyncpg.RaiseError,match="FIN11_REVERSAL_DUPLICATE_PREFLIGHT"):
            await conn.execute(Path(
                "docs/sql/chat189_reversal_source_unique_DRAFT.sql"
            ).read_text())
        # A failed explicit BEGIN in the Draft candidate leaves the session
        # aborted; restore the disposable fixture transaction before evidence.
        await conn.execute("ROLLBACK")
        assert await conn.fetchval("""
            SELECT count(*) FROM journal_drafts
            WHERE tenant_id='t_alpha' AND entry_type='reversal'
        """)==2
        assert await conn.fetchval("""
            SELECT count(*) FROM pg_indexes WHERE tablename='journal_drafts'
              AND indexname='uq_chat189_tenant_active_reversal'
        """)==0


@pytest.mark.asyncio
async def test_chat191_unclassified_linked_history_blocks_partial_reversal_index(auth_db):
    """Migration preflight must refuse ambiguous original references; no backfill."""
    from pathlib import Path
    await _chat189_prepare_reversal_drafts(auth_db)
    async with auth_db["admin"].acquire() as conn:
        await conn.execute("""
            INSERT INTO journal_drafts
                (tenant_id, date, status, entry_type, reversal_of_draft_id)
            VALUES ('t_alpha', '2026-10-23', 'pending_approval', 'standard', 41)
        """)
        with pytest.raises(asyncpg.RaiseError, match="FIN11_AMBIGUOUS_CORRECTION_HISTORY_PREFLIGHT"):
            await conn.execute(
                Path("docs/sql/chat189_reversal_source_unique_DRAFT.sql").read_text()
            )
        await conn.execute("ROLLBACK")
        assert await conn.fetchval("""
            SELECT COUNT(*) FROM journal_drafts
            WHERE tenant_id = 't_alpha' AND reversal_of_draft_id = 41
        """) == 1


@pytest.mark.asyncio
async def test_chat191_fin12_outbox_requires_append_only_verified_receipt_before_terminal_state(auth_db):
    """Isolated PostgreSQL15/16 proof: statuses must match append-only evidence.

    No real provider call, no dispatch, no live migrations or ledger mutation.
    """
    from pathlib import Path
    async with auth_db["admin"].acquire() as conn:
        await conn.execute(
            Path("docs/sql/chat186_posting_outbox_DRAFT.sql").read_text(encoding="utf-8")
        )
        intent = await conn.fetchval("""
            INSERT INTO posting_outbox_intents(
              tenant_id,source_id,target_system,idempotency_key,payload_sha256,payload_json
            ) VALUES ('t_alpha','chat191-synthetic','balance',$1,$2,'{}'::jsonb)
            RETURNING id
        """, "a"*64, "b"*64)
        await conn.execute(
            "UPDATE posting_outbox_intents SET state='unknown' WHERE id=$1", intent
        )
        with pytest.raises(asyncpg.RaiseError, match="FIN12_VERIFIED_RECEIPT_REQUIRED"):
            await conn.execute("""
                UPDATE posting_outbox_intents
                SET state='confirmed', provider_receipt_id='synthetic-receipt-1',
                    provider_verified_at=NOW()
                WHERE id=$1
            """, intent)
        with pytest.raises(asyncpg.RaiseError, match="FIN12_VERIFIED_RECEIPT_REQUIRED"):
            await conn.execute(
                "UPDATE posting_outbox_intents SET state='rejected' WHERE id=$1", intent
            )
        assert await conn.fetchval(
            "SELECT state FROM posting_outbox_intents WHERE id=$1", intent
        ) == "unknown"
        await conn.execute("""
            INSERT INTO posting_outbox_receipts(
                outbox_id,tenant_id,outcome,provider_receipt_id,
                evidence_sha256,verified_by,verified_at
            ) VALUES ($1,'t_alpha','accepted','synthetic-receipt-1',$2,
                      'synthetic-reviewed-adapter',NOW())
        """, intent, "c"*64)
        await conn.execute("""
            UPDATE posting_outbox_intents
            SET state='confirmed',provider_receipt_id='synthetic-receipt-1',
                provider_verified_at=NOW() WHERE id=$1
        """, intent)
        assert await conn.fetchval(
            "SELECT state FROM posting_outbox_intents WHERE id=$1", intent
        ) == "confirmed"
        with pytest.raises(asyncpg.RaiseError, match="FIN12_RECEIPT_OR_INTENT_IMMUTABLE"):
            await conn.execute("""
                UPDATE posting_outbox_intents SET provider_receipt_id='forged'
                WHERE id=$1
            """, intent)


# Chat192 FIN-11 maker/checker only in disposable PostgreSQL 15/16.
async def _chat192_setup_review_candidates(auth_db):
    from pathlib import Path
    await _chat189_prepare_reversal_drafts(auth_db)
    async with auth_db["admin"].acquire() as conn:
        candidate = Path(
            "docs/sql/chat192_fin11_correction_reviews_DRAFT.sql"
        ).read_text(encoding="utf-8")
        await conn.execute(candidate)
        await conn.execute(candidate)
        await conn.execute("""
            INSERT INTO journal_drafts
               (id,tenant_id,date,description,amount,currency,status,
                entry_type,reversal_of_draft_id,reversal_reason,lines_json)
            VALUES
               (71,'t_alpha','2026-10-30','synthetic reversal',100,'GEL',
                'pending_approval','reversal',41,'source error',
                '[{"account_code":"1120","debit":0,"credit":100},
                  {"account_code":"6110","debit":100,"credit":0}]'::jsonb),
               (72,'t_alpha','2026-10-30','synthetic adjustment',100,'GEL',
                'pending_approval','adjustment',41,'correct amount',
                '[{"account_code":"1120","debit":100,"credit":0},
                  {"account_code":"6110","debit":0,"credit":100}]'::jsonb)
        """)
        await conn.execute("""
            INSERT INTO audit_log
                (actor,role,action,resource,resource_id,new_value,status,tenant_id)
            VALUES
                ('auth:maker-71','maker','reversal_draft_created',
                 'journal_drafts','71',
                 '{"source_id":41,"status":"pending_approval"}'::jsonb,
                 'success','t_alpha'),
                ('auth:maker-72','maker','adjustment_draft_created',
                 'journal_drafts','72',
                 '{"source_id":41,"status":"pending_approval"}'::jsonb,
                 'success','t_alpha')
        """)
        await conn.execute(
            f'GRANT SELECT,INSERT,UPDATE ON correction_review_intents '
            f'TO "{auth_db["role"]}"'
        )
        await conn.execute(
            f'GRANT SELECT,INSERT ON correction_review_events '
            f'TO "{auth_db["role"]}"'
        )
        await conn.execute(
            f'GRANT USAGE,SELECT ON SEQUENCE correction_review_intents_id_seq,'
            f'correction_review_events_id_seq TO "{auth_db["role"]}"'
        )


@pytest.mark.asyncio
async def test_chat192_independent_review_is_transactional_tenant_scoped_and_no_posting(auth_db):
    from app.api.services.correction_review_service import (
        CorrectionReviewUnavailable, submit_correction_review, decide_correction_review,
    )
    await _chat192_setup_review_candidates(auth_db)
    with db.authenticated_tenant_context("t_alpha"):
        with pytest.raises(CorrectionReviewUnavailable, match="FIN11_REVIEW_MAKER_NOT_CREATOR"):
            async with db.get_conn() as conn:
                await submit_correction_review(
                    conn, tenant_id="t_alpha", draft_id=71,
                    maker_subject="auth:impersonator", maker_role="accountant",
                )
        async with db.get_conn() as conn:
            submitted = await submit_correction_review(
                conn, tenant_id="t_alpha", draft_id=71,
                maker_subject="auth:maker-71", maker_role="accountant",
            )
            assert submitted["state"] == "awaiting_checker"
            assert submitted["posted"] is False
            assert await conn.fetchval(
                "SELECT COUNT(*) FROM correction_review_events WHERE tenant_id='t_alpha'"
            ) == 1
            assert await conn.fetchval(
                "SELECT COUNT(*) FROM audit_log WHERE action='correction_review_submitted'"
            ) == 1

        # If a maker tries a CFO role or the checker uses the same subject,
        # identity separation still blocks the decision.
        with pytest.raises(CorrectionReviewUnavailable, match="FIN11_SELF_APPROVAL_DENIED"):
            async with db.get_conn() as conn:
                await decide_correction_review(
                    conn, tenant_id="t_alpha", draft_id=71,
                    checker_subject="auth:maker-71", checker_role="cfo",
                    decision="approved",
                )
        with pytest.raises(CorrectionReviewUnavailable, match="FIN11_REVIEW_ROLE_FORBIDDEN"):
            async with db.get_conn() as conn:
                await decide_correction_review(
                    conn, tenant_id="t_alpha", draft_id=71,
                    checker_subject="auth:reviewer", checker_role="reviewer",
                    decision="approved",
                )

    # A review cannot be applied to changed financial data.
    async with auth_db["admin"].acquire() as conn:
        await conn.execute("UPDATE journal_drafts SET amount=101 WHERE id=71")
    with db.authenticated_tenant_context("t_alpha"):
        with pytest.raises(CorrectionReviewUnavailable, match="FIN11_REVIEW_SOURCE_CHANGED"):
            async with db.get_conn() as conn:
                await decide_correction_review(
                    conn, tenant_id="t_alpha", draft_id=71,
                    checker_subject="auth:cfo-2", checker_role="cfo",
                    decision="approved",
                )
    async with auth_db["admin"].acquire() as conn:
        await conn.execute("UPDATE journal_drafts SET amount=100 WHERE id=71")
    with db.authenticated_tenant_context("t_alpha"):
        async with db.get_conn() as conn:
            decision = await decide_correction_review(
                conn, tenant_id="t_alpha", draft_id=71,
                checker_subject="auth:cfo-2", checker_role="cfo",
                decision="approved", reason="verified synthetic evidence",
            )
            assert decision["state"] == "approved"
            assert decision["posted"] is False
            assert await conn.fetchval(
                "SELECT status FROM journal_drafts WHERE id=71"
            ) == "pending_approval"
            assert await conn.fetchval(
                "SELECT COUNT(*) FROM correction_review_events WHERE action='approved'"
            ) == 1
            assert await conn.fetchval(
                "SELECT COUNT(*) FROM audit_log WHERE action='correction_review_approved'"
            ) == 1
        with pytest.raises(CorrectionReviewUnavailable, match="FIN11_REVIEW_NOT_AWAITING_CHECKER"):
            async with db.get_conn() as conn:
                await decide_correction_review(
                    conn, tenant_id="t_alpha", draft_id=71,
                    checker_subject="auth:cfo-3", checker_role="cfo",
                    decision="approved",
                )

    with db.authenticated_tenant_context("t_beta"):
        async with db.get_conn() as conn:
            assert await conn.fetchval(
                "SELECT count(*) FROM correction_review_intents"
            ) == 0
            assert await conn.fetchval(
                "SELECT count(*) FROM correction_review_events"
            ) == 0
            assert await conn.fetchval(
                "SELECT count(*) FROM audit_log WHERE action LIKE 'correction_review_%'"
            ) == 0
        with pytest.raises(CorrectionReviewUnavailable, match="FIN11_REVIEW_DRAFT_NOT_FOUND"):
            async with db.get_conn() as conn:
                await submit_correction_review(
                    conn, tenant_id="t_beta", draft_id=71,
                    maker_subject="auth:beta", maker_role="accountant",
                )


@pytest.mark.asyncio
async def test_chat192_rejection_and_direct_sql_bypass_denied(auth_db):
    from app.api.services.correction_review_service import (
        CorrectionReviewUnavailable, submit_correction_review, decide_correction_review,
    )
    await _chat192_setup_review_candidates(auth_db)
    with db.authenticated_tenant_context("t_alpha"):
        async with db.get_conn() as conn:
            await submit_correction_review(
                conn, tenant_id="t_alpha", draft_id=72,
                maker_subject="auth:maker-72", maker_role="accountant",
            )
            review_id = await conn.fetchval(
                "SELECT id FROM correction_review_intents WHERE draft_id=72"
            )
        with pytest.raises(CorrectionReviewUnavailable, match="FIN11_REVIEW_REASON_REQUIRED"):
            async with db.get_conn() as conn:
                await decide_correction_review(
                    conn, tenant_id="t_alpha", draft_id=72,
                    checker_subject="auth:cfo-1", checker_role="cfo",
                    decision="rejected", reason="",
                )

    # An unverified maker may not fabricate a review even via raw SQL.
    async with auth_db["admin"].acquire() as conn:
        with pytest.raises(asyncpg.RaiseError, match="FIN11_REVIEW_MAKER_SOURCE_MISMATCH"):
            await conn.execute("""
                INSERT INTO correction_review_intents
                    (tenant_id,draft_id,source_id,entry_type,maker_subject,
                     maker_role,source_fingerprint)
                VALUES ('t_alpha',71,41,'reversal','auth:attacker',
                        'accountant',$1)
            """, 'a'*64)

    # Even an owner cannot flip the status without prior matching evidence.
    async with auth_db["admin"].acquire() as conn:
        with pytest.raises(asyncpg.RaiseError, match="FIN11_REVIEW_CHECKER_EVIDENCE_REQUIRED"):
            await conn.execute("""
                UPDATE correction_review_intents
                SET state='approved',checker_subject='auth:cfo-1',
                    checker_role='cfo',decided_at=NOW() WHERE id=$1
            """, review_id)

    with db.authenticated_tenant_context("t_alpha"):
        async with db.get_conn() as conn:
            result = await decide_correction_review(
                conn, tenant_id="t_alpha", draft_id=72,
                checker_subject="auth:cfo-1", checker_role="cfo",
                decision="rejected", reason="synthetic mismatch",
            )
            assert result["state"] == "rejected"
            assert await conn.fetchval(
                "SELECT status FROM journal_drafts WHERE id=72"
            ) == "pending_approval"

    async with auth_db["admin"].acquire() as conn:
        with pytest.raises(asyncpg.RaiseError, match="FIN11_REVIEW_EVIDENCE_IMMUTABLE"):
            await conn.execute("""
                UPDATE correction_review_events
                   SET actor_subject='forged' WHERE review_id=$1
            """, review_id)
        with pytest.raises(asyncpg.RaiseError, match="FIN11_REVIEW_EVIDENCE_IMMUTABLE"):
            await conn.execute("""
                DELETE FROM correction_review_intents WHERE id=$1
            """, review_id)
        assert await conn.fetchval(
            "SELECT state FROM correction_review_intents WHERE id=$1", review_id
        ) == "rejected"


# FIN-12 Chat193: all tests run ONLY in temporary PG15/16 schema/nonowner role.
async def _chat193_setup_reconciliation(auth_db):
    from pathlib import Path
    import uuid
    async with auth_db["admin"].acquire() as conn:
        for name in ("chat186_posting_outbox_DRAFT.sql",
                     "chat193_fin12_unknown_reconciliation_DRAFT.sql"):
            sql = Path("docs/sql", name).read_text(encoding="utf-8")
            await conn.execute(sql)
            await conn.execute(sql)
        alpha = await conn.fetchval("""
            INSERT INTO posting_outbox_intents(
                tenant_id,source_id,target_system,idempotency_key,
                payload_sha256,payload_json,state
            ) VALUES ('t_alpha','synthetic-41','balance',$1,$2,
                      '{"amount":100}'::jsonb,'unknown')
            RETURNING id
        """, "a"*64, "b"*64)
        beta = await conn.fetchval("""
            INSERT INTO posting_outbox_intents(
                tenant_id,source_id,target_system,idempotency_key,
                payload_sha256,payload_json,state
            ) VALUES ('t_beta','synthetic-42','balance',$1,$2,
                      '{"amount":20}'::jsonb,'unknown')
            RETURNING id
        """, "c"*64, "d"*64)
        prepared = await conn.fetchval("""
            INSERT INTO posting_outbox_intents(
                tenant_id,source_id,target_system,idempotency_key,
                payload_sha256,payload_json,state
            ) VALUES ('t_alpha','synthetic-43','balance',$1,$2,
                      '{"amount":30}'::jsonb,'prepared')
            RETURNING id
        """, "e"*64, "f"*64)
        await conn.execute(
            f'GRANT SELECT ON posting_outbox_receipts TO "{auth_db["role"]}"'
        )
        for tbl in ("posting_outbox_intents",
                    "posting_outbox_reconciliation_cases",
                    "posting_outbox_reconciliation_events"):
            rights = ("SELECT,INSERT,UPDATE" if tbl.endswith("_cases")
                      else "SELECT,INSERT" if tbl.endswith("_events")
                      else "SELECT")
            await conn.execute(f'GRANT {rights} ON {tbl} TO "{auth_db["role"]}"')
        await conn.execute(
            f'GRANT USAGE,SELECT ON posting_outbox_reconciliation_cases_id_seq,'
            f'posting_outbox_reconciliation_events_id_seq TO "{auth_db["role"]}"'
        )
    return str(alpha), str(beta), str(prepared)


@pytest.mark.asyncio
async def test_chat193_unknown_manual_review_never_confirms_posts_or_retries(auth_db):
    from app.api.services.posting_outbox_reconciliation_service import (
        ManualReconciliationUnavailable,
        open_unknown_reconciliation, review_unknown_reconciliation,
    )
    alpha, beta, prepared = await _chat193_setup_reconciliation(auth_db)
    with db.authenticated_tenant_context("t_alpha"):
        async with db.get_conn() as conn:
            result = await open_unknown_reconciliation(
                conn, tenant_id="t_alpha", intent_id=alpha,
                opener_subject="auth:accountant-1", opener_role="accountant",
                claimed_outcome="claimed_accepted", evidence_sha256="1"*64,
            )
            assert result["state"] == "open"
            assert result["dispatch_allowed"] is False
            assert result["provider_verified"] is False
            assert await conn.fetchval(
                "SELECT state FROM posting_outbox_intents WHERE id=$1",
                __import__("uuid").UUID(alpha)
            ) == "unknown"
            assert await conn.fetchval(
                "SELECT count(*) FROM posting_outbox_receipts"
            ) == 0

        with pytest.raises(ManualReconciliationUnavailable, match="FIN12_RECON_ALREADY_OPEN"):
            async with db.get_conn() as conn:
                await open_unknown_reconciliation(
                    conn, tenant_id="t_alpha", intent_id=alpha,
                    opener_subject="auth:accountant-1", opener_role="accountant",
                    claimed_outcome="claimed_accepted", evidence_sha256="1"*64,
                )
        with pytest.raises(ManualReconciliationUnavailable, match="FIN12_RECON_SELF_REVIEW_DENIED"):
            async with db.get_conn() as conn:
                await review_unknown_reconciliation(
                    conn, tenant_id="t_alpha", intent_id=alpha,
                    reviewer_subject="auth:accountant-1", reviewer_role="cfo",
                )
        async with db.get_conn() as conn:
            reviewed = await review_unknown_reconciliation(
                conn, tenant_id="t_alpha", intent_id=alpha,
                reviewer_subject="auth:cfo-2", reviewer_role="cfo",
            )
            assert reviewed["state"] == "reviewed_hold"
            assert reviewed["dispatch_allowed"] is False
            assert reviewed["provider_verified"] is False
            assert reviewed["retry_allowed"] is False
            assert await conn.fetchval(
                "SELECT count(*) FROM posting_outbox_reconciliation_events"
            ) == 2
            assert await conn.fetchval(
                "SELECT state FROM posting_outbox_intents WHERE id=$1",
                __import__("uuid").UUID(alpha)
            ) == "unknown"
            assert await conn.fetchval(
                "SELECT count(*) FROM posting_outbox_receipts"
            ) == 0
        with pytest.raises(ManualReconciliationUnavailable, match="FIN12_RECON_ALREADY_REVIEWED"):
            async with db.get_conn() as conn:
                await review_unknown_reconciliation(
                    conn, tenant_id="t_alpha", intent_id=alpha,
                    reviewer_subject="auth:cfo-3", reviewer_role="cfo",
                )

    with db.authenticated_tenant_context("t_beta"):
        async with db.get_conn() as conn:
            assert await conn.fetchval(
                "SELECT count(*) FROM posting_outbox_reconciliation_cases"
            ) == 0
            assert await conn.fetchval(
                "SELECT count(*) FROM posting_outbox_reconciliation_events"
            ) == 0
        with pytest.raises(ManualReconciliationUnavailable, match="FIN12_RECON_SOURCE_NOT_FOUND"):
            async with db.get_conn() as conn:
                await open_unknown_reconciliation(
                    conn, tenant_id="t_beta", intent_id=alpha,
                    opener_subject="auth:beta-accountant", opener_role="accountant",
                    claimed_outcome="undetermined", evidence_sha256="2"*64,
                )


@pytest.mark.asyncio
async def test_chat193_direct_sql_cannot_open_prepared_or_mutate_case_history(auth_db):
    import uuid
    from app.api.services.posting_outbox_reconciliation_service import (
        open_unknown_reconciliation,
    )
    alpha, _, prepared = await _chat193_setup_reconciliation(auth_db)
    async with auth_db["admin"].acquire() as conn:
        with pytest.raises(asyncpg.RaiseError, match="FIN12_RECON_SOURCE_NOT_UNKNOWN"):
            await conn.execute("""
                INSERT INTO posting_outbox_reconciliation_cases
                  (tenant_id,outbox_id,source_id,target_system,
                   idempotency_key,payload_sha256,opener_subject,opener_role,
                   claimed_outcome,evidence_sha256)
                VALUES ('t_alpha',$1,'synthetic-43','balance',$2,$3,
                        'auth:malicious','accountant','undetermined',$4)
            """, uuid.UUID(prepared), "e"*64, "f"*64, "3"*64)
    with db.authenticated_tenant_context("t_alpha"):
        async with db.get_conn() as conn:
            await open_unknown_reconciliation(
                conn, tenant_id="t_alpha", intent_id=alpha,
                opener_subject="auth:accountant-1", opener_role="accountant",
                claimed_outcome="undetermined", evidence_sha256="1"*64,
            )
    async with auth_db["admin"].acquire() as conn:
        with pytest.raises(asyncpg.RaiseError, match="FIN12_RECON_HISTORY_IMMUTABLE"):
            await conn.execute("""
                DELETE FROM posting_outbox_reconciliation_events
                 WHERE tenant_id='t_alpha'
            """)
        with pytest.raises(asyncpg.RaiseError, match="FIN12_RECON_HISTORY_IMMUTABLE"):
            await conn.execute("""
                UPDATE posting_outbox_reconciliation_cases
                   SET opener_subject='forged' WHERE tenant_id='t_alpha'
            """)
        assert await conn.fetchval(
            "SELECT count(*) FROM posting_outbox_reconciliation_events"
        ) == 1


# FIN-12 Chat194: synthetically signed receipt *candidates* only.
async def _chat194_setup_receipt_candidate(auth_db):
    from pathlib import Path
    async with auth_db["admin"].acquire() as conn:
        for name in ("chat186_posting_outbox_DRAFT.sql",
                     "chat194_fin12_signed_receipt_candidates_DRAFT.sql"):
            sql = Path("docs/sql", name).read_text(encoding="utf-8")
            await conn.execute(sql)
            await conn.execute(sql)
        alpha = await conn.fetchval("""
            INSERT INTO posting_outbox_intents(
                tenant_id,source_id,target_system,idempotency_key,
                payload_sha256,payload_json,state
            ) VALUES ('t_alpha','draft41','balance',$1,$2,
                      '{"amount":100}'::jsonb,'unknown')
            RETURNING id
        """, "a"*64, "b"*64)
        beta = await conn.fetchval("""
            INSERT INTO posting_outbox_intents(
                tenant_id,source_id,target_system,idempotency_key,
                payload_sha256,payload_json,state
            ) VALUES ('t_beta','draft41','balance',$1,$2,
                      '{"amount":100}'::jsonb,'unknown')
            RETURNING id
        """, "c"*64, "d"*64)
        prepared = await conn.fetchval("""
            INSERT INTO posting_outbox_intents(
                tenant_id,source_id,target_system,idempotency_key,
                payload_sha256,payload_json,state
            ) VALUES ('t_alpha','draft43','balance',$1,$2,
                      '{"amount":20}'::jsonb,'prepared')
            RETURNING id
        """, "e"*64, "f"*64)
        await conn.execute(
            f'GRANT SELECT ON posting_outbox_intents, posting_outbox_receipts '
            f'TO "{auth_db["role"]}"'
        )
        await conn.execute(
            f'GRANT SELECT,INSERT ON posting_outbox_receipt_candidates '
            f'TO "{auth_db["role"]}"'
        )
    return str(alpha), str(beta), str(prepared)


@pytest.mark.asyncio
async def test_chat194_signed_receipt_candidates_never_set_real_vendor_state(auth_db):
    import base64
    from datetime import datetime, timezone
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from app.api.services.signed_receipt_candidate_service import (
        SyntheticReceiptUntrusted, canonical_synthetic_message,
        record_synthetic_receipt_candidate,
    )
    alpha, beta, prepared = await _chat194_setup_receipt_candidate(auth_db)
    private = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
    public = private.public_key().public_bytes_raw()
    now = datetime(2026, 10, 30, 17, 0, tzinfo=timezone.utc)
    env = {
        "version": 1, "key_id": "synthetic-issuer-1",
        "issued_at": "2026-10-30T17:00:00Z",
        "tenant_id": "t_alpha", "outbox_id": alpha,
        "source_id": "draft41", "target_system": "balance",
        "idempotency_key": "a"*64, "payload_sha256": "b"*64,
        "provider_receipt_id": "synthetic-receipt-41",
        "outcome": "accepted",
    }
    signature = base64.b64encode(
        private.sign(canonical_synthetic_message(env))
    ).decode("ascii")
    with db.authenticated_tenant_context("t_alpha"):
        async with db.get_conn() as conn:
            recorded = await record_synthetic_receipt_candidate(
                conn, tenant_id="t_alpha", intent_id=alpha,
                envelope=env, signature_b64=signature,
                trusted_key_id="synthetic-issuer-1",
                trusted_public_key=public, now=now,
            )
            assert recorded["synthetic_integrity_ok"] is True
            assert recorded["vendor_authenticated"] is False
            assert recorded["provider_verified"] is False
            assert recorded["confirm_allowed"] is False
            assert recorded["retry_allowed"] is False
            assert await conn.fetchval(
                "SELECT COUNT(*) FROM posting_outbox_receipt_candidates"
            ) == 1
            assert await conn.fetchval(
                "SELECT COUNT(*) FROM posting_outbox_receipts"
            ) == 0
            assert await conn.fetchval(
                "SELECT state FROM posting_outbox_intents WHERE id=$1",
                __import__("uuid").UUID(alpha),
            ) == "unknown"
        with pytest.raises(SyntheticReceiptUntrusted, match="FIN12_RECEIPT_CANDIDATE_STORAGE_CONFLICT"):
            async with db.get_conn() as conn:
                await record_synthetic_receipt_candidate(
                    conn, tenant_id="t_alpha", intent_id=alpha,
                    envelope=env, signature_b64=signature,
                    trusted_key_id="synthetic-issuer-1",
                    trusted_public_key=public, now=now,
                )
    with db.authenticated_tenant_context("t_beta"):
        async with db.get_conn() as conn:
            assert await conn.fetchval(
                "SELECT COUNT(*) FROM posting_outbox_receipt_candidates"
            ) == 0
        with pytest.raises(SyntheticReceiptUntrusted, match="FIN12_RECEIPT_TENANT_UNAUTHORIZED"):
            async with db.get_conn() as conn:
                await record_synthetic_receipt_candidate(
                    conn, tenant_id="t_beta", intent_id=alpha,
                    envelope=env, signature_b64=signature,
                    trusted_key_id="synthetic-issuer-1",
                    trusted_public_key=public, now=now,
                )
        cross_env = {**env, "tenant_id": "t_beta"}
        cross_sig = base64.b64encode(
            private.sign(canonical_synthetic_message(cross_env))
        ).decode("ascii")
        with pytest.raises(SyntheticReceiptUntrusted, match="FIN12_RECEIPT_SOURCE_NOT_FOUND"):
            async with db.get_conn() as conn:
                await record_synthetic_receipt_candidate(
                    conn, tenant_id="t_beta", intent_id=alpha,
                    envelope=cross_env, signature_b64=cross_sig,
                    trusted_key_id="synthetic-issuer-1",
                    trusted_public_key=public, now=now,
                )

    async with auth_db["admin"].acquire() as conn:
        with pytest.raises(asyncpg.RaiseError, match="FIN12_RECEIPT_CANDIDATE_SOURCE_INVALID"):
            await conn.execute("""
                INSERT INTO posting_outbox_receipt_candidates
                  (tenant_id,outbox_id,source_id,target_system,idempotency_key,
                   payload_sha256,provider_receipt_id,outcome,signer_key_id,
                   envelope_sha256,signature_sha256)
                VALUES ('t_alpha',$1,'draft43','balance',$2,$3,
                        'fake-receipt-43','accepted','synthetic-issuer-1',$4,$5)
            """, __import__("uuid").UUID(prepared), "e"*64,"f"*64,"1"*64,"2"*64)
        with pytest.raises(asyncpg.RaiseError, match="FIN12_RECEIPT_CANDIDATE_IMMUTABLE"):
            await conn.execute("""
                UPDATE posting_outbox_receipt_candidates
                SET provider_receipt_id='forged' WHERE tenant_id='t_alpha'
            """)
        with pytest.raises(asyncpg.RaiseError, match="FIN12_RECEIPT_CANDIDATE_IMMUTABLE"):
            await conn.execute("""
                DELETE FROM posting_outbox_receipt_candidates WHERE tenant_id='t_alpha'
            """)
        assert await conn.fetchval(
            "SELECT count(*) FROM posting_outbox_receipt_candidates"
        ) == 1


# Chat195 FIN-12: local receipt metadata is not vendor authentication.
@pytest.mark.asyncio
async def test_chat195_untrusted_receipts_cannot_create_terminal_intents_or_backfill_acceptance(auth_db):
    from pathlib import Path
    async with auth_db["admin"].acquire() as conn:
        await conn.execute(Path(
            "docs/sql/chat186_posting_outbox_DRAFT.sql"
        ).read_text(encoding="utf-8"))
        # BEFORE INSERT must not bypass the state-machine and vendor trust hold.
        for initial in ("unknown", "in_flight", "rejected"):
            with pytest.raises(asyncpg.RaiseError, match="FIN12_INITIAL_STATE_NOT_PREPARED"):
                await conn.execute("""
                    INSERT INTO posting_outbox_intents
                        (tenant_id,source_id,target_system,idempotency_key,
                         payload_sha256,payload_json,state)
                    VALUES ('t_alpha',$1,'balance',$2,$3,'{}'::jsonb,$4)
                """, "initial-"+initial, "a"*64, "b"*64, initial)
        with pytest.raises(asyncpg.RaiseError, match="FIN12_INITIAL_STATE_NOT_PREPARED"):
            await conn.execute("""
                INSERT INTO posting_outbox_intents
                    (tenant_id,source_id,target_system,idempotency_key,
                     payload_sha256,payload_json,state,
                     provider_receipt_id,provider_verified_at)
                VALUES ('t_alpha','initial-confirmed','balance',$1,$2,
                        '{}'::jsonb,'confirmed','forged-erp-ack',NOW())
            """, "c"*64, "d"*64)

        intent = await conn.fetchval("""
            INSERT INTO posting_outbox_intents
                (tenant_id,source_id,target_system,idempotency_key,
                 payload_sha256,payload_json)
            VALUES ('t_alpha','chat195-test','balance',$1,$2,'{}'::jsonb)
            RETURNING id
        """, "e"*64, "f"*64)
        await conn.execute(
            "UPDATE posting_outbox_intents SET state='unknown' WHERE id=$1", intent
        )
        for outcome in ("accepted", "rejected"):
            with pytest.raises(asyncpg.RaiseError, match="FIN12_UNVERIFIED_PROVIDER_RECEIPT_HOLD"):
                await conn.execute("""
                    INSERT INTO posting_outbox_receipts(
                       outbox_id,tenant_id,outcome,provider_receipt_id,
                       evidence_sha256,verified_by,verified_at)
                    VALUES ($1,'t_alpha',$2,'fake-erp-receipt',$3,
                            'manual-actor-pretending-vendor',NOW())
                """, intent, outcome, "f"*64)

        for new_state in ("confirmed", "rejected"):
            with pytest.raises(asyncpg.RaiseError, match="FIN12_VENDOR_AUTHENTICATION_NOT_CONFIGURED"):
                await conn.execute("""
                    UPDATE posting_outbox_intents
                    SET state=$1,provider_receipt_id=$2,provider_verified_at=$3
                    WHERE id=$4
                """, new_state,
                     "fake-erp-receipt" if new_state == "confirmed" else None,
                     __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                     if new_state == "confirmed" else None, intent)
        assert await conn.fetchval(
            "SELECT state FROM posting_outbox_intents WHERE id=$1", intent
        ) == "unknown"
        assert await conn.fetchval(
            "SELECT count(*) FROM posting_outbox_receipts"
        ) == 0
