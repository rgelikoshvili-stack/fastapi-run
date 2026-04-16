from fastapi import APIRouter, Header
from pydantic import BaseModel
from typing import Optional

from app.api.models.user import create_user, create_users_table
from app.api.services.auth_service import login, verify_token, refresh_token
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str
    tenant_id: str = "default"


class RegisterRequest(BaseModel):
    email: str
    password: str
    tenant_id: str = "default"
    role: str = "accountant"


class RefreshRequest(BaseModel):
    refresh_token: str


def _extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    if not authorization.lower().startswith("bearer "):
        return None
    return authorization.split(" ", 1)[1].strip()


@router.post("/login")
def auth_login(data: LoginRequest):
    result = login(data.email, data.password, data.tenant_id)
    if not result.get("ok"):
        return error_response("Login failed", "AUTH_ERROR", result.get("error"))
    return ok_response("Login successful", result)


@router.post("/register")
def auth_register(data: RegisterRequest):
    try:
        create_users_table()
        user = create_user(data.email, data.password, data.tenant_id, data.role)
        if not user:
            return error_response("User exists", "USER_EXISTS", "ეს email უკვე რეგისტრირებულია")
        return ok_response("Registered", {
            "email": user["email"],
            "role": user["role"],
            "tenant_id": user["tenant_id"],
        })
    except Exception as e:
        return error_response("Register failed", "REGISTER_ERROR", str(e))


@router.get("/me")
def auth_me(authorization: Optional[str] = Header(None)):
    token = _extract_bearer_token(authorization)
    if not token:
        return error_response("Unauthorized", "AUTH_ERROR", "Missing bearer token")

    payload = verify_token(token, expected_type="access")
    if not payload:
        return error_response("Unauthorized", "AUTH_ERROR", "Invalid token")

    return ok_response("User info", {
        "user_id": payload.get("sub"),
        "email": payload.get("email"),
        "role": payload.get("role"),
        "tenant_id": payload.get("tenant_id"),
        "token_type": payload.get("type"),
        "exp": payload.get("exp"),
    })


@router.post("/refresh")
def auth_refresh(data: RefreshRequest):
    refreshed = refresh_token(data.refresh_token)
    if not refreshed:
        return error_response("Refresh failed", "AUTH_ERROR", "Invalid refresh token")
    return ok_response("Token refreshed", refreshed)