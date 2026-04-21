import logging
import json
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, Literal

from app.api.models.user import create_user, create_users_table, get_user, hash_password
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
                tenant_id, name, company_inn, company_name_legal,
                company_name_aliases, company_type, is_vat_payer,
                subscription_tier, trial_ends_at, status,
                is_active, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, NOW())
            ON CONFLICT DO NOTHING
            """,
            (
                tenant_id, name, inn, name,
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
def auth_register(data: RegisterRequest):
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
def auth_signup(data: FullRegisterRequest):
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
