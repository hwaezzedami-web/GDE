#!/usr/bin/env python3
"""Construit db/reference/wilaya_boundaries.geojson à partir d'un GeoJSON source.

Chaque entité source est rapprochée d'une wilaya de db/reference/wilayas.csv :
  --code-property CHAMP   le champ contient le code wilaya (1..69)
  --name-property CHAMP   le champ contient le nom (comparaison sans accents ni casse)

Aucun contour n'est inventé : le script refuse d'écrire le fichier si des wilayas
restent sans contour, sauf --allow-missing.

Exemple :
  python scripts/build_wilaya_reference.py source.geojson --name-property shapeName
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WILAYAS_CSV = ROOT / "db" / "reference" / "wilayas.csv"
OUTPUT = ROOT / "db" / "reference" / "wilaya_boundaries.geojson"


def normalize(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"^(wilaya|province)\s+(de\s+|d')?", "", text)
    return re.sub(r"[^a-z0-9]", "", text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--code-property")
    group.add_argument("--name-property")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--allow-missing", action="store_true")
    args = parser.parse_args()

    with WILAYAS_CSV.open(encoding="utf-8", newline="") as fh:
        wilayas = {int(r["code"]): r["name_fr"] for r in csv.DictReader(fh)}
    by_name = {normalize(name): code for code, name in wilayas.items()}

    source = json.loads(args.source.read_text(encoding="utf-8"))
    features, unmatched = [], []
    for feature in source.get("features", []):
        props = feature.get("properties") or {}
        if args.code_property:
            raw = props.get(args.code_property)
            code = int(raw) if raw is not None and str(raw).strip().isdigit() else None
        else:
            code = by_name.get(normalize(str(props.get(args.name_property, ""))))
        if code is None or code not in wilayas:
            unmatched.append(props.get(args.code_property or args.name_property))
            continue
        features.append(
            {"type": "Feature", "properties": {"code": code, "name_fr": wilayas[code]}, "geometry": feature["geometry"]}
        )

    found = {f["properties"]["code"] for f in features}
    missing = sorted(set(wilayas) - found)
    if unmatched:
        print(f"Entités source non rapprochées : {unmatched}", file=sys.stderr)
    if missing:
        print(f"Wilayas sans contour : {[f'{c} {wilayas[c]}' for c in missing]}", file=sys.stderr)
        if not args.allow_missing:
            print("Fichier non écrit (utiliser --allow-missing pour forcer).", file=sys.stderr)
            return 1
    args.output.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8"
    )
    print(f"{len(features)} contours écrits dans {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
