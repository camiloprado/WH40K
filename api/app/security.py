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

con_strCookie = "__Host-session"
con_setPublicPaths = {"/api/v1/health", "/api/v1/session", "/health"}
con_dctHits: dict[str, list[float]] = defaultdict(list)

# Contrato público do módulo.
COOKIE = con_strCookie
PUBLIC_PATHS = con_setPublicPaths
_HITS = con_dctHits


def allow(key: str, limit: int, window: float) -> bool:
    var_fltNow = time.monotonic()
    var_lstRows = [stamp for stamp in con_dctHits[key] if var_fltNow - stamp < window]
    if len(var_lstRows) >= limit:
        con_dctHits[key] = var_lstRows
        return False
    var_lstRows.append(var_fltNow)
    con_dctHits[key] = var_lstRows
    return True


def read_token_hash() -> str:
    var_objSettings = get_settings()
    var_objPath = Path(var_objSettings.token_hash_file)
    if var_objPath.exists():
        return var_objPath.read_text(encoding="utf-8").strip()
    return var_objSettings.app_token_hash.strip()


def login(db: Session, token: str, user_agent: str | None, client: str) -> str:
    var_strDigest = hashlib.sha256(token.encode()).hexdigest()
    var_strConfigured = read_token_hash()
    var_strExpected = var_strConfigured or hashlib.sha256(b"unset-token").hexdigest()
    var_boolOk = hmac.compare_digest(var_strDigest, var_strExpected) and bool(var_strConfigured)
    if not var_boolOk:
        if not allow(f"login-fail:{client}", 8, 600):
            err(429, "rate_limited", "Muitas tentativas")
        if get_settings().app_env != "test":
            time.sleep(0.05)
        err(401, "bad_token", "Token inválido")
    var_strRaw = secrets.token_urlsafe(32)
    var_objNow = datetime.now(timezone.utc)
    db.add(
        SessionRow(
            token_hash=hashlib.sha256(var_strRaw.encode()).hexdigest(),
            user_agent=(user_agent or "")[:300] or None,
            last_seen_at=var_objNow,
            expires_at=var_objNow + timedelta(days=30),
        )
    )
    db.flush()
    return var_strRaw


def logout(db: Session, raw: str | None) -> None:
    if not raw:
        return
    var_strDigest = hashlib.sha256(raw.encode()).hexdigest()
    db.execute(delete(SessionRow).where(SessionRow.token_hash == var_strDigest))


def require_session(request: Request, db: Session) -> SessionRow:
    var_strRaw = request.cookies.get(con_strCookie)
    if not var_strRaw:
        err(401, "session_required", "Sessão obrigatória")
    var_strDigest = hashlib.sha256(var_strRaw.encode()).hexdigest()
    var_objRow = db.scalar(select(SessionRow).where(SessionRow.token_hash == var_strDigest))
    if var_objRow is None:
        err(401, "bad_token", "Sessão inválida")
    var_objNow = datetime.now(timezone.utc)
    var_objExpires = (
        var_objRow.expires_at
        if var_objRow.expires_at.tzinfo
        else var_objRow.expires_at.replace(tzinfo=timezone.utc)
    )
    if var_objExpires < var_objNow:
        err(401, "session_expired", "Sessão expirada")
    var_objRow.last_seen_at = var_objNow
    var_objRow.expires_at = var_objNow + timedelta(days=30)
    return var_objRow


def invalidate_all(db: Session) -> None:
    db.execute(delete(SessionRow))


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        var_strHost = request.headers.get("host", "")
        var_strHostname = var_strHost.split(":")[0].lower().strip("[]")
        var_objSettings = get_settings()
        var_setExtra = {item.strip().lower() for item in var_objSettings.extra_hosts.split(",") if item.strip()}
        # Só FQDN listados em EXTRA_HOSTS (ex.: pc.tailnet.ts.net). Sem wildcard *.ts.net.
        var_boolAllowed = var_strHostname in {"localhost", "127.0.0.1", *var_setExtra}
        if var_objSettings.app_env != "prod" and var_strHostname == "testserver":
            var_boolAllowed = True
        if not var_boolAllowed:
            return JSONResponse(
                status_code=400,
                content={"detail": "Host não permitido", "code": "host_not_allowed"},
            )
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            var_intLimit = 20 * 1024 * 1024 if request.url.path.endswith("/restore") else 204800
            var_strLen = request.headers.get("content-length")
            if var_strLen is not None:
                try:
                    if int(var_strLen) > var_intLimit:
                        return JSONResponse(
                            status_code=413,
                            content={"detail": "Corpo grande demais", "code": "payload_too_large"},
                        )
                except ValueError:
                    pass
            var_bytBody = await request.body()
            if len(var_bytBody) > var_intLimit:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Corpo grande demais", "code": "payload_too_large"},
                )
            var_strMedia = request.headers.get("content-type", "")
            if not var_strMedia.startswith("application/json"):
                return JSONResponse(
                    status_code=415,
                    content={"detail": "Use application/json", "code": "unsupported_media_type"},
                )
            if request.headers.get("x-app") != "wh40k":
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Cabeçalho X-App ausente", "code": "csrf_header_missing"},
                )
        var_strPath = request.url.path.rstrip("/") or "/"
        if var_strPath.startswith("/api/") and var_strPath not in con_setPublicPaths and con_strCookie not in request.cookies:
            return JSONResponse(
                status_code=401,
                content={"detail": "Sessão obrigatória", "code": "session_required"},
            )
        return await call_next(request)
