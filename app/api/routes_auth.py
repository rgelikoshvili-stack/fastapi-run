from fastapi import APIRouter
from pydantic import BaseModel
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
        return ok_response("Registered", {"email": user["email"], "role": user["role"], "tenant_id": user["tenant_id"]})
    except Exception as e:
        return error_response("Register failed", "REGISTER_ERROR", str(e))

@router.get("/me")
def auth_me(token: str = ""):
    payload = verify_token(token)
    if not payload:
        return error_response("Unauthorized", "AUTH_ERROR", "Invalid token")
    return ok_response("User info", payload)

@router.post("/refresh")
def auth_refresh(token: str = ""):
    new_token = refresh_token(token)
    if not new_token:
        return error_response("Refresh failed", "AUTH_ERROR", "Invalid token")
    return ok_response("Token refreshed", {"token": new_token})
