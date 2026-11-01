import logging
import json
import base64
import binascii
import secrets
import hashlib
from html import escape as html_escape
from urllib.parse import urlencode, urlsplit, urlunsplit
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, Literal

from app.api.models.user import create_user, create_users_table, get_user, hash_password, verify_password
from app.api.services.auth_service import ACCESS_TOKEN_EXPIRE_HOURS, login, verify_token, refresh_token, create_access_token, create_refresh_token, jwt_session_version_enabled
from app.api.response_utils import ok_response, error_response, http_error
from app.api.security import limiter
from app.api.client_ip import client_ip_for_rate_limit
from app.api.db import get_conn, _q, tenant_db_context
from app.api.tenant_context import resolve_tenant_id
from app.api.authz import require_permission, require_signed_tenant_permission
from app.api.observability import structured_log

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)


# ── Request models ───────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str
    tenant_id: str = "default"


class RegisterRequest(BaseModel):
    email: str
    password: str
    tenant_id: str = "default"


class FullRegisterRequest(BaseModel):
    """Full SaaS registration — creates tenant + user in one step."""
    company_type: Literal["legal_entity", "individual_entrepreneur", "individual"]
    company_inn: str
    company_name_legal: str
    is_vat_payer: bool = True
    email: str
    password: str

    @field_validator("company_inn")
    @classmethod
    def validate_inn(cls, v, info):
        v = v.strip()
        if not v.isdigit():
            raise ValueError("ID უნდა შეიცავდეს მხოლოდ ციფრებს")
        company_type = info.data.get("company_type")
        if company_type == "legal_entity" and len(v) != 9:
            raise ValueError("იურ. პირის ID — 9 ციფრი")
        elif company_type in ("individual_entrepreneur", "individual") and len(v) != 11:
            raise ValueError("ფიზ. პირის/ი/ე ID — 11 ციფრი")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("პაროლი — მინიმუმ 8 სიმბოლო")
        return v


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: str
    tenant_id: str = "default"


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v):
        if len(v) < 8:
            raise ValueError("პაროლი — მინიმუმ 8 სიმბოლო")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v):
        if len(v) < 8:
            raise ValueError("პაროლი — მინიმუმ 8 სიმბოლო")
        return v


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    if not authorization.lower().startswith("bearer "):
        return None
    return authorization.split(" ", 1)[1].strip()


def _generate_name_aliases(legal_name: str) -> list:
    aliases = {legal_name}
    prefixes = ["შპს ", "სს ", "ა/ა ", "ფასდ ", "LLC ", "JSC "]
    clean = legal_name
    for prefix in prefixes:
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
            aliases.add(clean)
            break
    if clean and len(clean.split()) > 1:
        aliases.add(clean.split()[0])
    return list(aliases)


_CREATE_RESET_TOKENS = """
    CREATE TABLE IF NOT EXISTS password_reset_tokens (
        id SERIAL PRIMARY KEY,
        token VARCHAR(128) UNIQUE NOT NULL,
        email VARCHAR(255) NOT NULL,
        tenant_id VARCHAR(100) NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        used BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT NOW()
    )
"""


_RESET_REQUESTED_MESSAGE = "თუ ეს email რეგისტრირებულია, reset ლინკი გაიგზავნება"


def _reset_token_storage_key(raw_token: str) -> str:
    """Store newly issued high-entropy reset tokens by digest, not in cleartext.

    The existing VARCHAR(128) token column can hold the 71-character key;
    outstanding legacy cleartext token rows remain valid until their expiry.
    """
    return "sha256:" + hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _reset_token_lookup_keys(presented_token: str) -> list[str]:
    """The stored digest must NEVER be accepted as a bearer reset token.

    Only legacy URL-safe cleartext tokens can use the raw-value fallback.
    A stored sha256:<hex> value must require its unknown preimage.
    """
    keys = [_reset_token_storage_key(presented_token)]
    if not presented_token.startswith("sha256:"):
        keys.append(presented_token)
    return keys


