from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
from app.errors import err
from app.models import SessionRow

COOKIE = "__Host-session"
PUBLIC_PATHS = {"/api/v1/health", "/api/v1/session", "/health"}
_HITS: dict[str, list[float]] = defaultdict(list)


def allow(key: str, limit: int, window: float) -> bool:
    now = time.monotonic()
    rows = [stamp for stamp in _HITS[key] if now - stamp < window]
    if len(rows) >= limit:
        _HITS[key] = rows
        return False
    rows.append(now)
    _HITS[key] = rows
    return True


def read_token_hash() -> str:
    settings = get_settings()
    path = Path(settings.token_hash_file)
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return settings.app_token_hash.strip()


def login(db: Session, token: str, user_agent: str | None, client: str) -> str:
    digest = hashlib.sha256(token.encode()).hexdigest()
    configured = read_token_hash()
    expected = configured or hashlib.sha256(b"unset-token").hexdigest()
    ok = hmac.compare_digest(digest, expected) and bool(configured)
    if not ok:
        if not allow(f"login-fail:{client}", 8, 600):
            err(429, "rate_limited", "Muitas tentativas")
        if get_settings().app_env != "test":
            time.sleep(0.05)
        err(401, "bad_token", "Token inválido")
    raw = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.add(
        SessionRow(
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            user_agent=(user_agent or "")[:300] or None,
            last_seen_at=now,
            expires_at=now + timedelta(days=90),
        )
    )
    db.flush()
    return raw


def logout(db: Session, raw: str | None) -> None:
    if not raw:
        return
    digest = hashlib.sha256(raw.encode()).hexdigest()
    db.execute(delete(SessionRow).where(SessionRow.token_hash == digest))


def require_session(request: Request, db: Session) -> SessionRow:
    raw = request.cookies.get(COOKIE)
    if not raw:
        err(401, "session_required", "Sessão obrigatória")
    digest = hashlib.sha256(raw.encode()).hexdigest()
    row = db.scalar(select(SessionRow).where(SessionRow.token_hash == digest))
    if row is None:
        err(401, "bad_token", "Sessão inválida")
    now = datetime.now(timezone.utc)
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if expires < now:
        err(401, "session_expired", "Sessão expirada")
    row.last_seen_at = now
    row.expires_at = now + timedelta(days=90)
    return row


def invalidate_all(db: Session) -> None:
    db.execute(delete(SessionRow))


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "")
        hostname = host.split(":")[0].lower().strip("[]")
        settings = get_settings()
        extra = {item.strip().lower() for item in settings.extra_hosts.split(",") if item.strip()}
        allowed = hostname in {"localhost", "127.0.0.1", *extra} or hostname.endswith(".ts.net")
        if settings.app_env != "prod" and hostname == "testserver":
            allowed = True
        if not allowed:
            return JSONResponse(
                status_code=400,
                content={"detail": "Host não permitido", "code": "host_not_allowed"},
            )
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            body = await request.body()
            limit = 20 * 1024 * 1024 if request.url.path == "/api/v1/restore" else 204800
            if len(body) > limit:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Corpo grande demais", "code": "payload_too_large"},
                )
            media = request.headers.get("content-type", "")
            if not media.startswith("application/json"):
                return JSONResponse(
                    status_code=415,
                    content={"detail": "Use application/json", "code": "unsupported_media_type"},
                )
            if request.headers.get("x-app") != "wh40k":
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Cabeçalho X-App ausente", "code": "csrf_header_missing"},
                )
        path = request.url.path.rstrip("/") or "/"
        if path.startswith("/api/") and path not in PUBLIC_PATHS and COOKIE not in request.cookies:
            return JSONResponse(
                status_code=401,
                content={"detail": "Sessão obrigatória", "code": "session_required"},
            )
        return await call_next(request)
