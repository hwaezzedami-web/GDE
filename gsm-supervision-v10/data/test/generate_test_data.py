#!/usr/bin/env python3
"""Génère le jeu de données de test FICTIF : data/test/sites_fictifs.csv

  python data/test/generate_test_data.py [--sites 3000] [--seed 2026]

TOUTES LES DONNÉES SONT FICTIVES : codes TST-*, noms TEST_*, positions tirées
aléatoirement autour des chefs-lieux de wilaya, équipementiers et états
attribués au hasard. Elles ne représentent aucun réseau réel.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WILAYAS_CSV = ROOT / "db" / "reference" / "wilayas.csv"
BOUNDARIES = ROOT / "db" / "reference" / "wilaya_boundaries.geojson"
OUT = Path(__file__).resolve().parent / "sites_fictifs.csv"

# Poids relatifs (densité de sites fictive, plus forte dans les grandes villes)
WEIGHTS = {16: 14, 31: 8, 25: 6, 19: 6, 9: 5, 35: 4, 15: 4, 6: 4, 23: 4, 5: 4, 13: 3, 22: 3,
           42: 3, 26: 3, 28: 3, 17: 3, 7: 3, 27: 3, 48: 2, 2: 3, 14: 2, 21: 3, 34: 3, 43: 2,
           10: 3, 44: 2, 29: 2, 12: 2, 4: 2, 24: 2, 41: 2, 18: 2, 40: 2, 36: 2, 46: 2, 30: 2, 47: 2,
           39: 2, 3: 2, 20: 1, 38: 1, 32: 1, 45: 1}
STATUS_WEIGHTS = [("UP", 92), ("DOWN", 3), ("DEGRADED", 3), ("UNKNOWN", 2)]


def _in_ring(x: float, y: float, ring: list) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][:2]
        xj, yj = ring[j][:2]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def load_polygons() -> dict[int, list]:
    """Contours des wilayas : {code: [polygone, …]} (polygone = [anneau extérieur, trous…])."""
    g = json.loads(BOUNDARIES.read_text(encoding="utf-8"))
    out = {}
    for f in g["features"]:
        geom = f["geometry"]
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        out[int(f["properties"]["code"])] = polys
    return out


def inside(polys: list, lon: float, lat: float) -> bool:
    for poly in polys:
        if _in_ring(lon, lat, poly[0]) and not any(_in_ring(lon, lat, h) for h in poly[1:]):
            return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=2026)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    wilayas = list(csv.DictReader(WILAYAS_CSV.open(encoding="utf-8")))
    weights = [WEIGHTS.get(int(w["code"]), 0.6) for w in wilayas]
    polygons = load_polygons() if BOUNDARIES.is_file() else {}
    # Équipementier fictif attribué par wilaya (zones de déploiement simulées)
    vendor_of = {w["code"]: rng.choice(["ERICSSON", "HUAWEI", "ZTE"]) for w in wilayas}
    counters: dict[str, int] = {}
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows = []
    for _ in range(a.sites):
        w = rng.choices(wilayas, weights)[0]
        code = int(w["code"])
        south = w["region"] == "Sud"
        sigma = 0.45 if south else (0.08 if code in (16, 31, 25) else 0.18)
        # Position tirée autour du chef-lieu, à l'intérieur du contour de la wilaya
        for _ in range(200):
            lat = round(float(w["center_lat"]) + rng.gauss(0, sigma), 6)
            lon = round(float(w["center_lon"]) + rng.gauss(0, sigma * 1.2), 6)
            if code not in polygons or inside(polygons[code], lon, lat):
                break
        else:
            lat, lon = float(w["center_lat"]), float(w["center_lon"])
        counters[w["code"]] = counters.get(w["code"], 0) + 1
        n = counters[w["code"]]
        vendor = vendor_of[w["code"]] if rng.random() < 0.85 else rng.choice(["ERICSSON", "HUAWEI", "ZTE"])
        techs = ["2G"]
        if rng.random() < 0.85:
            techs.append("3G")
        if rng.random() < (0.85 if not south else 0.5):
            techs.append("4G")
        if code in (16, 31, 25, 19) and rng.random() < 0.12:
            techs.append("5G")
        status = rng.choices([s for s, _ in STATUS_WEIGHTS], [p for _, p in STATUS_WEIGHTS])[0]
        alarm = ("", "", "")
        if status == "DOWN":
            alarm = ("TST-100", "[FICTIF] Site injoignable", "CRITICAL")
        elif status == "DEGRADED" and rng.random() < 0.5:
            alarm = ("TST-200", "[FICTIF] Défaut transmission", "MAJOR")
        rows.append({
            "site_code": f"TST-{code:02d}-{n:04d}",
            "site_name": f"TEST_{w['chef_lieu'].upper().replace(' ', '_').replace(chr(39), '')}_{n:04d}",
            "wilaya_code": code,
            "commune": w["chef_lieu"],
            "latitude": lat,
            "longitude": lon,
            "vendor": vendor,
            "technologies": "|".join(techs),
            "status": status,
            "omc_source": f"DEMO-{vendor}",
            "last_update": now,
            "alarm_code": alarm[0],
            "alarm_text": alarm[1],
            "alarm_severity": alarm[2],
        })
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        fh.write("# JEU DE DONNÉES FICTIF - aucune correspondance avec un réseau réel\n")
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), delimiter=";")
        wr.writeheader()
        wr.writerows(rows)
    print(f"{len(rows)} sites fictifs écrits dans {OUT}")


if __name__ == "__main__":
    main()