def _trusted_password_reset_base_url() -> str:
    """Never derive an emailed recovery link from untrusted Host/X-Forwarded-*."""
    configured = (
        os.environ.get("PASSWORD_RESET_BASE_URL")
        or os.environ.get("APP_BASE_URL")
        or ""
    ).strip()
    if (
        not configured
        or any(c.isspace() or ord(c) < 32 for c in configured)
        or "\\" in configured
    ):
        raise ValueError("trusted reset URL is not configured")
    parsed = urlsplit(configured)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or not parsed.netloc.isascii()
        or "%" in parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid trusted reset URL")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid trusted reset URL port") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("invalid trusted reset URL port")
    if parsed.scheme == "http" and not (
        os.environ.get("TEST_MODE") == "1"
        and parsed.hostname in {"localhost", "127.0.0.1"}
    ):
        raise ValueError("trusted reset URL must use HTTPS")
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _send_reset_email(to_email: str, reset_link: str):
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    if not smtp_user or not smtp_pass:
        log.warning("SMTP not configured — reset link not sent")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Bridge Hub — პაროლის აღდგენა"
    msg["From"] = smtp_user
    msg["To"] = to_email

    html = f"""
    <div style="font-family:Georgia,serif;max-width:480px;margin:40px auto;background:#f3ecdc;padding:32px;border-radius:8px">
      <h2 style="color:#8c3c2d;margin:0 0 8px">Bridge Hub</h2>
      <p style="color:#4a3728;margin:0 0 24px">პაროლის აღდგენის მოთხოვნა მიღებულია.</p>
      <a href="{html_escape(reset_link, quote=True)}"
         style="display:inline-block;background:#8c3c2d;color:#fff;padding:12px 24px;border-radius:4px;text-decoration:none;font-size:15px">
        პაროლის შეცვლა
      </a>
      <p style="color:#888;font-size:13px;margin-top:24px">ლინკი მოქმედია 1 საათის განმავლობაში.<br>თუ თქვენ არ მოგითხოვიათ — უგულებელყავით ეს წერილი.</p>
    </div>
    """
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, to_email, msg.as_string())
        log.info("action=reset_email_sent")
    except Exception as e:
        log.error("action=reset_email_error error_type=%s", type(e).__name__)


async def _tenant_exists_by_inn(inn: str) -> bool:
    async with get_conn() as conn:
        row = await conn.fetchrow(_q("SELECT 1 FROM tenants WHERE company_inn = %s LIMIT 1"), inn)
        return row is not None


async def _create_tenant(tenant_id: str, inn: str, name: str, company_type: str, is_vat_payer: bool) -> None:
    aliases = json.dumps(_generate_name_aliases(name))
    async with get_conn() as conn:
        await conn.execute(_q("""
            INSERT INTO tenants (
                tenant_id, name, slug, company_inn, company_name_legal,
                company_name_aliases, company_type, is_vat_payer,
                subscription_tier, trial_ends_at, status,
                is_active, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, NOW())
            ON CONFLICT DO NOTHING
        """),
            tenant_id, name, tenant_id, inn, name,
            aliases, company_type, is_vat_payer,
            "trial", datetime.utcnow() + timedelta(days=14),
            "active",
        )


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/login")
@limiter.limit("5/minute")
async def auth_login(request: Request, data: LoginRequest):
    # Do not log client-selected X-Forwarded-For or a raw personal IP.
    # Use the same trusted socket-peer policy as both rate limiters.
    ip_fingerprint = hashlib.sha256(
        client_ip_for_rate_limit(request).encode("utf-8")
    ).hexdigest()[:12]
    log.info("action=login_attempt email=%s tenant=%s ip_hash=%s",
             data.email, data.tenant_id, ip_fingerprint)
    result = await login(data.email, data.password, data.tenant_id)
    if not result.get("ok"):
        log.warning("action=login_fail email=%s tenant=%s reason=%s",
                    data.email, data.tenant_id, result.get("error"))
        return error_response("Login failed", "AUTH_ERROR", result.get("error"))
    user = result.get("user", {})
    log.info("action=login_success email=%s tenant=%s user_id=%s role=%s",
             data.email, data.tenant_id, user.get("id"), user.get("role"))
    return ok_response("Login successful", result)


