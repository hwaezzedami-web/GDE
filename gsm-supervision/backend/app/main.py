"""Application FastAPI : préfixe /api, documentation sur /api/docs."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from . import __version__
from .api import admin, auth
from .config import get_settings
from .db import get_engine
from .logging_setup import setup_logging

log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()  # lève ConfigError (ex. JWT_SECRET trop court) : démarrage refusé
    setup_logging(settings.log_level, settings.log_dir, name="api")
    log.info("API Supervision GSM %s démarrée", __version__)
    yield
    get_engine().dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Supervision GSM Algérie",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.include_router(auth.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")

    @app.get("/api/health", tags=["santé"])
    def health() -> dict:
        with get_engine().connect() as conn:
            version = conn.execute(text("SELECT version FROM schema_version WHERE id = 1")).scalar()
        return {"status": "ok", "version": __version__, "schema_version": version}

    return app


app = create_app()
