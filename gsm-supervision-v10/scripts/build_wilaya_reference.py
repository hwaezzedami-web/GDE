#!/usr/bin/env python3
"""Construit le référentiel des 69 wilayas et leurs contours à partir du paquet geoalgeria.

  npm pack geoalgeria && tar -xzf geoalgeria-*.tgz          (dans un répertoire temporaire)
  python3 scripts/build_wilaya_reference.py <chemin>/package

Produit :
  db/reference/wilayas.csv                  référentiel (codes, noms FR/AR, région, chef-lieu, wilaya mère)
  db/reference/wilaya_boundaries.geojson    contours des 69 wilayas (ODbL, © contributeurs OpenStreetMap)
  db/init/03_reference_wilayas.sql          insertion / mise à jour du référentiel
  db/init/04_wilaya_boundaries.sql          chargement des contours (n'écrase pas des contours personnalisés)

Les régions (Centre, Est, Ouest, Sud) sont un découpage d'exploitation propre au projet :
elles sont reprises du référentiel existant ; une wilaya créée en 2026 hérite de la région
de sa wilaya mère. À adapter au découpage régional de l'opérateur.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "db" / "reference"


def q(s) -> str:
    return "NULL" if s is None or s == "" else "'" + str(s).replace("'", "''") + "'"


def chef_lieu(capital: str | None, wilaya: str) -> str:
    """Nom du chef-lieu ; reprend l'orthographe accentuée de la wilaya quand il s'agit du même nom."""
    import unicodedata

    def k(x: str) -> str:
        x = "".join(c for c in unicodedata.normalize("NFKD", x) if not unicodedata.combining(c))
        return "".join(c for c in x.lower() if c.isalnum())
    if not capital or k(capital) == k(wilaya):
        return wilaya
    return capital


def main(pkg: Path) -> None:
    data = pkg / "data"
    wil = json.loads((data / "wilayas.json").read_text(encoding="utf-8"))["wilayas"]
    caps = {f["properties"]["code"]: f["geometry"]["coordinates"]
            for f in json.loads((data / "geojson" / "wilayas.geojson").read_text(encoding="utf-8"))["features"]}
    bounds = json.loads((data / "geojson" / "wilaya-boundaries.geojson").read_text(encoding="utf-8"))
    old_regions = {int(r["code"]): r["region"]
                   for r in csv.DictReader((REF / "wilayas.csv").open(encoding="utf-8"))}
    capital_names = {}
    for f in ("communes_w1_w23.json", "communes_w24_w48.json", "communes_w49_w69.json"):
        d = json.loads((data / f).read_text(encoding="utf-8"))
        for c in (d if isinstance(d, list) else d.get("communes", [])):
            capital_names[int(c["code_commune"])] = c.get("name_fr")

    rows = []
    for w in sorted(wil, key=lambda x: x["code"]):
        code = int(w["code"])
        parent = w.get("mother_wilaya_code")
        region = old_regions.get(code) or old_regions.get(int(parent)) if parent else old_regions.get(code)
        lon, lat = caps[code]
        rows.append({
            "code": code, "name": w["name_fr"], "name_ar": w["name_ar"], "region": region or "Sud",
            "chef_lieu": chef_lieu(capital_names.get(int(w["capital_commune_code"])), w["name_fr"]),
            "center_lat": round(lat, 5), "center_lon": round(lon, 5),
            "parent_code": parent or "", "created": w.get("created", 1984),
        })
    assert len(rows) == 69 and len(bounds["features"]) == 69, "69 wilayas attendues"

    with (REF / "wilayas.csv").open("w", encoding="utf-8", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)

    bounds["attribution"] = "© contributeurs OpenStreetMap (ODbL 1.0), compilation geoalgeria"
    (REF / "wilaya_boundaries.geojson").write_text(json.dumps(bounds, ensure_ascii=False, separators=(",", ":")),
                                                   encoding="utf-8")

    sql = ["-- =============================================================================",
           "-- Référentiel des 69 wilayas (loi n° 26-06, JO n° 25 du 5 avril 2026 ; les wilayas",
           "-- 59 à 69 exercent pleinement leurs compétences à partir du 1er janvier 2027).",
           "-- Généré par scripts/build_wilaya_reference.py depuis le paquet geoalgeria.",
           "-- center_lat/center_lon = chef-lieu (sert à centrer la carte).",
           "-- =============================================================================",
           "INSERT INTO wilayas (code, name, name_ar, region, chef_lieu, center_lat, center_lon, parent_code, created_year) VALUES"]
    vals = [f"({r['code']}, {q(r['name'])}, {q(r['name_ar'])}, {q(r['region'])}, {q(r['chef_lieu'])}, "
            f"{r['center_lat']}, {r['center_lon']}, {r['parent_code'] or 'NULL'}, {r['created']})" for r in rows]
    sql.append(",\n".join(vals))
    sql.append("""ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, name_ar = EXCLUDED.name_ar,
  region = EXCLUDED.region, chef_lieu = EXCLUDED.chef_lieu, center_lat = EXCLUDED.center_lat,
  center_lon = EXCLUDED.center_lon, parent_code = EXCLUDED.parent_code, created_year = EXCLUDED.created_year;
""")
    (ROOT / "db" / "init" / "03_reference_wilayas.sql").write_text("\n".join(sql), encoding="utf-8")

    b = ["-- =============================================================================",
         "-- Contours des 69 wilayas — © contributeurs OpenStreetMap, licence ODbL 1.0",
         "-- (compilation geoalgeria, simplifiés ~2 %, précision ~100 m à 3 km selon les zones).",
         "-- Usage : affichage de la carte et rattachement automatique des sites à leur wilaya.",
         "-- Les contours chargés manuellement (boundary_source = 'custom', commande",
         "-- « python -m app.cli load-boundaries ») ne sont jamais écrasés par ce script.",
         "-- Généré par scripts/build_wilaya_reference.py.",
         "-- ============================================================================="]
    for f in sorted(bounds["features"], key=lambda x: x["properties"]["code"]):
        g = json.dumps(f["geometry"], separators=(",", ":"))
        b.append(f"UPDATE wilayas SET boundary = ST_Multi(ST_CollectionExtract(ST_MakeValid("
                 f"ST_SetSRID(ST_GeomFromGeoJSON('{g}'), 4326)), 3))::geography, boundary_source = 'osm-geoalgeria'\n"
                 f"WHERE code = {f['properties']['code']} AND (boundary IS NULL OR boundary_source = 'osm-geoalgeria');")
    b.append("""
-- Sites sans wilaya renseignée : rattachement d'après leurs coordonnées
UPDATE sites s SET wilaya_code = w.code FROM wilayas w
WHERE s.wilaya_code IS NULL AND s.geom IS NOT NULL AND w.boundary IS NOT NULL AND ST_Covers(w.boundary, s.geom);

INSERT INTO schema_version (version, description) VALUES (2, '69 wilayas (loi 26-06) et contours OSM')
ON CONFLICT (version) DO NOTHING;
""")
    (ROOT / "db" / "init" / "04_wilaya_boundaries.sql").write_text("\n".join(b), encoding="utf-8")
    print(f"{len(rows)} wilayas, {len(bounds['features'])} contours écrits.")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
