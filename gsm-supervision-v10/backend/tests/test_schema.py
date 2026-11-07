"""Vérifie que les modèles ORM sont alignés sur le schéma SQL (source de vérité)."""
from sqlalchemy import inspect

from app.db import get_engine
from app.models import Base


def test_models_match_sql_schema():
    insp = inspect(get_engine())
    tables = set(insp.get_table_names())
    for name, table in Base.metadata.tables.items():
        assert name in tables, f"table {name} absente du schéma SQL"
        db_cols = {c["name"] for c in insp.get_columns(name)}
        model_cols = {c.name for c in table.columns}
        assert model_cols <= db_cols, f"{name} : colonnes inconnues en base {model_cols - db_cols}"
        unmapped = db_cols - model_cols - {"geom", "boundary"}
        assert not unmapped, f"{name} : colonnes non mappées {unmapped}"
