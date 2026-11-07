"""Fixtures de test : base PostgreSQL/PostGIS dédiée, recréée à chaque session.

Variable requise : TEST_DATABASE_URL (base d'administration, ex.
postgresql+psycopg://postgres@localhost:5432/postgres). Une base
« gsm_test_<pid> » est créée puis supprimée.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
ADMIN_URL = os.environ.get("TEST_DATABASE_URL")
if not ADMIN_URL:
    pytest.exit("Définir TEST_DATABASE_URL (PostgreSQL avec PostGIS) pour lancer les tests.", returncode=2)

DB_NAME = f"gsm_test_{os.getpid()}"
TEST_URL = make_url(ADMIN_URL).set(database=DB_NAME).render_as_string(hide_password=False)

os.environ["DATABASE_URL"] = TEST_URL
os.environ["ENVIRONMENT"] = "test"
os.environ["JWT_SECRET"] = "test-secret-" + "x" * 40
os.environ["DATA_DIR"] = str(ROOT / "data")
os.environ["SQL_INIT_DIR"] = str(ROOT / "db" / "init")
os.environ["LOGIN_MAX_FAILURES"] = "3"
os.environ.pop("INITIAL_ADMIN_USERNAME", None)


@pytest.fixture(scope="session", autouse=True)
def database():
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{DB_NAME}"'))
        c.execute(text(f'CREATE DATABASE "{DB_NAME}"'))
    from app.config import get_settings
    from app.db import apply_sql_scripts, get_engine, reset_engine

    get_settings.cache_clear()
    reset_engine()
    apply_sql_scripts(get_engine())
    yield
    reset_engine()
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{DB_NAME}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def db():
    from app.db import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def clean_db():
    """Vide les tables métier (garde le référentiel wilayas et les paramètres)."""
    from app.db import get_engine

    with get_engine().begin() as c:
        c.execute(text("""TRUNCATE status_history, alarms, site_elements, sites, collection_runs,
                          kpi_snapshots, alarm_rules, omc_sources, audit_log, users, service_heartbeats,
                          site_anomalies, reference_imports, site_code_aliases
                          RESTART IDENTITY CASCADE"""))
        c.execute(text("DELETE FROM app_settings WHERE key = 'reference'"))
        c.exec_driver_sql("""UPDATE app_settings SET value = value || '{"down_confirm_s":0,"up_confirm_s":0,
                          "unknown_elements_policy":"ignore","major_alarm_degrades":true}'::jsonb
                          WHERE key = 'status_rules'""")
        c.exec_driver_sql("""UPDATE app_settings SET value = value || '{"max_retries":1,"retry_backoff_s":1}'::jsonb
                          WHERE key = 'collector'""")
    yield


@pytest.fixture
def make_source(db, clean_db):
    from app.models import OmcSource

    def _make(code="TEST-HUAWEI", vendor="HUAWEI", connector_type="file_export", config=None,
              stale_after_s=600, enabled=True):
        o = OmcSource(code=code, name=code, vendor=vendor, connector_type=connector_type, enabled=enabled,
                      poll_interval_s=60, stale_after_s=stale_after_s, config=config or {})
        db.add(o)
        db.commit()
        return o
    return _make


@pytest.fixture
def client(clean_db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def users(db, clean_db):
    from app.models import User
    from app.security import hash_password

    pwd = "Test-Password-123"
    for name, role, exp in [("admin", "ADMIN", True), ("superviseur", "SUPERVISOR", True),
                            ("lecteur", "VIEWER", False)]:
        db.add(User(username=name, role=role, can_export=exp, password_hash=hash_password(pwd)))
    db.commit()
    return pwd


@pytest.fixture
def login(client, users):
    def _login(username="admin"):
        r = client.post("/api/auth/login", json={"username": username, "password": users})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}
    return _login
