"""Bridge Hub React UI is served from the FastAPI backend under /app."""

from pathlib import Path

from fastapi.testclient import TestClient

from main import app


def test_root_redirects_to_react_app():
    client = TestClient(app)

    response = client.get("/", follow_redirects=False)

    assert response.status_code in {307, 308}
    assert response.headers["location"] == "/app"


def test_react_app_index_served_under_app():
    client = TestClient(app)

    response = client.get("/app")

    assert response.status_code == 200
    assert "Bridge Hub" in response.text
    assert "/app/static/" in response.text


def test_react_app_spa_routes_fall_back_to_index():
    client = TestClient(app)

    response = client.get("/app/dashboard")

    assert response.status_code == 200
    assert "Bridge Hub" in response.text


def test_react_root_assets_are_served_as_files():
    client = TestClient(app)

    response = client.get("/app/manifest.json")

    assert response.status_code == 200
    assert "application/manifest+json" in response.headers["content-type"] or "application/json" in response.headers["content-type"]


def test_react_build_assets_exist():
    index = Path("static/react/index.html")
    static_dir = Path("static/react/static")

    assert index.exists()
    assert static_dir.exists()
