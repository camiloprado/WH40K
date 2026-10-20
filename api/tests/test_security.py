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


def test_dev1_cookie_flags_by_env(monkeypatch):
    monkeypatch.setenv("APP_TOKEN_HASH", "a" * 64)
    get_settings.cache_clear()
    from pathlib import Path

    Path("data").mkdir(exist_ok=True)
    Path("data/app_token_hash").write_text("a" * 64, encoding="utf-8")

    # Login real exige hash do token; aqui só inspecionamos Set-Cookie no fluxo 401→skip.
    # Em vez disso, exercita cookie_name/cookie_secure + open_session com hash batendo.
    import hashlib

    from app.security import cookie_name, cookie_secure

    assert cookie_name("dev") == "session"
    assert cookie_secure("dev") is False
    assert cookie_name("test") == "session"
    assert cookie_secure("test") is False
    assert cookie_name("prod") == "__Host-session"
    assert cookie_secure("prod") is True

    token = "t" * 40
    digest = hashlib.sha256(token.encode()).hexdigest()
    Path("data/app_token_hash").write_text(digest, encoding="utf-8")
    get_settings.cache_clear()

    client = _client("dev")
    response = client.post("/api/v1/session", json={"token": token}, headers={"X-App": "wh40k"})
    assert response.status_code == 200
    header = response.headers.get("set-cookie") or ""
    assert "session=" in header
    assert "__Host-session" not in header
    assert "Secure" not in header

    client_prod = _client("prod")
    # Host permitido em prod nos testes
    response_prod = client_prod.post(
        "/api/v1/session",
        json={"token": token},
        headers={"Host": "127.0.0.1", "X-App": "wh40k"},
    )
    assert response_prod.status_code == 200
    header_prod = response_prod.headers.get("set-cookie") or ""
    assert "__Host-session=" in header_prod
    assert "Secure" in header_prod


def test_rejects_other_tailnet_host():
    client = _client("prod")
    os.environ["EXTRA_HOSTS"] = "pc.tailnet.ts.net"
    get_settings.cache_clear()
    client = _client("prod")
    response = client.get("/api/v1/health", headers={"Host": "other.tailnet.ts.net"})
    assert response.status_code == 400
    assert response.json()["code"] == "host_not_allowed"


def test_accepts_configured_host():
    os.environ["EXTRA_HOSTS"] = "pc.tailnet.ts.net"
    get_settings.cache_clear()
    client = _client("prod")
    response = client.get("/api/v1/health", headers={"Host": "pc.tailnet.ts.net"})
    assert response.status_code == 200
