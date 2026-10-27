import os
import jwt
import logging
from datetime import datetime, timezone, timedelta
from app.api.models.user import get_user, verify_password, update_last_login, has_permission
from app.config.secrets import get_secret

log = logging.getLogger(__name__)


_PLACEHOLDER_SECRETS: frozenset[str] = frozenset({
    "test-secret", "dev-secret", "secret", "changeme",
    "your-secret-here", "insecure", "unsafe", "password",
    "default", "placeholder", "replace-me", "example",
    "jwt-secret", "jwt_secret", "mysecret", "supersecret",
})


def _load_jwt_secret() -> str:
    secret = get_secret("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET is not configured")
    is_test = os.environ.get("TEST_MODE") == "1"
    if not is_test and secret.lower() in _PLACEHOLDER_SECRETS:
        raise RuntimeError("JWT_SECRET must not use a default or placeholder value in production")
    if len(secret.encode("utf-8")) < 32:
        if is_test:
            log.warning("JWT_SECRET is shorter than 32 bytes; allowed only because TEST_MODE=1")
        else:
            raise RuntimeError("JWT_SECRET must be at least 32 bytes for HS256")
    return secret


_SECRET_KEY_CACHE: str | None = None


def _get_secret_key() -> str:
    """Lazy loader — resolves JWT_SECRET on first call, not at module import.
    Prevents startup crash when JWT_SECRET is not yet in env during container init."""
    global _SECRET_KEY_CACHE
    if _SECRET_KEY_CACHE is None:
        _SECRET_KEY_CACHE = _load_jwt_secret()
    return _SECRET_KEY_CACHE


def validate_jwt_secret_at_startup() -> None:
    """Eagerly validate JWT_SECRET at app startup. Fail fast before accepting traffic.
    Never logs the secret value — only safe diagnostic codes on failure."""
    global _SECRET_KEY_CACHE
    try:
        validated = _load_jwt_secret()
        _SECRET_KEY_CACHE = validated
        log.info("action=startup_jwt_validation_ok")
    except RuntimeError as exc:
        log.critical("action=startup_jwt_validation_failed reason=%s", type(exc).__name__)
        raise

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
REFRESH_TOKEN_EXPIRE_DAYS = 7


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def jwt_session_version_enabled() -> bool:
    """Controlled rollout. Requires migration 015 before activation.

    Must be consistently enabled on all serving replicas. Default is OFF.
    """
    return os.environ.get("JWT_SESSION_VERSION_ENABLED", "0") == "1"


def _required_auth_version(user) -> int:
    """Fail closed: never mint a non-revocable JWT with the flag enabled."""
    version = user["auth_version"]
    if type(version) is not int or version < 1:
        raise ValueError("valid database auth_version required")
    return version


def _create_access_token(user: dict) -> str:
    payload = {
        "sub": str(user["id"]),
        "type": "access",
        "email": user["email"],
        "role": user["role"],
        "tenant_id": user["tenant_id"],
        "iat": _now_ts(),
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)).timestamp()),
    }
    if jwt_session_version_enabled():
        payload["auth_version"] = _required_auth_version(user)
    return jwt.encode(payload, _get_secret_key(), algorithm=ALGORITHM)


def _create_refresh_token(user: dict) -> str:
    payload = {
        "sub": str(user["id"]),
        "type": "refresh",
        "email": user["email"],
        "role": user["role"],
        "tenant_id": user["tenant_id"],
        "iat": _now_ts(),
        "exp": int((datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).timestamp()),
    }
    if jwt_session_version_enabled():
        payload["auth_version"] = _required_auth_version(user)
    return jwt.encode(payload, _get_secret_key(), algorithm=ALGORITHM)


def create_access_token(payload_extra: dict) -> str:
    if jwt_session_version_enabled():
        _required_auth_version(payload_extra)
    now = datetime.now(timezone.utc)
    payload = {
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)).timestamp()),
        **payload_extra,
    }
    return jwt.encode(payload, _get_secret_key(), algorithm=ALGORITHM)


def create_refresh_token(payload_extra: dict) -> str:
    if jwt_session_version_enabled():
        _required_auth_version(payload_extra)
    now = datetime.now(timezone.utc)
    payload = {
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).timestamp()),
        **payload_extra,
    }
    return jwt.encode(payload, _get_secret_key(), algorithm=ALGORITHM)


async def _resolve_tenant_id(tenant_id: str) -> str:
    """If tenant_id looks like a company INN (all digits), resolve it to the actual tenant_id."""
    if not tenant_id or not tenant_id.strip().isdigit():
        return tenant_id
    try:
        from app.api.db import get_conn, _q
        async with get_conn() as conn:
            row = await conn.fetchrow(_q(
                "SELECT tenant_id FROM tenants WHERE company_inn = %s LIMIT 1"
            ), tenant_id.strip())
        return row[0] if row else tenant_id
    except Exception:
        return tenant_id


