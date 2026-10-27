import logging
import json
import secrets
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
from app.api.db import get_conn, _q
from app.api.tenant_context import resolve_tenant_id
from app.api.authz import require_permission
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


def _send_reset_email(to_email: str, reset_link: str):
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    if not smtp_user or not smtp_pass:
        log.warning("SMTP not configured — reset link not sent for email=%s", to_email)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Bridge Hub — პაროლის აღდგენა"
    msg["From"] = smtp_user
    msg["To"] = to_email

    html = f"""
    <div style="font-family:Georgia,serif;max-width:480px;margin:40px auto;background:#f3ecdc;padding:32px;border-radius:8px">
      <h2 style="color:#8c3c2d;margin:0 0 8px">Bridge Hub</h2>
      <p style="color:#4a3728;margin:0 0 24px">პაროლის აღდგენის მოთხოვნა მიღებულია.</p>
      <a href="{reset_link}"
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
        log.info("action=reset_email_sent to=%s", to_email)
    except Exception as e:
        log.error("action=reset_email_error: %s", e)


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
    log.info("action=login_attempt email=%s tenant=%s ip=%s",
             data.email, data.tenant_id,
             request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown"))
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
        user = await get_user(data.email, data.tenant_id)
        if user:
            token = secrets.token_urlsafe(48)
            expires = datetime.utcnow() + timedelta(hours=1)
            async with get_conn() as conn:
                await conn.execute(_CREATE_RESET_TOKENS)
                await conn.execute(_q(
                    "INSERT INTO password_reset_tokens (token, email, tenant_id, expires_at) VALUES (%s, %s, %s, %s)"
                ), token, data.email, data.tenant_id, expires)

            base_url = str(request.base_url).rstrip("/")
            reset_link = f"{base_url}/static/reset_password.html?token={token}&tenant_id={data.tenant_id}"
            _send_reset_email(data.email, reset_link)
            log.info("action=forgot_password email=%s tenant=%s", data.email, data.tenant_id)

        return ok_response("თუ ეს email რეგისტრირებულია, reset ლინკი გაიგზავნება", {})
    except Exception as e:
        log.error("action=forgot_password_error: %s", e)
        return error_response("Error", "RESET_ERROR", str(e))


@router.post("/reset-password")
@limiter.limit("5/minute")
async def auth_reset_password(data: ResetPasswordRequest, request: Request):
    """Atomically consume a reset token and rotate the user's session version.

    A concurrent reuse waits for the first transaction's row lock, then
    observes used=TRUE and cannot apply a second password update.
    """
    version_enabled = jwt_session_version_enabled()
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(_q(
                "SELECT email, tenant_id, expires_at, used "
                "FROM password_reset_tokens WHERE token=%s FOR UPDATE"
            ), data.token)
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
            ), data.token)

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
            await conn.execute(_q(
                "UPDATE users SET password_hash=%s WHERE email=%s AND tenant_id=%s"
            ), new_hash, email, tenant_id)

    log.info("action=change_password_success email=%s tenant=%s", email, tenant_id)
    return ok_response("პაროლი წარმატებით შეიცვალა", {})


class SignatureRequest(BaseModel):
    signature_b64: str  # base64 data URL, e.g. "data:image/png;base64,..."


@router.post("/signature")
@limiter.limit("10/minute")
async def save_signature(data: SignatureRequest, request: Request):
    """Save tenant signature/stamp image (base64)."""
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    b64 = data.signature_b64.strip()
    if len(b64) > 2_000_000:
        return error_response("Image too large (max 1.5 MB)", "VALIDATION_ERROR")
    async with get_conn() as conn:
        await conn.execute(_q("UPDATE tenants SET signature_b64=%s WHERE tenant_id=%s"), b64, tenant_id)
    return ok_response("ხელმოწერა/ბეჭედი შენახულია", {})


@router.get("/signature")
async def get_signature(request: Request):
    """Return tenant's saved signature image (base64) to authorized settings editors."""
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        row = await conn.fetchrow(_q("SELECT signature_b64 FROM tenants WHERE tenant_id=%s"), tenant_id)
    return ok_response("OK", {"signature_b64": row["signature_b64"] if row else None})


class StampRequest(BaseModel):
    stamp_b64: str


@router.post("/stamp")
@limiter.limit("10/minute")
async def save_stamp(data: StampRequest, request: Request):
    """Save tenant stamp image (base64)."""
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    b64 = data.stamp_b64.strip()
    if len(b64) > 2_000_000:
        return error_response("Image too large (max 1.5 MB)", "VALIDATION_ERROR")
    async with get_conn() as conn:
        await conn.execute(_q("UPDATE tenants SET stamp_b64=%s WHERE tenant_id=%s"), b64, tenant_id)
    return ok_response("ბეჭედი შენახულია", {})


@router.get("/stamp")
async def get_stamp(request: Request):
    """Return tenant's saved stamp image (base64) to authorized settings editors."""
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        row = await conn.fetchrow(_q("SELECT stamp_b64 FROM tenants WHERE tenant_id=%s"), tenant_id)
    return ok_response("OK", {"stamp_b64": row["stamp_b64"] if row else None})
