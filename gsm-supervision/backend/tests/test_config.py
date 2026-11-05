"""Configuration : refus de démarrer sans secret valide, variantes *_FILE."""

from __future__ import annotations

import pytest

from app.config import ConfigError, load_settings

VALID_SECRET = "s" * 40


@pytest.fixture
def env(monkeypatch):
    for name in ("DATABASE_URL", "JWT_SECRET", "JWT_SECRET_FILE", "POSTGRES_PASSWORD", "POSTGRES_PASSWORD_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("POSTGRES_PASSWORD", "mot-de-passe-fictif")
    return monkeypatch


def test_jwt_secret_required(env):
    with pytest.raises(ConfigError):
        load_settings()


def test_jwt_secret_too_short(env):
    env.setenv("JWT_SECRET", "court")
    with pytest.raises(ConfigError, match="32 caractères"):
        load_settings()


def test_error_message_never_contains_secret(env):
    env.setenv("JWT_SECRET", "valeur-secrete-courte")
    with pytest.raises(ConfigError) as info:
        load_settings()
    assert "valeur-secrete-courte" not in str(info.value)


def test_jwt_secret_placeholder_rejected(env):
    env.setenv("JWT_SECRET", "A_COMPLETER")
    with pytest.raises(ConfigError, match="A_COMPLETER"):
        load_settings()


def test_secret_file_variant(env, tmp_path):
    secret = tmp_path / "jwt"
    secret.write_text(VALID_SECRET + "\n", encoding="utf-8")
    env.setenv("JWT_SECRET_FILE", str(secret))
    assert load_settings().jwt_secret == VALID_SECRET


def test_direct_value_wins_over_file(env, tmp_path):
    secret = tmp_path / "jwt"
    secret.write_text("f" * 40, encoding="utf-8")
    env.setenv("JWT_SECRET_FILE", str(secret))
    env.setenv("JWT_SECRET", VALID_SECRET)
    assert load_settings().jwt_secret == VALID_SECRET


def test_unreadable_secret_file(env, tmp_path):
    env.setenv("JWT_SECRET_FILE", str(tmp_path / "absent"))
    with pytest.raises(ConfigError, match="JWT_SECRET_FILE"):
        load_settings()


def test_database_password_required(env):
    env.delenv("POSTGRES_PASSWORD")
    env.setenv("JWT_SECRET", VALID_SECRET)
    with pytest.raises(ConfigError, match="POSTGRES_PASSWORD"):
        load_settings()


def test_url_built_from_postgres_parts(env):
    env.setenv("JWT_SECRET", VALID_SECRET)
    env.setenv("POSTGRES_PASSWORD", "p@ss:wo/rd")
    env.setenv("POSTGRES_HOST", "db")
    url = load_settings().sqlalchemy_url
    assert url.host == "db" and url.password == "p@ss:wo/rd" and url.drivername == "postgresql+psycopg"


def test_placeholder_admin_password_ignored(env):
    env.setenv("JWT_SECRET", VALID_SECRET)
    env.setenv("INITIAL_ADMIN_PASSWORD", "A_COMPLETER")
    assert load_settings().initial_admin_password is None