@router.post("/register")
@limiter.limit("5/minute")
async def auth_register(data: RegisterRequest, request: Request):
    """Deny public tenant joins; this endpoint has no verified grant mechanism."""
    structured_log(
        log,
        logging.WARNING,
        "public_tenant_registration_denied",
        result="denied",
        reason="explicit_tenant_grant_required",
    )
    return http_error(
        403,
        "Registration is not available for an existing tenant",
        "TENANT_MEMBERSHIP_FORBIDDEN",
    )


@router.post("/signup")
@limiter.limit("3/minute")
async def auth_signup(data: FullRegisterRequest, request: Request):
    """Full SaaS signup: creates new tenant + admin user. Returns JWT immediately."""
    try:
        if await _tenant_exists_by_inn(data.company_inn):
            return error_response(
                "INN already registered",
                "INN_EXISTS",
                "ამ საიდენტიფიკაციო ნომრით კომპანია უკვე დარეგისტრირებულია",
            )

        async with get_conn() as conn:
            row = await conn.fetchrow(_q("SELECT 1 FROM users WHERE email = %s LIMIT 1"), data.email)
        if row:
            return error_response("Email taken", "EMAIL_EXISTS", "ეს email უკვე გამოყენებულია")

        tenant_id = f"t_{secrets.token_urlsafe(8)}"
        await _create_tenant(tenant_id, data.company_inn, data.company_name_legal, data.company_type, data.is_vat_payer)

        await create_users_table()
        user = await create_user(data.email, data.password, tenant_id, "admin")
        if not user:
            return error_response("User creation failed", "REGISTER_ERROR", "მომხმარებლის შექმნა ვერ მოხერხდა")

        token_payload = {
            "sub": str(user["id"]),
            "tenant_id": tenant_id,
            "role": "admin",
            "email": data.email,
        }
        if jwt_session_version_enabled():
            token_payload["auth_version"] = user["auth_version"]
        access = create_access_token(token_payload)
        refresh = create_refresh_token(token_payload)

        log.info("action=signup_success email=%s tenant=%s inn=%s", data.email, tenant_id, data.company_inn)

        return ok_response("Signup successful", {
            "tenant_id": tenant_id,
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_HOURS * 3600,
            "trial_days_left": 14,
            "user": {
                "id": user["id"],
                "email": data.email,
                "role": "admin",
                "company_name": data.company_name_legal,
                "company_inn": data.company_inn,
            },
        })

    except Exception as e:
        log.error("action=signup_error: %s", e)
        return error_response("Signup failed", "SIGNUP_ERROR", str(e))


@router.get("/me")
async def auth_me(authorization: Optional[str] = Header(None)):
    token = _extract_bearer_token(authorization)
    if not token:
        return http_error(401, "Unauthorized", "AUTH_ERROR", "Missing bearer token")

    payload = verify_token(token, expected_type="access")
    if not payload:
        return http_error(401, "Unauthorized", "AUTH_ERROR", "Invalid token")

    tenant_id = payload.get("tenant_id")
    company_name = None
    company_inn = None
    subscription_tier = None

    if tenant_id:
        try:
            async with get_conn() as conn:
                row = await conn.fetchrow(_q(
                    "SELECT company_name_legal, company_inn, subscription_tier FROM tenants WHERE tenant_id = %s"
                ), tenant_id)
            if row:
                company_name = row["company_name_legal"]
                company_inn = row["company_inn"]
                subscription_tier = row["subscription_tier"]
        except Exception as e:
            log.warning("unexpected error: %s", e)

    return ok_response("User info", {
        "user_id": payload.get("sub"),
        "email": payload.get("email"),
        "role": payload.get("role"),
        "tenant_id": tenant_id,
        "company_name": company_name,
        "company_inn": company_inn,
        "subscription_tier": subscription_tier,
        "token_type": payload.get("type"),
        "exp": payload.get("exp"),
    })


