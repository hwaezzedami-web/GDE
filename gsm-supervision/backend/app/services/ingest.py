"""Ingestion d'une collecte : rapprochement des codes, upserts, complétude, journal.

Règles :
- l'horodatage d'observation vient de la collecte (date des données), pas de l'heure de lecture ;
- pour un site du référentiel, nom, position, wilaya, commune et adresse priment ; le nom OMC est gardé
  dans ``extra.omc_name`` ;
- un site du référentiel n'est jamais désactivé par une collecte ;
- un site inconnu remonté par un OMC est créé hors référentiel ;
- si la collecte est complète, les éléments et alarmes absents de l'instantané sont désactivés / terminés.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..collector.connectors.base import SourceSpec
from ..collector.model import CollectResult, NSite
from ..collector.normalize import normalize_severity, normalize_technology


@dataclass
class IngestStats:
    sites_created: int = 0
    sites_updated: int = 0
    elements: int = 0
    elements_deactivated: int = 0
    alarms: int = 0
    alarms_cleared: int = 0
    unmapped: int = 0
    site_ids: set[int] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)


def canonical_site_codes(session: Session, codes: Iterable[str]) -> dict[str, str | None]:
    """Code OMC -> code du référentiel.

    Ordre : alias explicite (``site_code_aliases``), puis correspondance exacte, puis zéros de tête
    (uniquement si elle est unique). Un code inconnu est gardé tel quel (nouveau site hors référentiel).
    Un code ambigu donne None (non rapproché).
    """
    wanted = sorted({c for c in codes if c})
    if not wanted:
        return {}
    aliases = {
        r.omc_code: r.site_code
        for r in session.execute(
            text("SELECT omc_code, site_code FROM site_code_aliases WHERE omc_code = ANY(:c)"), {"c": wanted}
        )
    }
    existing = set(
        session.scalars(text("SELECT external_id FROM sites WHERE external_id = ANY(:c)"), {"c": wanted})
    )
    resolved: dict[str, str | None] = {}
    for code in wanted:
        if code in aliases:
            resolved[code] = aliases[code]
        elif code in existing:
            resolved[code] = code
        else:
            stripped = code.lstrip("0")
            matches = (
                session.scalars(
                    text("SELECT external_id FROM sites WHERE ltrim(external_id, '0') = :s LIMIT 2"),
                    {"s": stripped},
                ).all()
                if stripped
                else []
            )
            if len(matches) == 1:
                resolved[code] = matches[0]
            elif len(matches) > 1:
                resolved[code] = None
            else:
                resolved[code] = code
    return resolved


SITE_UPSERT = text(
    """
    INSERT INTO sites (external_id, name, geom, wilaya_code, commune, address, extra,
                       active, in_reference, created_at, updated_at)
    VALUES (:ext, :name,
            CASE WHEN CAST(:lon AS double precision) IS NULL THEN NULL
                 ELSE ST_SetSRID(ST_MakePoint(CAST(:lon AS double precision),
                                              CAST(:lat AS double precision)), 4326) END,
            :wilaya, :commune, :address, CAST(:extra AS jsonb), true, false, now(), now())
    ON CONFLICT (external_id) DO UPDATE SET
        name = CASE WHEN sites.in_reference THEN sites.name ELSE COALESCE(EXCLUDED.name, sites.name) END,
        geom = CASE WHEN sites.in_reference THEN sites.geom ELSE COALESCE(EXCLUDED.geom, sites.geom) END,
        wilaya_code = CASE WHEN sites.in_reference THEN sites.wilaya_code
                           ELSE COALESCE(EXCLUDED.wilaya_code, sites.wilaya_code) END,
        commune = CASE WHEN sites.in_reference THEN sites.commune ELSE COALESCE(EXCLUDED.commune, sites.commune) END,
        address = CASE WHEN sites.in_reference THEN sites.address ELSE COALESCE(EXCLUDED.address, sites.address) END,
        extra = sites.extra || CAST(:extra AS jsonb),
        active = true,
        updated_at = now()
    RETURNING (xmax = 0) AS inserted
    """
)

ELEMENT_UPSERT = text(
    """
    INSERT INTO site_elements (site_id, source_id, ne_id, ne_name, ne_type, technology, raw_status,
                               observed_at, active, created_at, updated_at)
    VALUES (:site_id, :source_id, :ne_id, :ne_name, :ne_type, :technology, :raw_status,
            :observed_at, true, now(), now())
    ON CONFLICT (source_id, ne_id) DO UPDATE SET
        site_id = EXCLUDED.site_id,
        ne_name = COALESCE(EXCLUDED.ne_name, site_elements.ne_name),
        ne_type = COALESCE(EXCLUDED.ne_type, site_elements.ne_type),
        technology = EXCLUDED.technology,
        raw_status = EXCLUDED.raw_status,
        observed_at = GREATEST(site_elements.observed_at, EXCLUDED.observed_at),
        active = true,
        updated_at = now()
    """
)

ALARM_UPSERT = text(
    """
    INSERT INTO alarms (source_id, omc_alarm_id, site_id, element_id, ne_id, code, severity,
                        description, raised_at, is_active, last_seen_at)
    VALUES (:source_id, :omc_alarm_id, :site_id, :element_id, :ne_id, :code, :severity,
            :description, :raised_at, true, :last_seen_at)
    ON CONFLICT (source_id, omc_alarm_id) DO UPDATE SET
        site_id = EXCLUDED.site_id,
        element_id = EXCLUDED.element_id,
        ne_id = EXCLUDED.ne_id,
        code = EXCLUDED.code,
        severity = EXCLUDED.severity,
        description = EXCLUDED.description,
        raised_at = COALESCE(alarms.raised_at, EXCLUDED.raised_at),
        is_active = true,
        cleared_at = NULL,
        last_seen_at = EXCLUDED.last_seen_at
    """
)


def _site_ids(session: Session, codes: Iterable[str]) -> dict[str, int]:
    codes = list(codes)
    if not codes:
        return {}
    rows = session.execute(text("SELECT external_id, id FROM sites WHERE external_id = ANY(:c)"), {"c": codes})
    return {r.external_id: r.id for r in rows}


def _upsert_site(session: Session, target: str, src: NSite | None) -> bool:
    """Renvoie True si le site vient d'être créé."""
    src = src or NSite(external_id=target)
    row = session.execute(
        SITE_UPSERT,
        {
            "ext": target,
            "name": src.name,
            "lat": src.lat,
            "lon": src.lon,
            "wilaya": src.wilaya_code,
            "commune": src.commune,
            "address": src.address,
            "extra": json.dumps({"omc_name": src.name} if src.name else {}, ensure_ascii=False),
        },
    ).one()
    return bool(row.inserted)


