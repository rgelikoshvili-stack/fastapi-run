import os, jwt, secrets
from datetime import datetime, timezone, timedelta
from app.api.models.user import get_user, verify_password, update_last_login, has_permission

SECRET_KEY = os.environ.get("JWT_SECRET", secrets.token_hex(32))
ALGORITHM  = "HS256"
TOKEN_EXPIRE_HOURS = 24


def login(email: str, password: str, tenant_id: str = "default") -> dict:
    user = get_user(email, tenant_id)
    if not user:
        return {"ok": False, "error": "მომხმარებელი ვერ მოიძებნა"}
    if not verify_password(password, user["password_hash"]):
        return {"ok": False, "error": "პაროლი არასწორია"}
    token = _create_token(user)
    update_last_login(user["id"])
    return {
        "ok": True,
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "tenant_id": user["tenant_id"],
        }
    }


def verify_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("exp", 0) < datetime.now(timezone.utc).timestamp():
            return None
        return payload
    except Exception:
        return None


def check_permission(token: str, action: str) -> bool:
    payload = verify_token(token)
    if not payload:
        return False
    return has_permission(payload.get("role", ""), action)


def _create_token(user: dict) -> str:
    payload = {
        "user_id":  user["id"],
        "email":    user["email"],
        "role":     user["role"],
        "tenant_id": user["tenant_id"],
        "exp": (datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)).timestamp(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def refresh_token(token: str) -> str | None:
    payload = verify_token(token)
    if not payload:
        return None
    payload["exp"] = (datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)).timestamp()
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
