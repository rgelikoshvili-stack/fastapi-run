"""app/api/routes_oauth.py — Google / Microsoft SSO, OAuth 2.0 code flow."""
import logging
import os
import secrets
import time
from urllib.parse import urlencode

import requests as _http
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse

from app.api.db import get_db
from app.api.response_utils import ok_response, http_error
from app.api.services.auth_service import create_access_token, create_refresh_token

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/oauth", tags=["auth"])

_STATE_TTL = 600  # seconds
_states: dict[str, tuple[float, str]] = {}  # state → (expiry, tenant_id)

_PROVIDERS = {
    "google": {
        "auth_url":          "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url":         "https://oauth2.googleapis.com/token",
        "userinfo_url":      "https://www.googleapis.com/oauth2/v3/userinfo",
        "scope":             "openid email profile",
        "client_id_env":     "GOOGLE_CLIENT_ID",
        "client_secret_env": "GOOGLE_CLIENT_SECRET",
    },
    "microsoft": {
        "auth_url":          "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url":         "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "userinfo_url":      "https://graph.microsoft.com/v1.0/me",
        "scope":             "openid email profile User.Read",
        "client_id_env":     "MICROSOFT_CLIENT_ID",
        "client_secret_env": "MICROSOFT_CLIENT_SECRET",
    },
}


def _redirect_uri(request: Request, provider: str) -> str:
    base = os.environ.get("APP_BASE_URL", str(request.base_url).rstrip("/"))
    return f"{base}/auth/oauth/{provider}/callback"


def _issue_state(tenant_id: str) -> str:
    state = secrets.token_urlsafe(32)
    _states[state] = (time.time() + _STATE_TTL, tenant_id)
    now = time.time()
    for k in [k for k, v in list(_states.items()) if v[0] < now]:
        _states.pop(k, None)
    return state


def _consume_state(state: str):
    entry = _states.pop(state, None)
    if entry and entry[0] > time.time():
        return entry[1]
    return None


@router.get("/{provider}/login")
def oauth_login(provider: str, request: Request, tenant_id: str = "default"):
    if provider not in _PROVIDERS:
        return http_error(400, f"Unknown provider: {provider}", "INVALID_PROVIDER")
    cfg = _PROVIDERS[provider]
    client_id = os.environ.get(cfg["client_id_env"], "")
    if not client_id:
        return http_error(503, f"{provider} OAuth not configured — set {cfg['client_id_env']}", "OAUTH_NOT_CONFIGURED")

    state = _issue_state(tenant_id)
    params = {
        "client_id": client_id,
        "redirect_uri": _redirect_uri(request, provider),
        "response_type": "code",
        "scope": cfg["scope"],
        "state": state,
    }
    if provider == "google":
        params["prompt"] = "select_account"
    url = cfg["auth_url"] + "?" + urlencode(params)
    return RedirectResponse(url)


@router.get("/{provider}/callback")
def oauth_callback(
    provider: str, request: Request,
    code: str = None, state: str = None, error: str = None,
):
    if error:
        return http_error(400, f"OAuth declined: {error}", "OAUTH_DECLINED")
    if not code or not state:
        return http_error(400, "Missing code or state", "OAUTH_INVALID")
    if provider not in _PROVIDERS:
        return http_error(400, f"Unknown provider: {provider}", "INVALID_PROVIDER")

    tenant_id = _consume_state(state)
    if tenant_id is None:
        return http_error(400, "State expired or already used", "OAUTH_STATE_INVALID")

    cfg = _PROVIDERS[provider]
    client_id = os.environ.get(cfg["client_id_env"], "")
    client_secret = os.environ.get(cfg["client_secret_env"], "")

    try:
        tok = _http.post(cfg["token_url"], data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": _redirect_uri(request, provider),
            "grant_type": "authorization_code",
        }, timeout=10)
        tok.raise_for_status()
        access_token = tok.json().get("access_token")
    except Exception as e:
        log.warning("oauth_token_failed provider=%s: %s", provider, e)
        return http_error(502, "Token exchange failed", "OAUTH_TOKEN_FAILED")

    try:
        ui = _http.get(cfg["userinfo_url"],
                       headers={"Authorization": f"Bearer {access_token}"},
                       timeout=10)
        ui.raise_for_status()
        info = ui.json()
    except Exception as e:
        log.warning("oauth_userinfo_failed provider=%s: %s", provider, e)
        return http_error(502, "User info unavailable", "OAUTH_USERINFO_FAILED")

    email = (info.get("email") or info.get("mail") or "").lower().strip()
    name = info.get("name") or info.get("displayName") or email
    if not email:
        return http_error(400, "Provider did not return email", "OAUTH_NO_EMAIL")

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_provider VARCHAR(32)")
        cur.execute("SELECT id, role FROM users WHERE email=%s AND tenant_id=%s AND is_active=TRUE",
                    (email, tenant_id))
        existing = cur.fetchone()
        if not existing:
            cur.execute("""
                INSERT INTO users (email, password_hash, tenant_id, role, oauth_provider)
                VALUES (%s, %s, %s, 'accountant', %s)
                ON CONFLICT (email, tenant_id) DO UPDATE
                    SET oauth_provider = EXCLUDED.oauth_provider
                RETURNING id, role
            """, (email, secrets.token_hex(32), tenant_id, provider))
            row = cur.fetchone()
            role = row[1] if row else "accountant"
        else:
            role = existing[1]
        conn.commit()
    except Exception as e:
        conn.rollback()
        log.warning("oauth_user_upsert failed: %s", e)
        return http_error(500, "User persistence failed", "DB_ERROR")
    finally:
        cur.close()
        conn.close()

    jwt_access  = create_access_token({"sub": email, "tenant_id": tenant_id, "role": role or "accountant"})
    jwt_refresh = create_refresh_token({"sub": email, "tenant_id": tenant_id})
    log.info("action=oauth_login provider=%s email=%s tenant=%s", provider, email, tenant_id)

    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<script>
localStorage.setItem('access_token', {repr(jwt_access)});
localStorage.setItem('refresh_token', {repr(jwt_refresh)});
localStorage.setItem('tenant_id', {repr(tenant_id)});
window.location.replace('/');
</script></head>
<body style="font-family:sans-serif;text-align:center;padding:40px">
  <p>Logging in as <strong>{name}</strong>…</p>
</body></html>"""
    return HTMLResponse(html)


@router.get("/providers")
def list_providers():
    configured = [n for n, cfg in _PROVIDERS.items() if os.environ.get(cfg["client_id_env"])]
    return ok_response("OAuth providers", {"configured": configured, "all": list(_PROVIDERS.keys())})
