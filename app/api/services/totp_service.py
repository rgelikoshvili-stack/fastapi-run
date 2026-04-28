"""app/api/services/totp_service.py — TOTP 2FA (Google Authenticator compatible)."""
import base64
import io
import logging
import os

import pyotp

log = logging.getLogger(__name__)

APP_NAME = os.environ.get("APP_NAME", "Bridge Hub")


def generate_totp_secret() -> str:
    """Generate a new random TOTP secret (base32)."""
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str) -> str:
    """Build otpauth:// URI for QR code scanning."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=APP_NAME)


def generate_qr_png(secret: str, email: str) -> bytes:
    """Return QR code as PNG bytes."""
    import qrcode
    uri = get_totp_uri(secret, email)
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def verify_totp(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP code. Allows 1 window drift (±30s)."""
    if not secret or not code:
        return False
    totp = pyotp.TOTP(secret)
    return totp.verify(code.strip(), valid_window=1)


# ── DB helpers ────────────────────────────────────────────────────────────────

def enable_2fa(conn, user_id: int, secret: str):
    cur = conn.cursor()
    cur.execute("""
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS totp_secret TEXT,
            ADD COLUMN IF NOT EXISTS totp_enabled BOOLEAN DEFAULT FALSE
    """)
    cur.execute("""
        UPDATE users SET totp_secret = %s, totp_enabled = TRUE
        WHERE id = %s
    """, (secret, user_id))
    cur.close()


def disable_2fa(conn, user_id: int):
    cur = conn.cursor()
    cur.execute("""
        UPDATE users SET totp_secret = NULL, totp_enabled = FALSE
        WHERE id = %s
    """, (user_id,))
    cur.close()


def get_user_totp(conn, user_id: int) -> dict:
    """Return {'enabled': bool, 'secret': str|None}."""
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT totp_enabled, totp_secret FROM users WHERE id = %s
        """, (user_id,))
        row = cur.fetchone()
        if not row:
            return {"enabled": False, "secret": None}
        return {"enabled": bool(row[0]), "secret": row[1]}
    except Exception:
        return {"enabled": False, "secret": None}
    finally:
        cur.close()
