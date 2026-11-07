"""Connexion à la base PostgreSQL et utilitaires de session."""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        s = get_settings()
        _engine = create_engine(
            s.database_url,
            pool_size=s.db_pool_size,
            max_overflow=s.db_pool_size,
            pool_pre_ping=True,      # reconnexion transparente après coupure
            pool_recycle=1800,
            future=True,
        )
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def reset_engine() -> None:
    """Utilisé par les tests pour changer d'URL de base."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def SessionLocal() -> Session:  # noqa: N802 - API proche de sessionmaker
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def get_db() -> Iterator[Session]:
    """Dépendance FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def sql_dir() -> Path:
    env = os.environ.get("SQL_INIT_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for p in [here.parents[2] / "db" / "init", Path("/app/db/init")]:
        if p.is_dir():
            return p
    raise FileNotFoundError("Répertoire des scripts SQL introuvable (définir SQL_INIT_DIR)")


def apply_sql_scripts(engine: Engine | None = None) -> list[str]:
    """Applique les scripts db/init/*.sql (idempotents). Retourne la liste appliquée."""
    engine = engine or get_engine()
    applied = []
    for f in sorted(sql_dir().glob("*.sql")):
        sql = f.read_text(encoding="utf-8")
        with engine.begin() as conn:
            # Exécution brute sans paramètres : les « % » des scripts ne sont pas interprétés
            with conn.connection.dbapi_connection.cursor() as cur:
                cur.execute(sql)
        applied.append(f.name)
    return applied


def schema_exists(engine: Engine | None = None) -> bool:
    engine = engine or get_engine()
    with engine.connect() as conn:
        return bool(conn.execute(text("SELECT to_regclass('public.sites') IS NOT NULL")).scalar())
