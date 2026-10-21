import os

os.environ.setdefault("APP_ENV", "test")

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def _client(monkeypatch, env: str = "test") -> TestClient:
    monkeypatch.setenv("APP_ENV", env)
    get_settings.cache_clear()
    return TestClient(create_app())


def test_rejects_bad_host(monkeypatch):
    client = _client(monkeypatch, "prod")
    response = client.post(
        "/api/v1/session",
        json={"token": "x" * 40},
        headers={"Host": "evil.example", "X-App": "wh40k"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "host_not_allowed"


def test_requires_json_and_app_header(monkeypatch):
    client = _client(monkeypatch)
    plain = client.post("/api/v1/session", content="token", headers={"content-type": "text/plain"})
    assert plain.status_code == 415
    assert plain.json()["code"] == "unsupported_media_type"
    missing = client.post("/api/v1/session", json={"token": "x" * 40})
    assert missing.status_code == 403
    assert missing.json()["code"] == "csrf_header_missing"


def test_requires_session_and_hides_docs(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/api/v1/lists")
    assert response.status_code == 401
    assert response.json()["code"] == "session_required"
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_payload_too_large(monkeypatch):
    client = _client(monkeypatch)
    blob = "😀" * 80000
    response = client.post(
        "/api/v1/session",
        content=blob,
        headers={"content-type": "application/json", "X-App": "wh40k"},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"


def test_dev1_cookie_flags_by_env(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_TOKEN_HASH", "a" * 64)
    get_settings.cache_clear()
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
    hash_file = tmp_path / "h"
    hash_file.write_text(digest, encoding="utf-8")
    monkeypatch.setenv("TOKEN_HASH_FILE", str(hash_file))
    get_settings.cache_clear()

    try:
        client = _client(monkeypatch, "dev")
        response = client.post("/api/v1/session", json={"token": token}, headers={"X-App": "wh40k"})
        assert response.status_code == 200
        header = response.headers.get("set-cookie") or ""
        assert "session=" in header
        assert "__Host-session" not in header
        assert "Secure" not in header

        client_prod = _client(monkeypatch, "prod")
        response_prod = client_prod.post(
            "/api/v1/session",
            json={"token": token},
            headers={"Host": "127.0.0.1", "X-App": "wh40k"},
        )
        assert response_prod.status_code == 200
        header_prod = response_prod.headers.get("set-cookie") or ""
        assert "__Host-session=" in header_prod
        assert "Secure" in header_prod
    finally:
        get_settings.cache_clear()


def test_rejects_other_tailnet_host(monkeypatch):
    prev = os.environ.get("EXTRA_HOSTS")
    try:
        os.environ["EXTRA_HOSTS"] = "pc.tailnet.ts.net"
        get_settings.cache_clear()
        client = _client(monkeypatch, "prod")
        response = client.get("/api/v1/health", headers={"Host": "other.tailnet.ts.net"})
        assert response.status_code == 400
        assert response.json()["code"] == "host_not_allowed"
    finally:
        if prev is None:
            os.environ.pop("EXTRA_HOSTS", None)
        else:
            os.environ["EXTRA_HOSTS"] = prev
        get_settings.cache_clear()


def test_accepts_configured_host(monkeypatch):
    prev = os.environ.get("EXTRA_HOSTS")
    try:
        os.environ["EXTRA_HOSTS"] = "pc.tailnet.ts.net"
        get_settings.cache_clear()
        client = _client(monkeypatch, "prod")
        response = client.get("/api/v1/health", headers={"Host": "pc.tailnet.ts.net"})
        assert response.status_code == 200
    finally:
        if prev is None:
            os.environ.pop("EXTRA_HOSTS", None)
        else:
            os.environ["EXTRA_HOSTS"] = prev
        get_settings.cache_clear()


def test_session_absolute_expiry():
    import hashlib
    from datetime import datetime, timedelta, timezone

    from fastapi import HTTPException
    from starlette.requests import Request

    from app.db import session_factory
    from app.models import SessionRow
    from app.security import require_session

    raw = "absolute-expiry-token"
    db = session_factory()()
    row = SessionRow(
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        created_at=datetime.now(timezone.utc) - timedelta(days=31),
        last_seen_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db.add(row)
    db.commit()
    scope = {"type": "http", "headers": [(b"cookie", f"session={raw}".encode())]}
    request = Request(scope)
    try:
        require_session(request, db)
        raise AssertionError("sessão de 31 dias deveria expirar")
    except HTTPException as exc:
        assert exc.status_code == 401
    finally:
        db.close()


def test_logout_all(monkeypatch):
    client = _client(monkeypatch, "test")
    response = client.delete("/api/v1/session/all", headers={"X-App": "wh40k", "content-type": "application/json"})
    assert response.status_code == 401
