"""Configuration lue depuis les variables d'environnement (aucun secret dans le code).

Voir .env.example à la racine du projet pour la liste complète.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Base de données
    database_url: str = Field(
        default="postgresql+psycopg://gsm:gsm@localhost:5432/gsm_supervision",
        description="URL SQLAlchemy de la base centrale",
    )
    db_pool_size: int = 10

    # Sécurité / sessions
    jwt_secret: str = Field(default="", description="Clé de signature des jetons (obligatoire en production)")
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    login_max_failures: int = 5
    login_lock_minutes: int = 15
    password_min_length: int = 10
    # Texte simple « https://a,https://b » (une liste typée serait lue comme du JSON : une valeur vide planterait)
    cors_origins: str = ""

    # Application
    environment: str = "production"  # production | development | test
    log_level: str = "INFO"
    log_dir: str | None = None
    export_max_rows: int = 200_000
    map_max_points: int = 100_000

    # Données de référence (CSV fictif d'exemple / profils connecteurs)
    data_dir: str = "/app/data"
    # Dossier surveillé pour l'import automatique du référentiel de sites (lecture seule)
    reference_watch_dir: str = "/data/referentiel"

    # Premier administrateur (créé uniquement si aucun utilisateur n'existe)
    initial_admin_username: str | None = None
    initial_admin_password: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def check_production(self) -> None:
        if self.environment == "production":
            if len(self.jwt_secret) < 32:
                raise RuntimeError(
                    "JWT_SECRET doit être défini (32 caractères minimum) en production. "
                    "Générez-le avec : python -c \"import secrets; print(secrets.token_urlsafe(48))\""
                )


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if not s.jwt_secret and s.environment != "production":
        # Secret éphémère pour le développement : les sessions sont perdues au redémarrage.
        import secrets

        s.jwt_secret = secrets.token_urlsafe(48)
    return s
