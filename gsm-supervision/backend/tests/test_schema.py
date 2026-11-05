"""Le schéma SQL (source de vérité) et models.py doivent correspondre exactement."""

from __future__ import annotations

from sqlalchemy import text

from app.models import Base
from app.services.bootstrap import EXPECTED_SCHEMA_VERSION, init_db

IGNORED_TABLES = {"spatial_ref_sys"}  # table interne de PostGIS


def _db_columns(engine) -> dict[str, set[str]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT c.table_name, c.column_name
                  FROM information_schema.columns c
                  JOIN information_schema.tables t
                    ON t.table_schema = c.table_schema AND t.table_name = c.table_name
                 WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE'
                """
            )
        ).all()
    columns: dict[str, set[str]] = {}
    for table, column in rows:
        if table not in IGNORED_TABLES:
            columns.setdefault(table, set()).add(column)
    return columns


def test_every_table_and_column_is_mapped(engine):
    db = _db_columns(engine)
    orm = {name: {c.name for c in table.columns} for name, table in Base.metadata.tables.items()}
    assert set(db) == set(orm), f"Tables non mappées : {set(db) ^ set(orm)}"
    for table, columns in db.items():
        missing = columns - orm[table]
        extra = orm[table] - columns
        assert not missing, f"{table} : colonnes non mappées dans models.py : {sorted(missing)}"
        assert not extra, f"{table} : colonnes mappées absentes de la base : {sorted(extra)}"


def test_schema_version(initialized_db):
    assert initialized_db["schema_version"] == EXPECTED_SCHEMA_VERSION == 4


def test_init_db_is_idempotent(engine):
    from app.config import get_settings

    settings = get_settings()
    result = init_db(engine, settings.db_dir, settings.initial_admin_username, settings.initial_admin_password)
    assert result["admin_created"] is False  # l'administrateur n'est pas recréé
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM wilayas")).scalar() == 69
        assert conn.execute(text("SELECT count(*) FROM users WHERE role = 'ADMIN'")).scalar() >= 1
        assert conn.execute(text("SELECT count(*) FROM app_settings WHERE key = 'status_rules'")).scalar() == 1


def test_extensions_present(engine):
    with engine.connect() as conn:
        names = set(conn.execute(text("SELECT extname FROM pg_extension")).scalars())
    assert {"postgis", "pg_trgm"} <= names


def test_wilaya_reference(engine):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT code, name_fr, parent_code FROM wilayas ORDER BY code")).all()
    assert [r.code for r in rows] == list(range(1, 70))
    assert rows[15].name_fr == "Alger"
    # les wilayas 59 à 69 ont une wilaya mère parmi les 58 historiques
    assert all(r.parent_code and 1 <= r.parent_code <= 58 for r in rows[58:])


def test_alias_fk_cascades_on_site_code_change(engine):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO sites (external_id, name) VALUES ('TST-ALIAS-1', 'Site fictif')"))
        conn.execute(text("INSERT INTO site_code_aliases (omc_code, site_code) VALUES ('0TST-ALIAS-1', 'TST-ALIAS-1')"))
        conn.execute(text("UPDATE sites SET external_id = 'TST-ALIAS-2' WHERE external_id = 'TST-ALIAS-1'"))
        target = conn.execute(text("SELECT site_code FROM site_code_aliases WHERE omc_code = '0TST-ALIAS-1'")).scalar()
        assert target == "TST-ALIAS-2"
        conn.execute(text("DELETE FROM sites WHERE external_id = 'TST-ALIAS-2'"))
        assert conn.execute(text("SELECT count(*) FROM site_code_aliases WHERE omc_code = '0TST-ALIAS-1'")).scalar() == 0