@router.post("/refresh")
async def auth_refresh(data: RefreshRequest):
    refreshed = await refresh_token(data.refresh_token)
    if not refreshed:
        return error_response("Refresh failed", "AUTH_ERROR", "Invalid refresh token")
    return ok_response("Token refreshed", refreshed)


@router.post("/forgot-password")
@limiter.limit("3/minute")
async def auth_forgot_password(data: ForgotPasswordRequest, request: Request):
    """Generate a reset token and send email. Always returns ok (security — don't leak email existence)."""
    try:
        # The tenant hint is used only to scope a public credential-recovery
        # lookup; possession of the emailed one-time token is required to reset.
        if (
            isinstance(data.tenant_id, str) and data.tenant_id
            and data.tenant_id == data.tenant_id.strip()
            and data.tenant_id.casefold() != "default"
        ):
            async with tenant_db_context(data.tenant_id):
                user = await get_user(data.email, data.tenant_id)
        else:
            user = await get_user(data.email, data.tenant_id)
        if user:
            try:
                base_url = _trusted_password_reset_base_url()
            except ValueError:
                # Fail closed: never mint/email a link using a request Host.
                # Public responses must not reveal account existence or config.
                log.error("action=forgot_password_origin_not_trusted")
                return ok_response(_RESET_REQUESTED_MESSAGE, {})

            token = secrets.token_urlsafe(48)
            token_key = _reset_token_storage_key(token)
            expires = datetime.utcnow() + timedelta(hours=1)
            async with get_conn() as conn:
                # Migration 016 must create the table before application rollout.
                await conn.execute(_q(
                    "INSERT INTO password_reset_tokens (token, email, tenant_id, expires_at) VALUES (%s, %s, %s, %s)"
                ), token_key, data.email, data.tenant_id, expires)

            query = urlencode({"token": token, "tenant_id": data.tenant_id})
            # New links use URL fragments so raw secrets never reach web-server
            # query logs/referrers. The static page accepts legacy query links.
            reset_link = f"{base_url}/static/reset_password.html#{query}"
            _send_reset_email(data.email, reset_link)
            log.info("action=forgot_password_accepted")

        return ok_response(_RESET_REQUESTED_MESSAGE, {})
    except Exception as exc:
        # Never return database, SMTP, tenant or account details to a public
        # forgot-password caller (account enumeration / SQL error disclosure).
        log.error("action=forgot_password_internal_error error_type=%s", type(exc).__name__)
        return ok_response(_RESET_REQUESTED_MESSAGE, {})


@router.post("/reset-password")
@limiter.limit("5/minute")
async def auth_reset_password(data: ResetPasswordRequest, request: Request):
    """Atomically consume a reset token and rotate the user's session version.

    A concurrent reuse waits for the first transaction's row lock, then
    observes used=TRUE and cannot apply a second password update.
    """
    version_enabled = jwt_session_version_enabled()
    if not 1 <= len(data.token) <= 128:
        return error_response("Invalid token", "INVALID_TOKEN", "ლინკი არასწორია")
    # Hash-first lookup for new tokens; raw fallback ONLY for outstanding
    # legacy links issued before digest storage was introduced.
    candidate_keys = _reset_token_lookup_keys(data.token)
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(_q(
                "SELECT token, email, tenant_id, expires_at, used "
                "FROM password_reset_tokens "
                "WHERE token = ANY(%s::varchar[]) FOR UPDATE"
            ), candidate_keys)
            if not row:
                return error_response("Invalid token", "INVALID_TOKEN", "ლინკი არასწორია")
            if row["used"]:
                return error_response("Token used", "TOKEN_USED", "ეს ლინკი უკვე გამოყენებულია")
            if datetime.utcnow() > row["expires_at"]:
                return error_response("Token expired", "TOKEN_EXPIRED", "ლინკის ვადა გასულია — ახალი მოითხოვეთ")

            email, tenant_id = row["email"], row["tenant_id"]
            # The reset token identifies the tenant after its locked, unexpired
            # row has been verified. Scope this *same* transaction for an
            # unprivileged app role when users has forced tenant RLS.
            # set_config(..., true) is transaction-local, never session-wide.
            if not isinstance(tenant_id, str) or not tenant_id or tenant_id != tenant_id.strip():
                return error_response("Invalid token", "INVALID_TOKEN", "ლინკი არასწორია")
            await conn.execute(
                "SELECT set_config('app.current_tenant_id', $1, true)", tenant_id
            )
            new_hash = hash_password(data.new_password)
            set_clause = (
                "password_hash=%s, auth_version=auth_version+1"
                if version_enabled else "password_hash=%s"
            )
            updated = await conn.fetchrow(_q(
                f"UPDATE users SET {set_clause} "
                "WHERE email=%s AND tenant_id=%s AND is_active=TRUE RETURNING id"
            ), new_hash, email, tenant_id)
            if not updated:
                return error_response("User not found", "NOT_FOUND", "მომხმარებელი ვერ მოიძებნა")

            await conn.execute(_q(
                "UPDATE password_reset_tokens SET used=TRUE WHERE token=%s"
            ), row["token"])

        log.info("action=password_reset_success email=%s tenant=%s", email, tenant_id)
        return ok_response("პაროლი წარმატებით შეიცვალა", {"email": email, "tenant_id": tenant_id})
    except Exception:
        log.exception("action=reset_password_error")
        return error_response("Error", "RESET_ERROR", "Password reset failed")


