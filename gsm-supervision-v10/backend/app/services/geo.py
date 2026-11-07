"""Chargement des contours administratifs des wilayas (GeoJSON) et rattachement des sites."""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session


def load_wilaya_boundaries(db: Session, geojson: dict, code_property: str = "code") -> tuple[int, list[str]]:
    """Met à jour wilayas.boundary. Retourne (nombre chargé, motifs d'exclusion)."""
    if geojson.get("type") != "FeatureCollection":
        raise ValueError("FeatureCollection GeoJSON attendue")
    codes = {r[0] for r in db.execute(text("SELECT code FROM wilayas"))}
    n, skipped = 0, []
    for i, feat in enumerate(geojson.get("features", [])):
        props = feat.get("properties") or {}
        raw = props.get(code_property)
        try:
            code = int(str(raw).strip())
        except (TypeError, ValueError):
            skipped.append(f"entité {i} : propriété {code_property!r} absente ou non numérique ({raw!r})")
            continue
        if code not in codes:
            skipped.append(f"entité {i} : code wilaya {code} inconnu du référentiel")
            continue
        geom = feat.get("geometry")
        if not geom or geom.get("type") not in ("Polygon", "MultiPolygon"):
            skipped.append(f"entité {i} : géométrie polygonale attendue")
            continue
        db.execute(text("""
            UPDATE wilayas SET boundary = ST_Multi(ST_CollectionExtract(
                       ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326)), 3))::geography,
                   boundary_source = 'custom'
            WHERE code = :c
        """), {"g": json.dumps(geom), "c": code})
        n += 1
    # Rattache les sites sans wilaya dont la position est dans un contour
    db.execute(text("""
        UPDATE sites s SET wilaya_code = w.code FROM wilayas w
        WHERE s.wilaya_code IS NULL AND s.geom IS NOT NULL AND w.boundary IS NOT NULL
          AND ST_Covers(w.boundary, s.geom)
    """))
    return n, skipped


def reassign_site_wilayas(db: Session, overwrite: bool = False) -> int:
    """Recalcule la wilaya des sites géolocalisés d'après les contours.

    overwrite=False : seulement les sites sans wilaya.
    overwrite=True  : tous les sites situés dans un contour (ex. après la création des
                      wilayas 59 à 69, pour basculer les sites de leur wilaya mère).
    """
    cond = "TRUE" if overwrite else "s.wilaya_code IS NULL"
    res = db.execute(text(f"""
        UPDATE sites s SET wilaya_code = w.code, updated_at = now() FROM wilayas w
        WHERE {cond} AND s.geom IS NOT NULL AND w.boundary IS NOT NULL
          AND ST_Covers(w.boundary, s.geom) AND s.wilaya_code IS DISTINCT FROM w.code
    """))
    return res.rowcount or 0
