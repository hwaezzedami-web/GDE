"""Configuration lue dans l'environnement (jamais de secret dans le code).

Chaque paramètre accepte une variante ``<NOM>_FILE`` pointant vers un fichier
(secrets Docker). La valeur directe prime sur le fichier.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

PLACEHOLDERS = {"A_COMPLETER", "CHANGEME", "CHANGE_ME"}
DEFAULT_DB_DIR = Path(__file__).resolve().parents[2] / "db"


class ConfigError(RuntimeError):
    """Configuration invalide : l'application refuse de démarrer."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    # Base de données : DATABASE_URL, sinon assemblée depuis POSTGRES_*
    database_url: str | None = None
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "gsm"
    postgres_user: str = "gsm"
    postgres_password: str | None = None

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    login_max_failures: int = 5
    login_lock_minutes: int = 15
    password_min_length: int = 10

    initial_admin_username: str = "admin"
    initial_admin_password: str | None = None

    export_max_rows: int = 100_000
    db_dir: Path = DEFAULT_DB_DIR
    log_level: str = "INFO"
    log_dir: Path | None = None

    @field_validator("jwt_secret")
    @classmethod
    def _check_jwt_secret(cls, value: str) -> str:
        if value.strip().upper() in PLACEHOLDERS:
            raise ValueError("JWT_SECRET n'est pas renseigné (valeur A_COMPLETER)")
        if len(value) < 32:
            raise ValueError("JWT_SECRET doit contenir au moins 32 caractères")
        return value

    @field_validator("initial_admin_password")
    @classmethod
    def _check_admin_password(cls, value: str | None) -> str | None:
        if value is not None and value.strip().upper() in PLACEHOLDERS:
            return None
        return value or None

    @model_validator(mode="after")
    def _check_db(self) -> "Settings":
        if not self.database_url and (
            not self.postgres_password or self.postgres_password.upper() in PLACEHOLDERS
        ):
            raise ValueError("DATABASE_URL ou POSTGRES_PASSWORD doit être renseigné")
        return self

    @property
    def sqlalchemy_url(self) -> str | URL:
        if self.database_url:
            return self.database_url
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


def _file_overrides() -> dict[str, str]:
    """Lit les variables ``<NOM>_FILE`` pour les champs dont la valeur directe est absente."""
    values: dict[str, str] = {}
    for field in Settings.model_fields:
        env_name = field.upper()
        file_var = os.environ.get(f"{env_name}_FILE")
        if file_var and not os.environ.get(env_name):
            try:
                values[field] = Path(file_var).read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise ConfigError(f"Impossible de lire {env_name}_FILE ({file_var}) : {exc}") from exc
    return values


def load_settings() -> Settings:
    try:
        return Settings(**_file_overrides())
    except ConfigError:
        raise
    except ValidationError as exc:
        # Ne jamais recopier les valeurs saisies (secrets) dans le message.
        messages = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'configuration'} : {err['msg'].removeprefix('Value error, ')}"
            for err in exc.errors(include_input=False, include_url=False)
        )
        raise ConfigError(f"Configuration invalide : {messages}") from None


@lru_cache
def get_settings() -> Settings:
    return load_settings()