class CompanyProfileRequest(BaseModel):
    company_inn: Optional[str] = None
    company_name_legal: Optional[str] = None
    company_type: Optional[str] = None
    is_vat_payer: Optional[bool] = None


@router.get("/company-profile")
async def get_company_profile(authorization: Optional[str] = Header(None)):
    """Return the current tenant's company profile (INN, name, type, VAT status)."""
    token = _extract_bearer_token(authorization)
    if not token:
        return error_response("Unauthorized", "AUTH_ERROR", "Missing bearer token")
    payload = verify_token(token, expected_type="access")
    if not payload:
        return error_response("Unauthorized", "AUTH_ERROR", "Invalid token")

    tenant_id = payload.get("tenant_id", "default")
    async with get_conn() as conn:
        row = await conn.fetchrow(_q(
            "SELECT company_inn, company_name_legal, company_type, is_vat_payer FROM tenants WHERE tenant_id = %s"
        ), tenant_id)

    if not row:
        return ok_response("Company profile", {"company_inn": None, "company_name_legal": None,
                                                "company_type": None, "is_vat_payer": True})
    return ok_response("Company profile", {
        "company_inn": row["company_inn"],
        "company_name_legal": row["company_name_legal"],
        "company_type": row["company_type"],
        "is_vat_payer": row["is_vat_payer"],
    })


@router.patch("/company-profile")
async def update_company_profile(data: CompanyProfileRequest, request: Request, authorization: Optional[str] = Header(None)):
    """Update company INN, name, type, and VAT status for the current tenant."""
    require_permission(request, "settings:write")
    token = _extract_bearer_token(authorization)
    if not token:
        return error_response("Unauthorized", "AUTH_ERROR", "Missing bearer token")
    payload = verify_token(token, expected_type="access")
    if not payload:
        return error_response("Unauthorized", "AUTH_ERROR", "Invalid token")

    tenant_id = payload.get("tenant_id", "default")

    fields, params = [], []
    if data.company_inn is not None:
        fields.append("company_inn = %s")
        params.append(data.company_inn.strip())
    if data.company_name_legal is not None:
        import json as _json
        fields.append("company_name_legal = %s")
        fields.append("name = %s")
        fields.append("company_name_aliases = %s")
        params.append(data.company_name_legal.strip())
        params.append(data.company_name_legal.strip())
        params.append(_json.dumps(_generate_name_aliases(data.company_name_legal.strip())))
    if data.company_type is not None:
        fields.append("company_type = %s")
        params.append(data.company_type)
    if data.is_vat_payer is not None:
        fields.append("is_vat_payer = %s")
        params.append(data.is_vat_payer)

    if not fields:
        return error_response("No fields", "VALIDATION_ERROR", "No fields to update")

    params.append(tenant_id)
    async with get_conn() as conn:
        await conn.execute(_q(f"UPDATE tenants SET {', '.join(fields)} WHERE tenant_id = %s"), *params)

    log.info("action=company_profile_updated tenant=%s", tenant_id)
    return ok_response("კომპანიის პროფილი განახლდა", {})


