import os
import sys
import time
from pathlib import Path

os.environ["TEST_MODE"] = "1"

import jwt
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import app

_TEST_JWT_SECRET = os.environ.get("JWT_SECRET", "test")


def _make_test_token(role: str = "admin", tenant_id: str = "test") -> str:
    payload = {
        "sub": "1",
        "type": "access",
        "email": "test@test.com",
        "role": role,
        "tenant_id": tenant_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, _TEST_JWT_SECRET, algorithm="HS256")


@pytest.fixture(scope="session")
def client():
    token = _make_test_token()
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})