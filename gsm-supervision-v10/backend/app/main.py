"""Application FastAPI — API de supervision des sites GSM."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from .api import admin, alarms, auth, dashboard, export, reference, site_management, site_reference, sites
from .config import get_settings
from .db import get_db, session_scope
from .logging_setup import setup_logging
from .services.bootstrap import ensure_initial_admin
from .services.status_engine import evaluate_all_locked

log = logging.getLogger("gsm.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    setup_logging("api", s.log_level, s.log_dir)
    s.check_production()
    try:
        with session_scope() as db:
            ensure_initial_admin(db)
    except Exception:  # la base peut ne pas être prête : l'API démarre quand même (/api/health le signale)
        log.exception("Initialisation : impossible de vérifier le compte administrateur")
    log.info("API démarrée (environnement=%s)", s.environment)
    watchdog = asyncio.create_task(_freshness_watchdog()) if s.environment != "test" else None
    yield
    if watchdog:
        watchdog.cancel()
        with suppress(asyncio.CancelledError):
            await watchdog


async def _freshness_watchdog(interval_s: int = 90) -> None:
    """Filet de sécurité : fait vieillir les données même si le service de collecte est arrêté."""
    while True:
        await asyncio.sleep(interval_s)
        try:
            res = await asyncio.to_thread(evaluate_all_locked)
            if res and res["transitions"]:
                log.info("Réévaluation (API) : %d transition(s)", res["transitions"])
        except Exception:
            log.exception("Réévaluation périodique en échec")


app = FastAPI(
    title="GSM Supervision Algérie — API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

_s = get_settings()
if _s.cors_origin_list:
    app.add_middleware(CORSMiddleware, allow_origins=_s.cors_origin_list, allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Authorization", "Content-Type"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api/") and "Cache-Control" not in response.headers:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Erreur non gérée sur %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Erreur interne du serveur."})


for r in (auth.router, sites.router, dashboard.router, alarms.router, export.router,
          reference.router, site_reference.router, site_management.router, admin.router):
    app.include_router(r)


@app.get("/api/health", tags=["health"])
def health(db: Session = Depends(get_db)):
    """Sonde de disponibilité (sans authentification, sans donnée sensible)."""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "unavailable"})
