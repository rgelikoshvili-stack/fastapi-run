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
from app.api.services.auth_service import login, verify_token, refresh_token, create_access_token, create_refresh_token
from app.api.response_utils import ok_response, error_response
from app.api.security import limiter
from app.api.db import get_db

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


def _ensure_reset_tokens_table():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id SERIAL PRIMARY KEY,
                token VARCHAR(128) UNIQUE NOT NULL,
                email VARCHAR(255) NOT NULL,
                tenant_id VARCHAR(100) NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()
    finally:
        cur.close()
        conn.close()


def _send_reset_email(to_email: str, reset_link: str):
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    if not smtp_user or not smtp_pass:
        log.warning("SMTP not configured — reset link: %s", reset_link)
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


def _tenant_exists_by_inn(inn: str) -> bool:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM tenants WHERE company_inn = %s LIMIT 1", (inn,))
        return cur.fetchone() is not None
    finally:
        cur.close()
        conn.close()


def _create_tenant(tenant_id: str, inn: str, name: str, company_type: str, is_vat_payer: bool) -> None:
    conn = get_db()
    try:
        aliases = json.dumps(_generate_name_aliases(name))
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tenants (
                tenant_id, name, slug, company_inn, company_name_legal,
                company_name_aliases, company_type, is_vat_payer,
                subscription_tier, trial_ends_at, status,
                is_active, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, NOW())
            ON CONFLICT DO NOTHING
            """,
            (
                tenant_id, name, tenant_id, inn, name,
                aliases, company_type, is_vat_payer,
                "trial", datetime.utcnow() + timedelta(days=14),
                "active",
            ),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/login")
@limiter.limit("5/minute")
def auth_login(request: Request, data: LoginRequest):
    log.info("action=login_attempt email=%s tenant=%s ip=%s",
             data.email, data.tenant_id,
             request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown"))
    result = login(data.email, data.password, data.tenant_id)
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
def auth_register(data: RegisterRequest, request: Request):
    """Simple register (existing tenant). For new company signup use /auth/signup."""
    try:
        create_users_table()
        user = create_user(data.email, data.password, data.tenant_id, "accountant")
        if not user:
            return error_response("User exists", "USER_EXISTS", "ეს email უკვე რეგისტრირებულია")
        return ok_response("Registered", {
            "email": user["email"],
            "role": user["role"],
            "tenant_id": user["tenant_id"],
        })
    except Exception as e:
        return error_response("Register failed", "REGISTER_ERROR", str(e))


@router.post("/signup")
@limiter.limit("3/minute")
def auth_signup(data: FullRegisterRequest, request: Request):
    """Full SaaS signup: creates new tenant + admin user. Returns JWT immediately."""
    try:
        if _tenant_exists_by_inn(data.company_inn):
            return error_response(
                "INN already registered",
                "INN_EXISTS",
                "ამ საიდენტიფიკაციო ნომრით კომპანია უკვე დარეგისტრირებულია",
            )

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE email = %s LIMIT 1", (data.email,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return error_response("Email taken", "EMAIL_EXISTS", "ეს email უკვე გამოყენებულია")
        cur.close()
        conn.close()

        tenant_id = f"t_{secrets.token_urlsafe(8)}"
        _create_tenant(tenant_id, data.company_inn, data.company_name_legal, data.company_type, data.is_vat_payer)

        create_users_table()
        user = create_user(data.email, data.password, tenant_id, "admin")
        if not user:
            return error_response("User creation failed", "REGISTER_ERROR", "მომხმარებლის შექმნა ვერ მოხერხდა")

        token_payload = {
            "sub": str(user["id"]),
            "tenant_id": tenant_id,
            "role": "admin",
            "email": data.email,
        }
        access = create_access_token(token_payload)
        refresh = create_refresh_token({"sub": str(user["id"])})

        log.info("action=signup_success email=%s tenant=%s inn=%s", data.email, tenant_id, data.company_inn)

        return ok_response("Signup successful", {
            "tenant_id": tenant_id,
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "bearer",
            "expires_in": 3600,
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
def auth_me(authorization: Optional[str] = Header(None)):
    token = _extract_bearer_token(authorization)
    if not token:
        return error_response("Unauthorized", "AUTH_ERROR", "Missing bearer token")

    payload = verify_token(token, expected_type="access")
    if not payload:
        return error_response("Unauthorized", "AUTH_ERROR", "Invalid token")

    tenant_id = payload.get("tenant_id")
    company_name = None
    company_inn = None
    subscription_tier = None

    if tenant_id:
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "SELECT company_name_legal, company_inn, subscription_tier FROM tenants WHERE tenant_id = %s",
                (tenant_id,),
            )
            row = cur.fetchone()
            if row:
                company_name, company_inn, subscription_tier = row
            cur.close()
            conn.close()
        except Exception:
            pass

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
def auth_refresh(data: RefreshRequest):
    refreshed = refresh_token(data.refresh_token)
    if not refreshed:
        return error_response("Refresh failed", "AUTH_ERROR", "Invalid refresh token")
    return ok_response("Token refreshed", refreshed)


@router.post("/forgot-password")
@limiter.limit("3/minute")
def auth_forgot_password(data: ForgotPasswordRequest, request: Request):
    """Generate a reset token and send email. Always returns ok (security — don't leak email existence)."""
    try:
        _ensure_reset_tokens_table()
        user = get_user(data.email, data.tenant_id)
        if user:
            token = secrets.token_urlsafe(48)
            expires = datetime.utcnow() + timedelta(hours=1)
            conn = get_db()
            try:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO password_reset_tokens (token, email, tenant_id, expires_at) VALUES (%s, %s, %s, %s)",
                    (token, data.email, data.tenant_id, expires)
                )
                conn.commit()
            finally:
                cur.close()
                conn.close()

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
def auth_reset_password(data: ResetPasswordRequest, request: Request):
    """Validate reset token and update password."""
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                """SELECT email, tenant_id, expires_at, used
                   FROM password_reset_tokens
                   WHERE token = %s""",
                (data.token,)
            )
            row = cur.fetchone()
        finally:
            cur.close()
            conn.close()

        if not row:
            return error_response("Invalid token", "INVALID_TOKEN", "ლინკი არასწორია")
        email, tenant_id, expires_at, used = row
        if used:
            return error_response("Token used", "TOKEN_USED", "ეს ლინკი უკვე გამოყენებულია")
        if datetime.utcnow() > expires_at:
            return error_response("Token expired", "TOKEN_EXPIRED", "ლინკის ვადა გასულია — ახალი მოითხოვეთ")

        new_hash = hash_password(data.new_password)
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET password_hash=%s WHERE email=%s AND tenant_id=%s",
                (new_hash, email, tenant_id)
            )
            cur.execute(
                "UPDATE password_reset_tokens SET used=TRUE WHERE token=%s",
                (data.token,)
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()

        log.info("action=password_reset_success email=%s tenant=%s", email, tenant_id)
        return ok_response("პაროლი წარმატებით შეიცვალა", {"email": email, "tenant_id": tenant_id})

    except Exception as e:
        log.error("action=reset_password_error: %s", e)
        return error_response("Error", "RESET_ERROR", str(e))


class CompanyProfileRequest(BaseModel):
    company_inn: Optional[str] = None
    company_name_legal: Optional[str] = None
    company_type: Optional[str] = None
    is_vat_payer: Optional[bool] = None


@router.get("/company-profile")
def get_company_profile(authorization: Optional[str] = Header(None)):
    """Return the current tenant's company profile (INN, name, type, VAT status)."""
    token = _extract_bearer_token(authorization)
    if not token:
        return error_response("Unauthorized", "AUTH_ERROR", "Missing bearer token")
    payload = verify_token(token, expected_type="access")
    if not payload:
        return error_response("Unauthorized", "AUTH_ERROR", "Invalid token")

    tenant_id = payload.get("tenant_id", "default")
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT company_inn, company_name_legal, company_type, is_vat_payer
               FROM tenants WHERE tenant_id = %s""",
            (tenant_id,),
        )
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not row:
        return ok_response("Company profile", {"company_inn": None, "company_name_legal": None,
                                                "company_type": None, "is_vat_payer": True})
    return ok_response("Company profile", {
        "company_inn": row[0],
        "company_name_legal": row[1],
        "company_type": row[2],
        "is_vat_payer": row[3],
    })


@router.patch("/company-profile")
def update_company_profile(data: CompanyProfileRequest, authorization: Optional[str] = Header(None)):
    """Update company INN, name, type, and VAT status for the current tenant."""
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
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE tenants SET {', '.join(fields)} WHERE tenant_id = %s",
            params,
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

    log.info("action=company_profile_updated tenant=%s", tenant_id)
    return ok_response("კომპანიის პროფილი განახლდა", {})


@router.post("/change-password")
@limiter.limit("5/minute")
def auth_change_password(data: ChangePasswordRequest, request: Request, authorization: Optional[str] = Header(None)):
    """Change password for logged-in user."""
    token = _extract_bearer_token(authorization)
    if not token:
        return error_response("Unauthorized", "AUTH_ERROR", "Missing bearer token")
    payload = verify_token(token, expected_type="access")
    if not payload:
        return error_response("Unauthorized", "AUTH_ERROR", "Invalid token")

    email = payload.get("email")
    tenant_id = payload.get("tenant_id", "default")
    user = get_user(email, tenant_id)
    if not user:
        return error_response("User not found", "NOT_FOUND", "მომხმარებელი ვერ მოიძებნა")
    if not verify_password(data.current_password, user["password_hash"]):
        return error_response("Wrong password", "AUTH_ERROR", "მიმდინარე პაროლი არასწორია")

    new_hash = hash_password(data.new_password)
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET password_hash=%s WHERE email=%s AND tenant_id=%s", (new_hash, email, tenant_id))
        conn.commit()
    finally:
        cur.close()
        conn.close()

    log.info("action=change_password_success email=%s tenant=%s", email, tenant_id)
    return ok_response("პაროლი წარმატებით შეიცვალა", {})
