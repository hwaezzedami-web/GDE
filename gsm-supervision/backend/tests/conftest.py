"""Fixtures : base PostgreSQL + PostGIS réelle, créée puis supprimée (gsm_test_<pid>).

URL d'administration : TEST_DATABASE_URL (défaut postgresql+psycopg://postgres:postgres@localhost:5432/postgres).
Si PostgreSQL est injoignable, les tests qui ont besoin de la base sont ignorés avec un message explicite.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# Valeurs de test uniquement (fictives) ; posées avant tout import de l'application.
TEST_JWT_SECRET = "secret-de-test-uniquement-0123456789abcdef"
INITIAL_ADMIN_PASSWORD = "Initial-admin-2026"
ADMIN_PASSWORD = "Nouveau-chef-2026"
os.environ["JWT_SECRET"] = TEST_JWT_SECRET
os.environ["INITIAL_ADMIN_USERNAME"] = "admin"
os.environ["INITIAL_ADMIN_PASSWORD"] = INITIAL_ADMIN_PASSWORD
os.environ["LOGIN_MAX_FAILURES"] = "3"
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://invalide@localhost:1/invalide")

ADMIN_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"
)


@pytest.fixture(scope="session")
def database_url():
    admin_engine = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        conn = admin_engine.connect()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL indisponible via TEST_DATABASE_URL ({exc.__class__.__name__})")
    name = f"gsm_test_{os.getpid()}"
    conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
    conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False)
    try:
        yield url
    finally:
        from app.db import reset_engine

        reset_engine()
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.close()
        admin_engine.dispose()


@pytest.fixture(scope="session")
def initialized_db(database_url):
    os.environ["DATABASE_URL"] = database_url
    from app.config import get_settings
    from app.db import get_engine, reset_engine
    from app.services.bootstrap import init_db

    get_settings.cache_clear()
    reset_engine()
    settings = get_settings()
    result = init_db(get_engine(), settings.db_dir, settings.initial_admin_username, settings.initial_admin_password)
    return result


@pytest.fixture(scope="session")
def engine(initialized_db):
    from app.db import get_engine

    return get_engine()


@pytest.fixture(scope="session")
def client(initialized_db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def admin_token(client) -> str:
    """Connexion de l'administrateur initial puis changement de mot de passe imposé."""
    resp = client.post("/api/auth/login", json={"username": "admin", "password": INITIAL_ADMIN_PASSWORD})
    assert resp.status_code == 200, resp.text
    assert resp.json()["must_change_password"] is True
    token = resp.json()["access_token"]
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": INITIAL_ADMIN_PASSWORD, "new_password": ADMIN_PASSWORD},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def make_user(client, admin_token):
    """Crée un utilisateur prêt à l'emploi (mot de passe déjà changé) et renvoie son jeton."""
    counter = {"n": 0}

    def factory(role: str = "VIEWER", can_export: bool = False) -> tuple[str, str, str]:
        counter["n"] += 1
        username = f"{role.lower()}-{os.getpid()}-{id(counter)}-{counter['n']}"
        temp, final = "Temporaire-123", "Definitif-4567"
        resp = client.post(
            "/api/admin/users",
            json={"username": username, "password": temp, "role": role, "can_export": can_export},
            headers=auth(admin_token),
        )
        assert resp.status_code == 201, resp.text
        token = client.post("/api/auth/login", json={"username": username, "password": temp}).json()["access_token"]
        resp = client.post(
            "/api/auth/change-password",
            json={"current_password": temp, "new_password": final},
            headers=auth(token),
        )
        assert resp.status_code == 200, resp.text
        return username, final, resp.json()["access_token"]

    return factory
