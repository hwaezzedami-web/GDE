"""Lecture des fichiers de référentiel de sites : KMZ, KML, Excel (xlsx), CSV, GeoJSON.

Chaque lecteur renvoie un ParsedTable : la liste des colonnes rencontrées et une
ligne (dict) par site, avec la géométrie du point quand le format en porte une.

Sécurité (fichiers fournis par les utilisateurs) :
  - XML lu avec defusedxml (pas de DTD, pas d'entités externes ni d'expansion) ;
  - archives (KMZ) : taille décompressée plafonnée (protection « zip bomb ») ;
  - nombre de lignes plafonné ; aucune exécution de contenu (formules Excel lues en valeur).
"""
from __future__ import annotations

import csv
import html
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime

from defusedxml import ElementTree as SafeET

MAX_ROWS = 300_000
MAX_UNCOMPRESSED = 400 * 1024 * 1024
GEOMETRY = "__geometry__"          # pseudo-colonne : coordonnées du point (KML / GeoJSON)
PLACEMARK_NAME = "__placemark__"   # pseudo-colonne : nom du repère KML

_TR_TH_TD = re.compile(r"<tr[^>]*>\s*<t[hd][^>]*>(.*?)</t[hd]>\s*<td[^>]*>(.*?)</td>\s*</tr>", re.I | re.S)
_TAGS = re.compile(r"<[^>]+>")


class ReferenceFileError(ValueError):
    pass


@dataclass
class ParsedTable:
    format: str
    columns: list[str]
    rows: list[dict]
    has_geometry: bool = False
    sheet: str | None = None
    warnings: list[str] = field(default_factory=list)


