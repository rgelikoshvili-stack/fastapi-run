import os
import sys
from pathlib import Path

# ✅ ეს არის მთავარი — RBAC გამორთვა ტესტებისთვის
os.environ["TEST_MODE"] = "1"

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import app


@pytest.fixture(scope="session")
def client():
    return TestClient(app)