async def login(email: str, password: str, tenant_id: str = "default") -> dict:
    resolved = await _resolve_tenant_id(tenant_id)
    user = await get_user(email, resolved)
    if not user and resolved != tenant_id:
        user = await get_user(email, tenant_id)
    if not user:
        return {"ok": False, "error": "მომხმარებელი ვერ მოიძებნა"}

    if not verify_password(password, user["password_hash"]):
        return {"ok": False, "error": "პაროლი არასწორია"}

    access_token = _create_access_token(user)
    refresh_token = _create_refresh_token(user)
    await update_last_login(user["id"])

    return {
        "ok": True,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "tenant_id": user["tenant_id"],
        },
    }


def verify_token(token: str, expected_type: str = "access") -> dict | None:
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
        if payload.get("type") != expected_type:
            return None
        return payload
    except Exception:
        return None


def access_membership_check_enabled() -> bool:
    """Explicit release gate for per-request JWT revocation validation.

    Keep disabled until the real DB schema, throughput and failure behavior
    have passed staging. A release MUST deliberately set this to '1'.
    """
    return (
        os.environ.get("ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK", "0") == "1"
        or jwt_session_version_enabled()
    )


async def verify_live_access_membership(payload: dict) -> bool:
    """Verify a signed access claim still matches an active tenant member.

    Called only after signature/type/expiration verification. Database errors
    propagate so callers can respond 503 (fail closed), not accept a token
    whose current membership cannot be established.
    """
    if not isinstance(payload, dict):
        return False
    subject = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    email = payload.get("email")
    role = payload.get("role")
    if (
        not isinstance(subject, str)
        or not subject.isascii()
        or not subject.isdecimal()
        or not 0 < len(subject) <= 18
        or int(subject) <= 0
        or not isinstance(tenant_id, str)
        or not tenant_id
        or tenant_id != tenant_id.strip()
        or tenant_id.casefold() == "default"
        or not isinstance(email, str)
        or not email.strip()
        or not isinstance(role, str)
        or not role.strip()
    ):
        return False

    version_enabled = jwt_session_version_enabled()
    if version_enabled:
        claim_version = payload.get("auth_version")
        if type(claim_version) is not int or claim_version < 1:
            return False

    from app.api.db import _q, get_conn, tenant_db_context

    columns = "id, email, role, tenant_id, auth_version" if version_enabled else "id, email, role, tenant_id"
    async with tenant_db_context(tenant_id):
        async with get_conn() as conn:
            current = await conn.fetchrow(
                _q(
                    f"SELECT {columns} FROM users "
                    "WHERE id=%s AND tenant_id=%s AND is_active=TRUE"
                ),
                int(subject),
                tenant_id,
            )
    if not current:
        return False
    return (
        str(current["id"]) == subject
        and current["tenant_id"] == tenant_id
        and current["role"] == role
        and isinstance(current["email"], str)
        and current["email"].casefold() == email.casefold()
        and (
            not version_enabled
            or current["auth_version"] == claim_version
        )
    )


async def refresh_token(refresh_token_value: str) -> dict | None:
    """Renew tokens only while the signed user's tenant membership is active.

    Refresh requests are public endpoints, so explicitly bind the verified
    tenant context for this DB read. Never trust role/email claims after the
    membership has been disabled or edited in the database.
    """
    payload = verify_token(refresh_token_value, expected_type="refresh")
    if not payload:
        return None

    subject = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    email = payload.get("email")
    role = payload.get("role")
    if (
        not isinstance(subject, str)
        or not subject.isascii()
        or not subject.isdecimal()
        or not 0 < len(subject) <= 18
        or int(subject) <= 0
        or not isinstance(tenant_id, str)
        or not tenant_id
        or tenant_id != tenant_id.strip()
        or tenant_id.casefold() == "default"
        or not isinstance(email, str)
        or not email.strip()
        or not isinstance(role, str)
        or not role
    ):
        return None

    version_enabled = jwt_session_version_enabled()
    if version_enabled:
        claim_version = payload.get("auth_version")
        if type(claim_version) is not int or claim_version < 1:
            return None

    try:
        from app.api.db import _q, get_conn, tenant_db_context
        columns = "id, email, role, tenant_id, auth_version" if version_enabled else "id, email, role, tenant_id"

        async with tenant_db_context(tenant_id):
            async with get_conn() as conn:
                current = await conn.fetchrow(
                    _q(
                        f"SELECT {columns} FROM users "
                        "WHERE id=%s AND tenant_id=%s AND is_active=TRUE"
                    ),
                    int(subject),
                    tenant_id,
                )
    except Exception:
        log.exception("refresh_membership_lookup_failed")
        return None

    if not current:
        return None
    if (
        str(current["id"]) != subject
        or current["tenant_id"] != tenant_id
        or current["role"] != role
        or not isinstance(current["email"], str)
        or current["email"].casefold() != email.casefold()
        or (version_enabled and current["auth_version"] != claim_version)
    ):
        return None

    user = {
        "id": current["id"],
        "email": current["email"],
        "role": current["role"],
        "tenant_id": current["tenant_id"],
    }
    if version_enabled:
        user["auth_version"] = current["auth_version"]
    return {
        "access_token": _create_access_token(user),
        "refresh_token": _create_refresh_token(user),
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_HOURS * 3600,
    }


def check_permission(token: str, action: str) -> bool:
    payload = verify_token(token, expected_type="access")
    if not payload:
        return False
    return has_permission(payload.get("role", ""), action)
