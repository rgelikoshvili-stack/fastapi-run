"""app/api/routes_2fa.py — Two-Factor Authentication (TOTP / Google Authenticator)."""
import base64
from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel

from app.api.authz import require_auth
from app.api.db import get_db
from app.api.response_utils import ok_response, http_error
from app.api.services.totp_service import (
    generate_totp_secret, generate_qr_png, verify_totp,
    enable_2fa, disable_2fa, get_user_totp,
)
import logging

router = APIRouter(prefix="/auth/2fa", tags=["2fa"])
log = logging.getLogger(__name__)


class TOTPVerifyRequest(BaseModel):
    code: str


class TOTPEnableRequest(BaseModel):
    code: str   # must verify before enabling


@router.post("/setup")
def setup_2fa(request: Request):
    """Step 1 — generate secret + QR code. User scans with Authenticator app."""
    require_auth(request)
    user_id = getattr(request.state, "user_id", None)
    email = getattr(request.state, "email", "user")
    if not user_id:
        return http_error(401, "Not authenticated", "UNAUTHORIZED")

    secret = generate_totp_secret()
    qr_bytes = generate_qr_png(secret, email)
    qr_b64 = base64.b64encode(qr_bytes).decode()

    # Store secret temporarily (not yet enabled — user must verify first)
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            ALTER TABLE users
                ADD COLUMN IF NOT EXISTS totp_secret TEXT,
                ADD COLUMN IF NOT EXISTS totp_enabled BOOLEAN DEFAULT FALSE
        """)
        cur.execute(
            "UPDATE users SET totp_secret = %s, totp_enabled = FALSE WHERE id = %s",
            (secret, user_id),
        )
        conn.commit()
    finally:
        cur.close(); conn.close()

    return ok_response("2FA setup initiated — scan QR code then call /auth/2fa/enable", {
        "secret": secret,
        "qr_code_base64": qr_b64,
        "qr_data_uri": f"data:image/png;base64,{qr_b64}",
        "instructions": "Scan QR code in Google Authenticator, then POST /auth/2fa/enable with your 6-digit code",
    })


@router.get("/qr.png")
def get_qr_image(request: Request):
    """Return QR code as PNG image directly."""
    require_auth(request)
    user_id = getattr(request.state, "user_id", None)
    email = getattr(request.state, "email", "user")
    if not user_id:
        return http_error(401, "Not authenticated", "UNAUTHORIZED")

    conn = get_db()
    totp_info = get_user_totp(conn, user_id)
    conn.close()

    if not totp_info.get("secret"):
        return http_error(404, "No 2FA setup found. Call /auth/2fa/setup first.", "NOT_FOUND")

    png = generate_qr_png(totp_info["secret"], email)
    return Response(content=png, media_type="image/png")


@router.post("/enable")
def enable_2fa_endpoint(body: TOTPEnableRequest, request: Request):
    """Step 2 — verify code from Authenticator app → activate 2FA."""
    require_auth(request)
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return http_error(401, "Not authenticated", "UNAUTHORIZED")

    conn = get_db()
    totp_info = get_user_totp(conn, user_id)

    if not totp_info.get("secret"):
        conn.close()
        return http_error(400, "Run /auth/2fa/setup first", "SETUP_REQUIRED")

    if not verify_totp(totp_info["secret"], body.code):
        conn.close()
        return http_error(400, "Invalid TOTP code", "INVALID_CODE")

    enable_2fa(conn, user_id, totp_info["secret"])
    conn.commit()
    conn.close()

    return ok_response("2FA enabled successfully", {"enabled": True})


@router.post("/disable")
def disable_2fa_endpoint(body: TOTPVerifyRequest, request: Request):
    """Disable 2FA — requires current valid code to confirm."""
    require_auth(request)
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return http_error(401, "Not authenticated", "UNAUTHORIZED")

    conn = get_db()
    totp_info = get_user_totp(conn, user_id)

    if not totp_info.get("enabled"):
        conn.close()
        return http_error(400, "2FA is not enabled", "NOT_ENABLED")

    if not verify_totp(totp_info["secret"], body.code):
        conn.close()
        return http_error(400, "Invalid TOTP code", "INVALID_CODE")

    disable_2fa(conn, user_id)
    conn.commit()
    conn.close()

    return ok_response("2FA disabled", {"enabled": False})


@router.post("/verify")
def verify_2fa_code(body: TOTPVerifyRequest, request: Request):
    """Verify a TOTP code — used during login flow when 2FA is enabled."""
    require_auth(request)
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return http_error(401, "Not authenticated", "UNAUTHORIZED")

    conn = get_db()
    totp_info = get_user_totp(conn, user_id)
    conn.close()

    if not totp_info.get("enabled"):
        return ok_response("2FA not enabled for this user", {"valid": True, "required": False})

    valid = verify_totp(totp_info["secret"], body.code)
    if not valid:
        return http_error(401, "Invalid or expired TOTP code", "INVALID_CODE")

    return ok_response("Code verified", {"valid": True, "required": True})


@router.get("/status")
def get_2fa_status(request: Request):
    """Check if 2FA is enabled for current user."""
    require_auth(request)
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return http_error(401, "Not authenticated", "UNAUTHORIZED")

    conn = get_db()
    totp_info = get_user_totp(conn, user_id)
    conn.close()

    return ok_response("2FA status", {"enabled": totp_info.get("enabled", False)})