@router.post("/change-password")
@limiter.limit("5/minute")
async def auth_change_password(data: ChangePasswordRequest, request: Request, authorization: Optional[str] = Header(None)):
    """Change password and, when enabled, revoke all old JWTs atomically."""
    token = _extract_bearer_token(authorization)
    if not token:
        return error_response("Unauthorized", "AUTH_ERROR", "Missing bearer token")
    payload = verify_token(token, expected_type="access")
    if not payload:
        return error_response("Unauthorized", "AUTH_ERROR", "Invalid token")

    email = payload.get("email")
    tenant_id = payload.get("tenant_id", "default")
    if jwt_session_version_enabled():
        # Authenticate the exact signed membership and lock the user row
        # before comparing the old password and incrementing auth_version.
        subject = payload.get("sub")
        claim_version = payload.get("auth_version")
        if (
            not isinstance(subject, str) or not subject.isascii()
            or not subject.isdecimal() or not 0 < len(subject) <= 18
            or int(subject) <= 0
            or not isinstance(tenant_id, str) or not tenant_id
            or tenant_id != tenant_id.strip()
            or tenant_id.casefold() == "default"
            or not isinstance(email, str) or not email.strip()
            or type(claim_version) is not int or claim_version < 1
        ):
            return http_error(401, "Invalid session", "AUTH_MEMBERSHIP_REVOKED")
        try:
            async with get_conn() as conn:
                # Signed JWT tenant; transaction-local for direct handler calls
                # and for an unprivileged runtime role with forced user RLS.
                await conn.execute(
                    "SELECT set_config('app.current_tenant_id', $1, true)", tenant_id
                )
                user = await conn.fetchrow(_q(
                    "SELECT id, password_hash, auth_version FROM users "
                    "WHERE id=%s AND email=%s AND tenant_id=%s AND is_active=TRUE FOR UPDATE"
                ), int(subject), email, tenant_id)
                if not user or user["auth_version"] != claim_version:
                    return http_error(401, "Session was revoked", "AUTH_MEMBERSHIP_REVOKED")
                if not verify_password(data.current_password, user["password_hash"]):
                    return error_response("Wrong password", "AUTH_ERROR", "მიმდინარე პაროლი არასწორია")
                new_hash = hash_password(data.new_password)
                await conn.execute(_q(
                    "UPDATE users SET password_hash=%s, auth_version=auth_version+1 "
                    "WHERE id=%s AND tenant_id=%s"
                ), new_hash, int(subject), tenant_id)
        except Exception:
            log.exception("action=change_password_db_failure")
            return http_error(503, "Password service unavailable", "PASSWORD_CHANGE_UNAVAILABLE")
    else:
        # Legacy path remains intact until migration 015 and staging rollout.
        user = await get_user(email, tenant_id)
        if not user:
            return error_response("User not found", "NOT_FOUND", "მომხმარებელი ვერ მოიძებნა")
        if not verify_password(data.current_password, user["password_hash"]):
            return error_response("Wrong password", "AUTH_ERROR", "მიმდინარე პაროლი არასწორია")
        new_hash = hash_password(data.new_password)
        async with get_conn() as conn:
            if (
                isinstance(tenant_id, str) and tenant_id
                and tenant_id == tenant_id.strip()
                and tenant_id.casefold() != "default"
            ):
                await conn.execute(
                    "SELECT set_config('app.current_tenant_id', $1, true)", tenant_id
                )
            await conn.execute(_q(
                "UPDATE users SET password_hash=%s WHERE email=%s AND tenant_id=%s"
            ), new_hash, email, tenant_id)

    log.info("action=change_password_success email=%s tenant=%s", email, tenant_id)
    return ok_response("პაროლი წარმატებით შეიცვალა", {})


