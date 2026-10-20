from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers.v1 import router
from app.security import SecurityMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    docs = "/docs" if settings.app_env == "dev" else None
    app = FastAPI(title="List Companion", docs_url=docs, redoc_url=None, openapi_url="/openapi.json" if docs else None)
    app.add_middleware(SecurityMiddleware)
    app.include_router(router)

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        code = "not_found" if exc.status_code == 404 else "invalid_input"
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc.detail), "code": code})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"detail": "Dados inválidos", "code": "validation_error", "errors": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def unexpected(_request: Request, exc: Exception):
        logging.getLogger("list-companion").exception("erro interno", exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "Erro interno", "code": "internal_error"})

    return app


app = create_app()
