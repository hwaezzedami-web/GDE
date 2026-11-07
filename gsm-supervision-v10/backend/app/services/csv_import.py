"""Import d'un fichier CSV de sites (étape 2 du projet : données de test / initialisation).

Format attendu (séparateur ; ou , détecté automatiquement, UTF-8) :

  Colonnes obligatoires :
    site_code, site_name, latitude, longitude, vendor, technologies
  Colonnes optionnelles :
    wilaya_code, wilaya, commune, address, status, tech_status, omc_source,
    last_update, alarm_code, alarm_text, alarm_severity

  technologies : liste séparée par | (ex. 2G|3G|4G)
  status       : UP | DOWN | DEGRADED | UNKNOWN (état global du site)
  tech_status  : détail par technologie, prioritaire sur status (ex. 2G:UP|4G:DOWN)
  omc_source   : code de la source ; créée en type manual_csv si elle n'existe pas

Le fichier d'exemple data/test/sites_fictifs.csv suit ce format.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..collector.model import CollectResult, NAlarm, NElement, NSite
from ..collector.normalize import map_severity, map_status, map_technology, parse_datetime, parse_float, split_list
from ..models import VENDORS, OmcSource
from .ingest import LAT_RANGE, LON_RANGE, ingest

REQUIRED = {"site_code", "site_name", "latitude", "longitude", "vendor", "technologies"}
ELEMENT_TYPE = {"2G": "BTS", "3G": "NODEB", "4G": "ENODEB", "5G": "GNODEB"}


@dataclass
class ImportReport:
    rows: int = 0
    accepted: int = 0
    rejected: list[str] = field(default_factory=list)
    sources: dict[str, dict] = field(default_factory=dict)


def _sniff(text_data: str) -> csv.Dialect | type[csv.Dialect]:
    sample = text_data[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=";,\t")
    except csv.Error:
        return csv.excel


def parse_sites_csv(content: bytes | str, default_source: str = "IMPORT-CSV"
                    ) -> tuple[dict[tuple[str, str], CollectResult], ImportReport]:
    """Analyse le CSV et le découpe par (code source, équipementier)."""
    text_data = content.decode("utf-8-sig") if isinstance(content, bytes) else content.lstrip("﻿")
    # Les lignes commençant par # sont des commentaires (ex. mention « données fictives »)
    text_data = "\n".join(line for line in text_data.splitlines() if not line.lstrip().startswith("#"))
    reader = csv.DictReader(io.StringIO(text_data), dialect=_sniff(text_data))
    if not reader.fieldnames:
        raise ValueError("Fichier vide ou sans en-tête")
    headers = {h.strip().lower() for h in reader.fieldnames if h}
    missing = REQUIRED - headers
    if missing:
        raise ValueError("Colonnes obligatoires manquantes : " + ", ".join(sorted(missing)))

    report = ImportReport()
    results: dict[tuple[str, str], CollectResult] = {}
    now = datetime.now(timezone.utc)
    for i, raw in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        report.rows += 1
        try:
            code = row["site_code"]
            if not code:
                raise ValueError("site_code vide")
            vendor = row["vendor"].upper()
            if vendor not in VENDORS:
                raise ValueError(f"vendor {row['vendor']!r} invalide (ERICSSON, HUAWEI ou ZTE)")
            lat, lon = parse_float(row["latitude"]), parse_float(row["longitude"])
            if lat is None or lon is None:
                raise ValueError("coordonnées manquantes")
            if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]):
                raise ValueError(f"coordonnées hors Algérie ({lat}, {lon})")
            techs = []
            for t in split_list(row["technologies"], "|;/ "):
                nt = map_technology(t)
                if not nt:
                    raise ValueError(f"technologie {t!r} inconnue")
                techs.append(nt)
            techs = sorted(set(techs))
            if not techs:
                raise ValueError("aucune technologie")
            observed = parse_datetime(row.get("last_update")) if row.get("last_update") else now

            per_tech: dict[str, str] = {}
            if row.get("tech_status"):
                for part in split_list(row["tech_status"], "|;"):
                    t, _, s = part.partition(":")
                    nt, ns = map_technology(t), map_status(s)
                    if nt and ns:
                        per_tech[nt] = ns
            site_status = map_status(row.get("status")) or "UNKNOWN"
            for idx, t in enumerate(techs):
                if t in per_tech:
                    continue
                if site_status == "DEGRADED":
                    # Convention d'import : la technologie la plus récente est en panne
                    per_tech[t] = "DOWN" if idx == len(techs) - 1 and len(techs) > 1 else (
                        "DEGRADED" if len(techs) == 1 else "UP")
                else:
                    per_tech[t] = site_status

            wcode = row.get("wilaya_code")
            src = (row.get("omc_source") or default_source).upper()
            res = results.setdefault((src, vendor), CollectResult())
            res.sites.append(NSite(
                external_id=code, name=row["site_name"] or code, latitude=lat, longitude=lon,
                wilaya_code=int(wcode) if wcode and wcode.isdigit() else None,
                wilaya_name=row.get("wilaya") or None, commune=row.get("commune") or None,
                address=row.get("address") or None,
                extra={"import_line": i},
            ))
            for t in techs:
                res.elements.append(NElement(
                    external_id=f"{code}-{t}", site_external_id=code, technology=t,
                    element_type=ELEMENT_TYPE[t], name=f"{code}_{t}",
                    oper_status=per_tech[t], raw_status=f"import:{per_tech[t]}", observed_at=observed,
                ))
            if row.get("alarm_code") or row.get("alarm_text"):
                res.alarms.append(NAlarm(
                    external_alarm_id=f"{code}-{row.get('alarm_code') or 'ALM'}",
                    site_external_id=code, alarm_code=row.get("alarm_code") or None,
                    description=row.get("alarm_text") or None,
                    severity=map_severity(row.get("alarm_severity")), raised_at=observed,
                ))
            report.accepted += 1
        except (ValueError, KeyError) as exc:
            report.rejected.append(f"Ligne {i} : {exc}")
    return results, report


def import_sites_csv(db: Session, content: bytes | str, default_source: str = "IMPORT-CSV",
                     connector_type: str = "manual_csv", is_demo: bool = False,
                     poll_interval_s: int = 300) -> ImportReport:
    results, report = parse_sites_csv(content, default_source)
    for (src_code, vendor), res in results.items():
        source = db.scalar(select(OmcSource).where(OmcSource.code == src_code))
        if source is None:
            source = OmcSource(
                code=src_code, name=f"{src_code} ({'données fictives' if is_demo else 'import CSV'})",
                vendor=vendor, connector_type=connector_type, enabled=connector_type == "demo",
                is_demo=is_demo, poll_interval_s=poll_interval_s,
                stale_after_s=None if connector_type == "manual_csv" else max(600, poll_interval_s * 4),
                config={},
            )
            db.add(source)
            db.flush()
        elif source.vendor != vendor:
            report.rejected.append(
                f"Source {src_code} : équipementier {vendor} différent de celui de la source ({source.vendor})")
            continue
        stats = ingest(db, source, res)
        source.last_success_at = datetime.now(timezone.utc)
        source.last_status = "SUCCESS"
        report.sources[src_code] = stats.as_dict()
        report.rejected.extend(m for m in stats.messages if "rejeté" in m)
    return report
