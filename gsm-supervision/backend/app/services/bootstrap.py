"""Initialisation idempotente de la base (``python -m app.cli init-db``).

1. Rejoue ``db/init/*.sql`` dans l'ordre (scripts idempotents).
2. Charge les wilayas (``db/reference/wilayas.csv``) et leurs contours (GeoJSON).
3. Crée les paramètres par défaut et, si aucun utilisateur n'existe, l'administrateur initial.

Un verrou consultatif évite que plusieurs conteneurs initialisent la base en même temps.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from ..models import User
from ..security import hash_password, record_audit

log = logging.getLogger(__name__)

INIT_LOCK_ID = 7421001
EXPECTED_SCHEMA_VERSION = 4

DEFAULT_SETTINGS: dict[str, dict] = {
    "status_rules": {
        "partial_down_is_degraded": True,
        "major_alarm_degrades": True,
        "unknown_elements_policy": "ignore",
        "down_confirm_s": 0,
        "up_confirm_s": 0,
        "default_stale_after_s": 1800,
    },
}


def run_sql_scripts(engine: Engine, db_dir: Path) -> list[str]:
    scripts = sorted((db_dir / "init").glob("*.sql"))
    if not scripts:
        raise FileNotFoundError(f"Aucun script SQL dans {db_dir / 'init'}")
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": INIT_LOCK_ID})
        for script in scripts:
            log.info("Script SQL : %s", script.name)
            conn.exec_driver_sql(script.read_text(encoding="utf-8"))
    return [s.name for s in scripts]


def load_wilayas(session: Session, csv_path: Path) -> int:
    with csv_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        session.execute(
            text(
                """
                INSERT INTO wilayas (code, name_fr, name_ar, region, parent_code)
                VALUES (:code, :name_fr, :name_ar, :region, :parent_code)
                ON CONFLICT (code) DO UPDATE SET
                    name_fr = EXCLUDED.name_fr,
                    name_ar = EXCLUDED.name_ar,
                    -- la DR saisie en base n'est pas écrasée par un CSV vide
                    region = COALESCE(EXCLUDED.region, wilayas.region),
                    parent_code = EXCLUDED.parent_code,
                    updated_at = now()
                """
            ),
            {
                "code": int(row["code"]),
                "name_fr": row["name_fr"].strip(),
                "name_ar": (row.get("name_ar") or "").strip() or None,
                "region": (row.get("region") or "").strip() or None,
                "parent_code": int(row["parent_code"]) if (row.get("parent_code") or "").strip() else None,
            },
        )
    return len(rows)


def load_boundaries(session: Session, geojson_path: Path) -> int:
    if not geojson_path.exists():
        log.warning("Contours absents : %s", geojson_path)
        return 0
    data = json.loads(geojson_path.read_text(encoding="utf-8"))
    count = 0
    for feature in data.get("features", []):
        code = (feature.get("properties") or {}).get("code")
        geometry = feature.get("geometry")
        if code is None or not geometry:
            continue
        result = session.execute(
            text(
                """
                UPDATE wilayas
                   SET geom = ST_Multi(ST_CollectionExtract(
                                ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326)), 3)),
                       updated_at = now()
                 WHERE code = :code
                """
            ),
            {"g": json.dumps(geometry), "code": int(code)},
        )
        count += result.rowcount
    if count == 0:
        log.warning("Aucun contour de wilaya chargé (voir db/reference/README.md)")
    return count


def ensure_default_settings(session: Session) -> None:
    for key, value in DEFAULT_SETTINGS.items():
        session.execute(
            text(
                "INSERT INTO app_settings (key, value, updated_by) VALUES (:k, CAST(:v AS jsonb), 'system') "
                "ON CONFLICT (key) DO NOTHING"
            ),
            {"k": key, "v": json.dumps(value)},
        )


def ensure_initial_admin(session: Session, username: str, password: str | None) -> bool:
    """Crée l'administrateur initial si la table ``users`` est vide."""
    if session.scalar(select(func.count()).select_from(User)):
        return False
    if not password:
        log.warning("Aucun utilisateur et INITIAL_ADMIN_PASSWORD absent : administrateur non créé")
        return False
    user = User(
        username=username,
        full_name="Administrateur",
        password_hash=hash_password(password),
        role="ADMIN",
        can_export=True,
        must_change_password=True,
        password_changed_at=datetime.now(UTC),
    )
    session.add(user)
    session.flush()
    record_audit(session, "USER_CREATE", username="system", target=username, details={"role": "ADMIN", "initial": True})
    log.info("Administrateur initial « %s » créé (changement de mot de passe imposé)", username)
    return True


def schema_version(session: Session) -> int | None:
    return session.scalar(text("SELECT version FROM schema_version WHERE id = 1"))


def init_db(engine: Engine, db_dir: Path, admin_username: str, admin_password: str | None) -> dict:
    scripts = run_sql_scripts(engine, db_dir)
    with Session(engine) as session, session.begin():
        session.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": INIT_LOCK_ID})
        wilayas = load_wilayas(session, db_dir / "reference" / "wilayas.csv")
        boundaries = load_boundaries(session, db_dir / "reference" / "wilaya_boundaries.geojson")
        ensure_default_settings(session)
        admin_created = ensure_initial_admin(session, admin_username, admin_password)
        version = schema_version(session)
    if version != EXPECTED_SCHEMA_VERSION:
        raise RuntimeError(f"Version de schéma {version}, attendu {EXPECTED_SCHEMA_VERSION}")
    return {
        "scripts": scripts,
        "wilayas": wilayas,
        "boundaries": boundaries,
        "admin_created": admin_created,
        "schema_version": version,
    }
