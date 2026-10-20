import os

os.environ.setdefault("APP_ENV", "test")

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def _client(env: str = "test") -> TestClient:
    os.environ["APP_ENV"] = env
    get_settings.cache_clear()
    return TestClient(create_app())


def test_rejects_bad_host():
    client = _client("prod")
    response = client.post(
        "/api/v1/session",
        json={"token": "x" * 40},
        headers={"Host": "evil.example", "X-App": "wh40k"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "host_not_allowed"


def test_requires_json_and_app_header():
    client = _client()
    plain = client.post("/api/v1/session", content="token", headers={"content-type": "text/plain"})
    assert plain.status_code == 415
    assert plain.json()["code"] == "unsupported_media_type"
    missing = client.post("/api/v1/session", json={"token": "x" * 40})
    assert missing.status_code == 403
    assert missing.json()["code"] == "csrf_header_missing"


def test_requires_session_and_hides_docs():
    client = _client()
    response = client.get("/api/v1/lists")
    assert response.status_code == 401
    assert response.json()["code"] == "session_required"
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_payload_too_large():
    client = _client()
    blob = "😀" * 80000
    response = client.post(
        "/api/v1/session",
        content=blob,
        headers={"content-type": "application/json", "X-App": "wh40k"},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"
