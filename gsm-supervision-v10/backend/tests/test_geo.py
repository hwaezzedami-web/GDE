"""Carte de l'Algérie embarquée : 69 wilayas, contours PostGIS, rattachement des sites."""
from sqlalchemy import text

from app.collector.model import CollectResult, NElement, NSite
from app.db import apply_sql_scripts
from app.services.geo import load_wilaya_boundaries, reassign_site_wilayas
from app.services.ingest import ingest

# Carré FICTIF autour d'Alger, uniquement pour tester les contours personnalisés
SQUARE = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"code_w": "16"},
     "geometry": {"type": "Polygon", "coordinates": [[[2.8, 36.5], [3.4, 36.5], [3.4, 36.9], [2.8, 36.9], [2.8, 36.5]]]}},
    {"type": "Feature", "properties": {"code_w": "99"}, "geometry": None},
]}


def test_reference_has_69_wilayas_with_boundaries(db):
    row = db.execute(text("""SELECT count(*), count(boundary), count(*) FILTER (WHERE created_year = 2026),
                                    count(*) FILTER (WHERE boundary_source = 'osm-geoalgeria')
                             FROM wilayas""")).one()
    assert tuple(row) == (69, 69, 11, 69)
    # Chaque chef-lieu est dans le contour de sa propre wilaya
    bad = db.execute(text("""SELECT code FROM wilayas WHERE NOT ST_Covers(boundary,
                             ST_SetSRID(ST_MakePoint(center_lon, center_lat), 4326)::geography)""")).all()
    assert bad == []
    assert db.execute(text("SELECT parent_code FROM wilayas WHERE code = 59")).scalar() == 3   # Aflou <- Laghouat


def test_sites_assigned_from_coordinates(db, make_source):
    src = make_source(code="GEO", vendor="ZTE")
    ingest(db, src, CollectResult(
        sites=[NSite("G1", latitude=35.70, longitude=-0.62),                    # Oran, sans wilaya
               NSite("G2", latitude=34.11, longitude=2.10, wilaya_code=3)],     # Aflou, déclaré Laghouat
        elements=[NElement("G1-2G", "G1", "2G", oper_status="UP"), NElement("G2-2G", "G2", "2G", oper_status="UP")]))
    db.commit()
    rows = dict(db.execute(text("SELECT external_id, wilaya_code FROM sites")).all())
    assert rows == {"G1": 31, "G2": 3}          # la wilaya fournie par la source est conservée
    assert reassign_site_wilayas(db, overwrite=False) == 0
    assert reassign_site_wilayas(db, overwrite=True) == 1
    db.commit()
    assert db.execute(text("SELECT wilaya_code FROM sites WHERE external_id='G2'")).scalar() == 59


def test_custom_boundaries_are_preserved(db):
    n, skipped = load_wilaya_boundaries(db, SQUARE, "code_w")
    db.commit()
    assert n == 1 and len(skipped) == 1
    apply_sql_scripts()                          # rejouer l'initialisation ne les écrase pas
    src, area = db.execute(text("SELECT boundary_source, ST_Area(boundary) FROM wilayas WHERE code = 16")).one()
    assert src == "custom" and area > 1.5e9
    # Retour aux contours fournis
    db.execute(text("UPDATE wilayas SET boundary_source = 'osm-geoalgeria' WHERE code = 16"))
    db.commit()
    apply_sql_scripts()
    assert db.execute(text("SELECT ST_Area(boundary) < 1.5e9 FROM wilayas WHERE code = 16")).scalar()