def ingest(session: Session, source: SourceSpec, result: CollectResult, now: datetime) -> IngestStats:
    stats = IngestStats(warnings=list(result.warnings))
    observed = result.observed_at

    # Sites touchés précédemment par cette source (utile pour la désactivation).
    previously = set(
        session.scalars(
            text("SELECT DISTINCT site_id FROM site_elements WHERE source_id = :s"), {"s": source.id}
        )
    )

    # 1. Rapprochement des codes ------------------------------------------------
    codes = (
        {s.external_id for s in result.sites}
        | {e.site_id for e in result.elements}
        | {a.site_id for a in result.alarms if a.site_id}
    )
    resolved = canonical_site_codes(session, codes)
    by_code = {s.external_id: s for s in result.sites}

    # 2. Sites --------------------------------------------------------------------
    targets: dict[str, NSite | None] = {}
    for code, target in resolved.items():
        if target is None:
            stats.unmapped += 1
            stats.warnings.append(f"Code site ambigu, non rapproché : {code}")
            continue
        targets.setdefault(target, None)
        if code in by_code:
            targets[target] = by_code[code]
    for target in sorted(targets):
        if _upsert_site(session, target, targets[target]):
            stats.sites_created += 1
        else:
            stats.sites_updated += 1
    site_ids = _site_ids(session, targets.keys())

    # 3. Éléments -------------------------------------------------------------------
    element_rows, ne_ids = [], []
    for e in result.elements:
        target = resolved.get(e.site_id)
        if target is None or target not in site_ids:
            continue
        ne_ids.append(e.ne_id)
        element_rows.append(
            {
                "site_id": site_ids[target],
                "source_id": source.id,
                "ne_id": e.ne_id,
                "ne_name": e.ne_name,
                "ne_type": e.ne_type,
                "technology": normalize_technology(e.technology),
                "raw_status": e.raw_status,
                "observed_at": e.observed_at or observed,
            }
        )
    if element_rows:
        session.execute(ELEMENT_UPSERT, element_rows)
    stats.elements = len(element_rows)

    if result.elements_complete:
        deactivated = session.scalars(
            text(
                """
                UPDATE site_elements SET active = false, updated_at = now()
                 WHERE source_id = :s AND active AND ne_id <> ALL(CAST(:ids AS text[]))
                RETURNING site_id
                """
            ),
            {"s": source.id, "ids": ne_ids},
        ).all()
        stats.elements_deactivated = len(deactivated)
        stats.site_ids |= set(deactivated)

    # 4. Alarmes ------------------------------------------------------------------
    ne_lookup = {
        r.ne_id: r.id
        for r in session.execute(
            text("SELECT ne_id, id FROM site_elements WHERE source_id = :s AND ne_id = ANY(:ids)"),
            {"s": source.id, "ids": ne_ids or [""]},
        )
    }
    alarm_rows, alarm_ids = [], []
    for a in result.alarms:
        target = resolved.get(a.site_id) if a.site_id else None
        alarm_ids.append(a.alarm_id)
        alarm_rows.append(
            {
                "source_id": source.id,
                "omc_alarm_id": a.alarm_id,
                "site_id": site_ids.get(target) if target else None,
                "element_id": ne_lookup.get(a.ne_id) if a.ne_id else None,
                "ne_id": a.ne_id,
                "code": a.code,
                "severity": normalize_severity(a.severity),
                "description": a.description,
                "raised_at": a.raised_at,
                "last_seen_at": observed,
            }
        )
    if alarm_rows:
        session.execute(ALARM_UPSERT, alarm_rows)
    stats.alarms = len(alarm_rows)

    if result.alarms_complete:
        cleared = session.scalars(
            text(
                """
                UPDATE alarms SET is_active = false, cleared_at = :now
                 WHERE source_id = :s AND is_active AND omc_alarm_id <> ALL(CAST(:ids AS text[]))
                RETURNING site_id
                """
            ),
            {"s": source.id, "now": now, "ids": alarm_ids},
        ).all()
        stats.alarms_cleared = len(cleared)
        stats.site_ids |= {c for c in cleared if c is not None}

    # 5. Présence OMC : un site est supervisé s'il a au moins un élément actif ----
    touched = previously | set(site_ids.values())
    stats.site_ids |= touched
    if touched:
        session.execute(
            text(
                """
                UPDATE sites s SET
                    is_supervised = EXISTS (SELECT 1 FROM site_elements e WHERE e.site_id = s.id AND e.active),
                    last_supervised_at = CASE
                        WHEN EXISTS (SELECT 1 FROM site_elements e
                                      WHERE e.site_id = s.id AND e.active AND e.source_id = :src)
                        THEN :obs ELSE s.last_supervised_at END
                 WHERE s.id = ANY(:ids)
                """
            ),
            {"src": source.id, "obs": observed, "ids": sorted(touched)},
        )
    return stats
