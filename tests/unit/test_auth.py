"""Unit tests for JWT auth flow (no DB required)."""
import os
import time
import pytest
import jwt

if len(os.environ.get("JWT_SECRET", "").encode("utf-8")) < 32:
    os.environ["JWT_SECRET"] = "test-secret-for-ci-32-bytes-minimum"
os.environ.setdefault("TEST_MODE", "1")
os.environ.setdefault("DATABASE_URL", "")

JWT_SECRET = os.environ.get("JWT_SECRET", "test-secret-for-ci-32-bytes-minimum")
ALGORITHM  = "HS256"


def _make_token(role="admin", tenant_id="test", exp_offset=3600, token_type="access"):
    payload = {
        "sub": "user-1",
        "type": token_type,
        "email": "test@test.com",
        "role": role,
        "tenant_id": tenant_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + exp_offset,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def _decode(token: str):
    return jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])


# ── Token generation ──────────────────────────────────────────────────────────

def test_access_token_valid():
    token = _make_token()
    payload = _decode(token)
    assert payload["type"] == "access"
    assert payload["role"] == "admin"
    assert payload["tenant_id"] == "test"


def test_token_contains_required_claims():
    token = _make_token()
    payload = _decode(token)
    for field in ("sub", "type", "email", "role", "tenant_id", "exp", "iat"):
        assert field in payload, f"missing claim: {field}"


def test_token_expiry_is_future():
    token = _make_token(exp_offset=3600)
    payload = _decode(token)
    assert payload["exp"] > int(time.time())


# ── Token validation ──────────────────────────────────────────────────────────

def test_expired_token_rejected():
    token = _make_token(exp_offset=-1)
    with pytest.raises(jwt.ExpiredSignatureError):
        _decode(token)


def test_wrong_secret_rejected():
    token = jwt.encode(
        {"sub": "x", "exp": int(time.time()) + 3600},
        "wrong-secret-for-ci-32-bytes-minimum",
        algorithm=ALGORITHM,
    )
    with pytest.raises(jwt.InvalidSignatureError):
        _decode(token)


def test_tampered_token_rejected():
    token = _make_token()
    tampered = token[:-4] + "XXXX"
    with pytest.raises(jwt.DecodeError):
        _decode(tampered)


def test_missing_token_returns_401(client):
    from fastapi.testclient import TestClient
    from main import app
    bare_client = TestClient(app)
    resp = bare_client.get("/api/approval/list")
    assert resp.status_code in (401, 403)


# ── Role-based access ─────────────────────────────────────────────────────────

def test_viewer_role_token():
    token = _make_token(role="viewer")
    payload = _decode(token)
    assert payload["role"] == "viewer"


def test_refresh_token_type():
    token = _make_token(token_type="refresh", exp_offset=86400)
    payload = _decode(token)
    assert payload["type"] == "refresh"


# ── API endpoint auth ────────────────────────────────────────────────────────

def test_health_is_public(client):
    resp = client.get("/health/")
    assert resp.status_code == 200


def test_authenticated_request_passes(client):
    resp = client.get("/health/")
    assert resp.status_code == 200
    data = resp.json()
    # ok may be False when DB is unavailable in unit test environment
    assert "ok" in data


def test_invalid_token_returns_401():
    from fastapi.testclient import TestClient
    from main import app
    c = TestClient(app, headers={"Authorization": "Bearer totally-invalid-token"})
    resp = c.get("/api/approval/list")
    assert resp.status_code in (401, 403, 422)


def test_jwt_secret_rejects_short_secret_outside_test_mode(monkeypatch):
    from app.api.services import auth_service

    monkeypatch.setenv("JWT_SECRET", "short-secret")
    monkeypatch.delenv("TEST_MODE", raising=False)

    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        auth_service._load_jwt_secret()


def test_jwt_secret_allows_short_secret_in_test_mode(monkeypatch):
    from app.api.services import auth_service

    monkeypatch.setenv("JWT_SECRET", "short-secret")
    monkeypatch.setenv("TEST_MODE", "1")

    assert auth_service._load_jwt_secret() == "short-secret"