_IDENTITY_IMAGE_MIMES = frozenset({"image/png", "image/jpeg", "image/webp"})


def _validated_identity_image(raw: str) -> str:
    """Accept clear ('') or bounded passive raster image data URLs only.

    Do not persist arbitrary HTML/SVG/JS or external URLs as a signature.
    Legacy saved values are still read; the UI separately renders them via
    safe DOM image.src assignment after a type check.
    """
    image = raw.strip()
    if not image:
        return ""
    if len(image) > 2_000_000 or not image.startswith("data:"):
        raise ValueError("invalid image data URL or size")
    try:
        header, encoded = image.split(",", 1)
        mime = header[5:-7]
        if mime not in _IDENTITY_IMAGE_MIMES or not header.endswith(";base64"):
            raise ValueError("unsupported image format")
        payload = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("invalid image encoding") from None
    if not payload or len(payload) > 1_500_000:
        raise ValueError("invalid image size")
    supported = (
        (mime == "image/png" and payload.startswith(b"\x89PNG\r\n\x1a\n"))
        or (mime == "image/jpeg" and payload.startswith(b"\xff\xd8\xff"))
        or (mime == "image/webp" and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP")
    )
    if not supported:
        raise ValueError("invalid image signature")
    return image


class SignatureRequest(BaseModel):
    signature_b64: str  # base64 data URL, e.g. "data:image/png;base64,..."


@router.post("/signature")
@limiter.limit("10/minute")
async def save_signature(data: SignatureRequest, request: Request):
    """Save tenant signature/stamp image (base64)."""
    tenant_id = require_signed_tenant_permission(request, "settings:write")
    try:
        b64 = _validated_identity_image(data.signature_b64)
    except ValueError:
        return http_error(422, "Invalid signature image", "VALIDATION_ERROR")
    async with get_conn() as conn:
        result = await conn.execute(_q(
            "UPDATE tenants SET signature_b64=%s WHERE tenant_id=%s"
        ), b64, tenant_id)
    if result == "UPDATE 0":
        return http_error(404, "Tenant not found", "TENANT_NOT_FOUND")
    return ok_response("ხელმოწერა/ბეჭედი შენახულია", {})


@router.get("/signature")
async def get_signature(request: Request):
    """Return tenant's saved signature image (base64) to authorized settings editors."""
    tenant_id = require_signed_tenant_permission(request, "settings:write")
    async with get_conn() as conn:
        row = await conn.fetchrow(_q("SELECT signature_b64 FROM tenants WHERE tenant_id=%s"), tenant_id)
    return ok_response("OK", {"signature_b64": row["signature_b64"] if row else None})


class StampRequest(BaseModel):
    stamp_b64: str


@router.post("/stamp")
@limiter.limit("10/minute")
async def save_stamp(data: StampRequest, request: Request):
    """Save tenant stamp image (base64)."""
    tenant_id = require_signed_tenant_permission(request, "settings:write")
    try:
        b64 = _validated_identity_image(data.stamp_b64)
    except ValueError:
        return http_error(422, "Invalid stamp image", "VALIDATION_ERROR")
    async with get_conn() as conn:
        result = await conn.execute(_q(
            "UPDATE tenants SET stamp_b64=%s WHERE tenant_id=%s"
        ), b64, tenant_id)
    if result == "UPDATE 0":
        return http_error(404, "Tenant not found", "TENANT_NOT_FOUND")
    return ok_response("ბეჭედი შენახულია", {})


@router.get("/stamp")
async def get_stamp(request: Request):
    """Return tenant's saved stamp image (base64) to authorized settings editors."""
    tenant_id = require_signed_tenant_permission(request, "settings:write")
    async with get_conn() as conn:
        row = await conn.fetchrow(_q("SELECT stamp_b64 FROM tenants WHERE tenant_id=%s"), tenant_id)
    return ok_response("OK", {"stamp_b64": row["stamp_b64"] if row else None})
