import os
import jwt
from datetime import datetime, timezone, timedelta
from app.api.models.user import get_user, verify_password, update_last_login, has_permission

SECRET_KEY = os.environ.get("JWT_SECRET")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET is not configured")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
REFRESH_TOKEN_EXPIRE_DAYS = 7


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


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
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


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
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(payload_extra: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)).timestamp()),
        **payload_extra,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(payload_extra: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).timestamp()),
        **payload_extra,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def login(email: str, password: str, tenant_id: str = "default") -> dict:
    user = get_user(email, tenant_id)
    if not user:
        return {"ok": False, "error": "მომხმარებელი ვერ მოიძებნა"}

    if not verify_password(password, user["password_hash"]):
        return {"ok": False, "error": "პაროლი არასწორია"}

    access_token = _create_access_token(user)
    refresh_token = _create_refresh_token(user)
    update_last_login(user["id"])

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
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != expected_type:
            return None
        return payload
    except Exception:
        return None


def refresh_token(refresh_token_value: str) -> dict | None:
    payload = verify_token(refresh_token_value, expected_type="refresh")
    if not payload:
        return None

    user = {
        "id": int(payload["sub"]),
        "email": payload["email"],
        "role": payload["role"],
        "tenant_id": payload["tenant_id"],
    }

    new_access_token = _create_access_token(user)
    new_refresh_token = _create_refresh_token(user)

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_HOURS * 3600,
    }


def check_permission(token: str, action: str) -> bool:
    payload = verify_token(token, expected_type="access")
    if not payload:
        return False
    return has_permission(payload.get("role", ""), action)