def _clean(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        if v != v:            # NaN
            return None
        return str(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    s = str(v)
    s = html.unescape(_TAGS.sub("", s)) if "<" in s else s
    s = s.replace("\xa0", " ").strip()
    return s or None


def _ordered_columns(rows: list[dict]) -> list[str]:
    seen: dict[str, None] = {}
    for r in rows[:5000]:
        for k in r:
            if not k.startswith("__"):
                seen.setdefault(k, None)
    return list(seen)


# --------------------------------------------------------------------------- KML / KMZ
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_kml(stream) -> ParsedTable:
    rows: list[dict] = []
    warnings: list[str] = []
    try:
        for _event, el in SafeET.iterparse(stream, events=("end",), forbid_dtd=True):
            if _local(el.tag) != "Placemark":
                continue
            row: dict = {}
            desc = None
            for child in el.iter():
                t = _local(child.tag)
                if t == "name" and PLACEMARK_NAME not in row:
                    row[PLACEMARK_NAME] = _clean(child.text)
                elif t == "description" and desc is None:
                    desc = child.text or ""
                elif t == "Data":                      # <ExtendedData><Data name=…><value>
                    val = next((c.text for c in child if _local(c.tag) == "value"), None)
                    if child.get("name"):
                        row[child.get("name").strip()] = _clean(val)
                elif t == "SimpleData" and child.get("name"):
                    row[child.get("name").strip()] = _clean(child.text)
                elif t == "coordinates" and GEOMETRY not in row and child.text:
                    first = child.text.strip().split()[0].split(",")
                    try:
                        row[GEOMETRY] = (float(first[1]), float(first[0]))   # (lat, lon)
                    except (ValueError, IndexError):
                        pass
            if desc:
                for k, v in _TR_TH_TD.findall(desc):
                    key = _clean(k)
                    if key and key not in row:
                        row[key] = _clean(v)
            rows.append(row)
            el.clear()
            if len(rows) > MAX_ROWS:
                raise ReferenceFileError(f"Fichier trop volumineux (plus de {MAX_ROWS} repères)")
    except SafeET.ParseError as exc:
        raise ReferenceFileError(f"KML illisible : {exc}") from exc
    except (SafeET.DTDForbidden, SafeET.EntitiesForbidden, SafeET.ExternalReferenceForbidden) as exc:
        raise ReferenceFileError("KML refusé : déclarations DTD / entités interdites") from exc
    if not rows:
        raise ReferenceFileError("Aucun repère (Placemark) trouvé dans le fichier KML")
    return ParsedTable("kml", _ordered_columns(rows), rows, has_geometry=any(GEOMETRY in r for r in rows),
                       warnings=warnings)


def parse_kmz(content: bytes) -> ParsedTable:
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ReferenceFileError("Archive KMZ illisible") from exc
    kmls = [i for i in zf.infolist() if i.filename.lower().endswith(".kml") and not i.is_dir()]
    if not kmls:
        raise ReferenceFileError("Aucun fichier .kml dans l'archive KMZ")
    info = next((i for i in kmls if i.filename.lower().endswith("doc.kml")), kmls[0])
    if info.file_size > MAX_UNCOMPRESSED:
        raise ReferenceFileError("KML décompressé trop volumineux")
    with zf.open(info) as fh:
        data = fh.read(MAX_UNCOMPRESSED + 1)
    if len(data) > MAX_UNCOMPRESSED:
        raise ReferenceFileError("KML décompressé trop volumineux")
    t = parse_kml(io.BytesIO(data))
    t.format = "kmz"
    return t


# --------------------------------------------------------------------------- Excel
def parse_xlsx(content: bytes, sheet: str | None = None) -> ParsedTable:
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # fichier corrompu, chiffré, format non xlsx
        raise ReferenceFileError(f"Classeur Excel illisible ({exc.__class__.__name__}) — format .xlsx attendu") from exc
    try:
        sheets = wb.sheetnames
        if sheet and sheet not in sheets:
            raise ReferenceFileError(f"Feuille « {sheet} » absente (feuilles : {', '.join(sheets)})")
        ws = wb[sheet] if sheet else None
        if ws is None:   # feuille la plus remplie parmi les 10 premières
            ws = max((wb[n] for n in sheets[:10]), key=lambda w: (w.max_row or 0) * (w.max_column or 0))
        it = ws.iter_rows(values_only=True)
        header, skipped = None, 0
        for raw in it:
            vals = [_clean(v) for v in raw]
            if sum(1 for v in vals if v) >= 2:
                header = [v or f"Colonne {i + 1}" for i, v in enumerate(vals)]
                break
            skipped += 1
            if skipped > 20:
                break
        if not header:
            raise ReferenceFileError("Ligne d'en-tête introuvable dans les 20 premières lignes")
        rows = []
        for raw in it:
            vals = [_clean(v) for v in raw]
            if not any(vals):
                continue
            rows.append({header[i]: v for i, v in enumerate(vals[:len(header)]) if v is not None})
            if len(rows) > MAX_ROWS:
                raise ReferenceFileError(f"Fichier trop volumineux (plus de {MAX_ROWS} lignes)")
        return ParsedTable("xlsx", [h for h in header if h], rows, sheet=ws.title)
    finally:
        wb.close()


# --------------------------------------------------------------------------- CSV
def parse_csv(content: bytes) -> ParsedTable:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text_data = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    lines = [ln for ln in text_data.splitlines() if not ln.lstrip().startswith("#")]
    text_data = "\n".join(lines)
    try:
        dialect = csv.Sniffer().sniff(text_data[:8192], delimiters=";,\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text_data), dialect=dialect)
    if not reader.fieldnames:
        raise ReferenceFileError("Fichier CSV vide ou sans en-tête")
    rows = []
    for r in reader:
        row = {(k or "").strip(): _clean(v) for k, v in r.items() if k}
        if any(row.values()):
            rows.append({k: v for k, v in row.items() if v is not None})
        if len(rows) > MAX_ROWS:
            raise ReferenceFileError(f"Fichier trop volumineux (plus de {MAX_ROWS} lignes)")
    return ParsedTable("csv", [f.strip() for f in reader.fieldnames if f and f.strip()], rows)


# --------------------------------------------------------------------------- GeoJSON
def parse_geojson(content: bytes) -> ParsedTable:
    try:
        data = json.loads(content.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ReferenceFileError("GeoJSON illisible") from exc
    feats = data.get("features") if isinstance(data, dict) else None
    if not isinstance(feats, list):
        raise ReferenceFileError("FeatureCollection GeoJSON attendue")
    rows = []
    for f in feats[:MAX_ROWS + 1]:
        props = f.get("properties") or {}
        row = {str(k): _clean(v) for k, v in props.items() if not isinstance(v, (dict, list))}
        g = f.get("geometry") or {}
        if g.get("type") == "Point" and isinstance(g.get("coordinates"), list) and len(g["coordinates"]) >= 2:
            row[GEOMETRY] = (float(g["coordinates"][1]), float(g["coordinates"][0]))
        rows.append({k: v for k, v in row.items() if v is not None})
    if len(rows) > MAX_ROWS:
        raise ReferenceFileError(f"Fichier trop volumineux (plus de {MAX_ROWS} entités)")
    return ParsedTable("geojson", _ordered_columns(rows), rows, has_geometry=any(GEOMETRY in r for r in rows))


# --------------------------------------------------------------------------- aiguillage
def read_reference_file(filename: str, content: bytes, sheet: str | None = None) -> ParsedTable:
    name = (filename or "").lower()
    is_zip = content[:4] == b"PK\x03\x04"
    if name.endswith(".kmz") or (is_zip and not name.endswith((".xlsx", ".xlsm"))
                                 and b".kml" in content[:4096].lower()):
        return parse_kmz(content)
    if name.endswith((".xlsx", ".xlsm")) or (is_zip and b"[Content_Types].xml" in content[:4096]):
        return parse_xlsx(content, sheet)
    if name.endswith(".xls"):
        raise ReferenceFileError("Format Excel 97-2003 (.xls) non pris en charge : enregistrer en .xlsx")
    if name.endswith(".kml") or content.lstrip()[:200].lower().startswith((b"<?xml", b"<kml")):
        return parse_kml(io.BytesIO(content))
    if name.endswith((".geojson", ".json")):
        return parse_geojson(content)
    if name.endswith((".csv", ".txt")):
        return parse_csv(content)
    raise ReferenceFileError("Format non reconnu : KMZ, KML, XLSX, CSV ou GeoJSON attendu")
