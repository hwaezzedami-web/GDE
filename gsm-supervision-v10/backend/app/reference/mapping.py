"""Correspondance colonnes du fichier -> champs du référentiel, et normalisation des sites.

Champs cibles :
  code (obligatoire), name, latitude, longitude (ou géométrie du point), wilaya, commune,
  address, dr (direction régionale), lifecycle (cycle de vie), technologies.
Toutes les autres colonnes sont conservées telles quelles (« attributs du référentiel »).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .parsers import GEOMETRY, PLACEMARK_NAME, ParsedTable

TARGETS = ("code", "name", "latitude", "longitude", "wilaya", "commune", "address", "dr", "lifecycle",
           "technologies")
TARGET_LABELS = {
    "code": "Code site", "name": "Nom du site", "latitude": "Latitude", "longitude": "Longitude",
    "wilaya": "Wilaya", "commune": "Commune", "address": "Adresse", "dr": "Direction régionale",
    "lifecycle": "Cycle de vie", "technologies": "Technologies",
}
# Synonymes reconnus (comparaison sans accents, minuscules, sans ponctuation), du plus sûr au moins sûr
SYNONYMS = {
    "code": ["code site", "code du site", "site code", "code_site", "site id", "siteid", "site_id", "id site",
             "code", "site"],
    "name": ["nom du site", "nom site", "site name", "nom", "name", "libelle", "designation"],
    "latitude": ["latitude", "lat", "y", "latitude dd", "lat dd"],
    "longitude": ["longitude", "lon", "long", "lng", "x", "longitude dd", "lon dd"],
    "wilaya": ["wilaya", "province", "nom wilaya"],
    "commune": ["commune", "municipalite", "baladia"],
    "address": ["adresse", "address", "localisation", "emplacement"],
    "dr": ["region", "dr", "direction regionale", "direction", "zone"],
    "lifecycle": ["etape cycle de vie", "cycle de vie", "lifecycle", "etat du site", "statut site", "phase"],
    "technologies": ["technologies radio", "technologies", "technologie", "techno", "technology", "rat"],
}
NULL_TOKENS = {"", "nan", "null", "none", "---", "--", "-", "n/a", "na", "#n/a", "???", "?", "0.0,0.0"}
LAT_RANGE, LON_RANGE = (18.0, 38.5), (-9.5, 12.5)


def _key(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def detect_mapping(table: ParsedTable) -> dict[str, str | None]:
    """Propose une colonne par champ cible (ou None)."""
    cols = list(table.columns)
    keys = {c: _key(c) for c in cols}
    used: set[str] = set()
    mapping: dict[str, str | None] = {}
    for target in TARGETS:
        best, best_score = None, 0
        for rank, syn in enumerate(SYNONYMS[target]):
            for c in cols:
                if c in used:
                    continue
                k = keys[c]
                score = 0
                if k == syn:
                    score = 100 - rank
                elif len(syn) > 3 and (k.startswith(syn + " ") or k.endswith(" " + syn)):
                    score = 50 - rank
                if score > best_score:
                    best, best_score = c, score
        mapping[target] = best
        if best:
            used.add(best)
    if table.has_geometry:
        # Les coordonnées du point priment sur des colonnes texte
        mapping["latitude"] = mapping["longitude"] = GEOMETRY
    if not mapping["code"] and table.format in ("kml", "kmz"):
        mapping["code"] = PLACEMARK_NAME
    return mapping


# --------------------------------------------------------------------------- valeurs
_DMS = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)\s*[°d]\s*(?:(\d+(?:[.,]\d+)?)\s*['m′]\s*)?(?:(\d+(?:[.,]\d+)?)\s*(?:\"|''|s|″)\s*)?([NSEOW])?\s*$", re.I)


def parse_coord(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace("’", "'")
    if s.lower() in NULL_TOKENS:
        return None
    m = _DMS.match(s)
    if m and ("°" in s or "d" in s.lower()):
        deg = float(m.group(1).replace(",", "."))
        mins = float((m.group(2) or "0").replace(",", "."))
        secs = float((m.group(3) or "0").replace(",", "."))
        val = abs(deg) + mins / 60 + secs / 3600
        if deg < 0 or (m.group(4) or "").upper() in ("S", "W", "O"):
            val = -val
        return val
    try:
        return float(s.replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


def clean(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return None if s.lower() in NULL_TOKENS else s


_TECH_RX = re.compile(r"\b([2-5])\s?G\b", re.I)
_TECH_WORDS = {"GSM": "2G", "DCS": "2G", "UMTS": "3G", "WCDMA": "3G", "LTE": "4G", "NR": "5G"}


def parse_technologies(v) -> list[str]:
    s = clean(v)
    if not s:
        return []
    found = {f"{m}G" for m in _TECH_RX.findall(s)}
    for w, t in _TECH_WORDS.items():
        if re.search(rf"\b{w}\b", s, re.I):
            found.add(t)
    return sorted(found)


def normalize_code(v, digits: int | None) -> str | None:
    s = clean(v)
    if not s:
        return None
    if re.fullmatch(r"\d+\.0+", s):            # 5474.0 (Excel)
        s = s.split(".")[0]
    s = s.upper()
    if digits and s.isdigit() and len(s) < digits:
        s = s.zfill(digits)
    return s


# --------------------------------------------------------------------------- normalisation
@dataclass
class RefSite:
    code: str
    name: str | None
    lat: float
    lon: float
    wilaya_label: str | None
    commune: str | None
    address: str | None
    dr: str | None
    lifecycle: str | None
    technologies: list[str]
    attributes: dict
    line: int


@dataclass
class Normalized:
    sites: list[RefSite] = field(default_factory=list)
    invalid: list[dict] = field(default_factory=list)     # {line, code, reason}
    fixes: list[dict] = field(default_factory=list)       # {line, code, fix}


def normalize(table: ParsedTable, mapping: dict, code_digits: int | None = None) -> Normalized:
    out = Normalized()
    if not mapping.get("code"):
        raise ValueError("Choisir la colonne du code site")
    if not (mapping.get("latitude") and mapping.get("longitude")):
        raise ValueError("Choisir les colonnes de latitude et de longitude")
    mapped = {c for c in mapping.values() if c}
    seen: dict[str, int] = {}
    first_line = 2 if table.format in ("xlsx", "csv") else 1
    for i, row in enumerate(table.rows):
        line = i + first_line
        code = normalize_code(row.get(mapping["code"]), code_digits)
        if not code:
            out.invalid.append({"line": line, "code": None, "reason": "code site vide"})
            continue
        if len(code) > 60:
            out.invalid.append({"line": line, "code": code[:60], "reason": "code site trop long"})
            continue
        if code in seen:
            out.invalid.append({"line": line, "code": code, "reason": f"code en double (déjà ligne {seen[code]})"})
            continue
        if mapping["latitude"] == GEOMETRY:
            lat, lon = row.get(GEOMETRY) or (None, None)
        else:
            lat, lon = parse_coord(row.get(mapping["latitude"])), parse_coord(row.get(mapping["longitude"]))
        if lat is None or lon is None:
            out.invalid.append({"line": line, "code": code, "reason": "coordonnées absentes ou illisibles"})
            continue
        in_dz = LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]
        if not in_dz:
            if LAT_RANGE[0] <= lon <= LAT_RANGE[1] and LON_RANGE[0] <= lat <= LON_RANGE[1]:
                out.fixes.append({"line": line, "code": code,
                                  "fix": f"latitude et longitude inversées ({lat}, {lon}) : corrigé"})
                lat, lon = lon, lat
            else:
                out.invalid.append({"line": line, "code": code, "reason": f"coordonnées hors Algérie ({lat}, {lon})"})
                continue
        seen[code] = line
        g = lambda t: clean(row.get(mapping[t])) if mapping.get(t) else None  # noqa: E731
        attrs = {k: v for k, v in row.items()
                 if not k.startswith("__") and k not in mapped and clean(v) is not None}
        out.sites.append(RefSite(
            code=code, name=g("name"), lat=round(lat, 7), lon=round(lon, 7), wilaya_label=g("wilaya"),
            commune=g("commune"), address=g("address"), dr=g("dr"),
            lifecycle=(g("lifecycle") or "").lower() or None,
            technologies=parse_technologies(row.get(mapping["technologies"])) if mapping.get("technologies") else [],
            attributes=attrs, line=line,
        ))
    return out


# --------------------------------------------------------------------------- wilayas
# Variantes rencontrées dans les référentiels d'opérateurs (comparaison sans accents ni ponctuation)
WILAYA_ALIASES = {
    "alger centre": 16, "alger est": 16, "alger ouest": 16, "alger": 16, "algiers": 16,
    "el menia": 58, "el meniaa": 58, "el menea": 58,
    "el meghaier": 57, "el mghair": 57, "el m ghair": 57, "el mghaier": 57,
    "bordj bou arreridj": 34, "b b arreridj": 34, "bba": 34,
    "ain salah": 53, "in salah": 53, "ain guezzam": 54, "in guezzam": 54, "in guezam": 54,
    "tamanghasset": 11, "tamenghest": 11, "bechar": 8, "beni abbes": 52, "bordj badji mokhtar": 50,
    "bbm": 50, "oum el bouaghi": 4, "oeb": 4, "sidi bel abbes": 22, "sba": 22, "tizi ouzou": 15,
    "ain temouchent": 46, "ain defla": 44, "el oued": 39, "souf": 39, "naama": 45, "msila": 28, "m sila": 28,
}


def build_wilaya_resolver(wilayas: list[tuple[int, str, str | None]]):
    """wilayas : [(code, nom, chef-lieu)] -> fonction label -> code ou None."""
    table = {_key(k): v for k, v in WILAYA_ALIASES.items()}
    for code, name, chef in wilayas:
        table.setdefault(_key(name), code)
        if chef:
            table.setdefault(_key(chef), code)

    def resolve(label: str | None) -> int | None:
        if not label:
            return None
        s = label.strip()
        m = re.match(r"^(\d{1,2})(?:\s*[-.:]\s*|\s+|$)", s)
        if m and 1 <= int(m.group(1)) <= 69:
            return int(m.group(1))
        k = _key(s)
        if k in table:
            return table[k]
        k2 = re.sub(r"^(wilaya( de)?|w) ", "", k)
        return table.get(k2)
    return resolve
