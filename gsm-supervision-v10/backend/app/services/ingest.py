"""Écriture en base d'un résultat de collecte normalisé (upserts sans doublons).

Clés d'unicité utilisées :
  - sites          : external_id (code site opérateur)
  - site_elements  : (omc_source_id, external_id)
  - alarms         : (omc_source_id, external_alarm_id)
Une même collecte rejouée deux fois produit donc exactement le même état.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..collector.model import CollectResult
from ..collector.normalize import norm_key
from ..models import SEVERITIES, STATUSES, TECHNOLOGIES, OmcSource
from .settings_service import get_setting
from .status_engine import evaluate_sites

log = logging.getLogger(__name__)

LAT_RANGE = (18.0, 38.5)
LON_RANGE = (-9.5, 12.5)


@dataclass
class IngestStats:
    sites: int = 0
    elements: int = 0
    alarms: int = 0
    rejected: int = 0
    element_transitions: int = 0
    site_transitions: int = 0
    deactivated_elements: int = 0
    cleared_alarms: int = 0
    messages: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["messages"] = self.messages[:200]
        return d


def _wilaya_lookup(db: Session) -> tuple[set[int], dict[str, int]]:
    rows = db.execute(text("SELECT code, name, chef_lieu FROM wilayas")).all()
    codes = {r[0] for r in rows}
    names: dict[str, int] = {}
    for code, name, chef in rows:
        names[norm_key(name)] = code
        if chef:
            names.setdefault(norm_key(chef), code)
    return codes, names


def canonical_site_codes(db: Session, codes: set[str]) -> dict[str, str]:
    """Code remonté par l'OMC -> code du site du référentiel.

    1. Correspondances explicites (table site_code_aliases, créées depuis l'écran « Sites inconnus ») ;
    2. zéros de tête (« 5474 » OMC, « 05474 » référentiel), si le paramètre est actif, que la
       correspondance est unique et que le code OMC n'est pas déjà connu tel quel."""
    codes = {c for c in codes if c}
    if not codes:
        return {}
    out = dict(db.execute(text("SELECT omc_code, site_external_id FROM site_code_aliases WHERE omc_code = ANY(:c)"),
                          {"c": list(codes)}).all())
    rest = codes - set(out)
    if not rest or not get_setting(db, "reference")["match_leading_zeros"]:
        return out
    known = {r[0] for r in db.execute(text("SELECT external_id FROM sites WHERE external_id = ANY(:c)"),
                                      {"c": list(rest)})}
    todo = {c: c.lstrip("0") for c in rest - known if c.lstrip("0")}
    if not todo:
        return out
    found = {k: (ext, n) for k, ext, n in db.execute(text("""
        SELECT ltrim(external_id, '0'), min(external_id), count(*) FROM sites
        WHERE in_reference AND ltrim(external_id, '0') = ANY(:k) GROUP BY 1"""), {"k": list(set(todo.values()))})}
    out.update({c: found[k][0] for c, k in todo.items() if k in found and found[k][1] == 1})
    return out


def ingest(db: Session, source: OmcSource, result: CollectResult,
           now: datetime | None = None, evaluate: bool = True) -> IngestStats:
    """Intègre le résultat. N'effectue pas de commit (transaction gérée par l'appelant)."""
    now = now or datetime.now(timezone.utc)
    st = IngestStats(rejected=len(result.rejected))
    st.messages.extend(result.rejected[:100])
    st.messages.extend(result.warnings[:100])
    codes, names = _wilaya_lookup(db)

    # Codes OMC -> codes du référentiel (zéros de tête)
    canon = canonical_site_codes(db, {(x.external_id or "").strip() for x in result.sites}
                                 | {(e.site_external_id or "").strip() for e in result.elements}
                                 | {(a.site_external_id or "").strip() for a in result.alarms})
    if canon:
        for x in result.sites:
            x.external_id = canon.get((x.external_id or "").strip(), x.external_id)
        for e in result.elements:
            e.site_external_id = canon.get((e.site_external_id or "").strip(), e.site_external_id)
        for a in result.alarms:
            if a.site_external_id:
                a.site_external_id = canon.get(a.site_external_id.strip(), a.site_external_id)
        st.messages.append(f"{len(canon)} code(s) site rapproché(s) du référentiel (correspondances, zéros de tête), "
                           f"ex. {next(iter(canon))} -> {next(iter(canon.values()))}")

    # ------------------------------------------------------------------ sites
    site_rows = {}
    for s in result.sites:
        ext = (s.external_id or "").strip()
        if not ext:
            st.rejected += 1
            st.messages.append("Site sans identifiant rejeté")
            continue
        lat, lon = s.latitude, s.longitude
        if lat is not None and lon is not None:
            if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]):
                st.messages.append(f"Site {ext} : coordonnées hors Algérie ({lat}, {lon}) ignorées")
                lat = lon = None
        else:
            lat = lon = None
        wcode = s.wilaya_code if s.wilaya_code in codes else None
        if wcode is None and s.wilaya_name:
            wcode = names.get(norm_key(s.wilaya_name))
        site_rows[ext] = {
            "ext": ext,
            "name": (s.name or ext)[:200],
            "name_given": bool(s.name),
            "vendor": source.vendor,
            "src": source.id,
            "wilaya": wcode,
            "commune": s.commune,
            "address": s.address,
            "lat": lat,
            "lon": lon,
            "extra": json.dumps(s.extra or {}, default=str),
        }
    if site_rows:
        db.execute(text("""
            INSERT INTO sites (external_id, name, vendor, primary_source_id, wilaya_code, commune,
                               address, latitude, longitude, extra, status_since)
            VALUES (:ext, :name, :vendor, :src, :wilaya, :commune, :address, :lat, :lon,
                    CAST(:extra AS jsonb), now())
            ON CONFLICT (external_id) DO UPDATE SET
                -- Le référentiel de sites fait foi pour le nom, la position et la localisation
                name        = CASE WHEN sites.in_reference THEN sites.name
                                   WHEN CAST(:name_given AS boolean) THEN EXCLUDED.name ELSE sites.name END,
                wilaya_code = CASE WHEN sites.in_reference THEN COALESCE(sites.wilaya_code, EXCLUDED.wilaya_code)
                                   ELSE COALESCE(EXCLUDED.wilaya_code, sites.wilaya_code) END,
                commune     = CASE WHEN sites.in_reference THEN COALESCE(sites.commune, EXCLUDED.commune)
                                   ELSE COALESCE(EXCLUDED.commune, sites.commune) END,
                address     = CASE WHEN sites.in_reference THEN COALESCE(sites.address, EXCLUDED.address)
                                   ELSE COALESCE(EXCLUDED.address, sites.address) END,
                latitude    = CASE WHEN sites.in_reference AND sites.latitude IS NOT NULL THEN sites.latitude
                                   ELSE COALESCE(EXCLUDED.latitude, sites.latitude) END,
                longitude   = CASE WHEN sites.in_reference AND sites.latitude IS NOT NULL THEN sites.longitude
                                   ELSE COALESCE(EXCLUDED.longitude, sites.longitude) END,
                extra       = sites.extra || EXCLUDED.extra
                              || CASE WHEN sites.in_reference AND CAST(:name_given AS boolean)
                                           AND EXCLUDED.name <> sites.name
                                      THEN jsonb_build_object('omc_name', EXCLUDED.name) ELSE '{}'::jsonb END,
                primary_source_id = COALESCE(sites.primary_source_id, EXCLUDED.primary_source_id),
                is_active   = TRUE,
                updated_at  = now()
        """), list(site_rows.values()))
        st.sites = len(site_rows)
        # Wilaya déduite des coordonnées si les contours administratifs sont chargés
        db.execute(text("""
            UPDATE sites s SET wilaya_code = w.code
            FROM wilayas w
            WHERE s.wilaya_code IS NULL AND s.geom IS NOT NULL AND w.boundary IS NOT NULL
              AND s.external_id = ANY(:exts) AND ST_Covers(w.boundary, s.geom)
        """), {"exts": list(site_rows.keys())})

    # -------------------------------------------------------------- éléments
    needed = {e.site_external_id for e in result.elements} | {
        a.site_external_id for a in result.alarms if a.site_external_id}
    site_ids: dict[str, int] = {}
    if needed:
        for ext, sid in db.execute(text("SELECT external_id, id FROM sites WHERE external_id = ANY(:e)"),
                                   {"e": list(needed)}):
            site_ids[ext] = sid

    existing = {r[0]: (r[1], r[2], r[3]) for r in db.execute(text(
        "SELECT external_id, id, oper_status, site_id FROM site_elements WHERE omc_source_id = :s"),
        {"s": source.id})}

    elem_rows, hist_rows = [], []
    seen_ext = set()
    affected_sites: set[int] = set()
    for e in result.elements:
        ext = (e.external_id or "").strip()
        sid = site_ids.get(e.site_external_id)
        if not ext or sid is None:
            st.rejected += 1
            st.messages.append(f"Équipement {ext or '?'} rejeté : site {e.site_external_id!r} inconnu")
            continue
        if e.technology not in TECHNOLOGIES:
            st.rejected += 1
            st.messages.append(f"Équipement {ext} rejeté : technologie {e.technology!r} non reconnue")
            continue
        status = e.oper_status if e.oper_status in STATUSES else None
        if e.oper_status is not None and status is None:
            st.messages.append(f"Équipement {ext} : état {e.oper_status!r} non reconnu -> UNKNOWN")
            status = "UNKNOWN"
        if ext in seen_ext:
            continue
        seen_ext.add(ext)
        observed = e.observed_at or now
        prev = existing.get(ext)
        if status is not None and prev is not None and prev[1] != status:
            hist_rows.append({"site_id": sid, "eid": prev[0], "old": prev[1], "new": status,
                              "at": observed, "src": source.code, "reason": e.raw_status})
            st.element_transitions += 1
        elem_rows.append({
            "site_id": sid, "src": source.id, "ext": ext, "tech": e.technology,
            "etype": e.element_type or "NE", "name": e.name,
            "has_status": status is not None, "status": status or "UNKNOWN", "raw": e.raw_status,
            "observed": observed if status is not None else None,
            "lastcomm": e.last_communication_at,
            "extra": json.dumps(e.extra or {}, default=str),
        })
        affected_sites.add(sid)
        if prev is not None and prev[2] != sid:
            affected_sites.add(prev[2])

    if elem_rows:
        db.execute(text("""
            INSERT INTO site_elements (site_id, omc_source_id, external_id, technology, element_type, name,
                                       oper_status, raw_status, status_observed_at, status_changed_at,
                                       last_communication_at, extra)
            VALUES (:site_id, :src, :ext, :tech, :etype, :name, :status, :raw, CAST(:observed AS timestamptz),
                    CASE WHEN CAST(:has_status AS boolean) THEN CAST(:observed AS timestamptz) END, :lastcomm, CAST(:extra AS jsonb))
            ON CONFLICT (omc_source_id, external_id) DO UPDATE SET
                site_id      = EXCLUDED.site_id,
                technology   = EXCLUDED.technology,
                element_type = EXCLUDED.element_type,
                name         = COALESCE(EXCLUDED.name, site_elements.name),
                oper_status  = CASE WHEN CAST(:has_status AS boolean) THEN EXCLUDED.oper_status ELSE site_elements.oper_status END,
                raw_status   = CASE WHEN CAST(:has_status AS boolean) THEN EXCLUDED.raw_status ELSE site_elements.raw_status END,
                status_observed_at = CASE WHEN CAST(:has_status AS boolean) THEN EXCLUDED.status_observed_at
                                          ELSE site_elements.status_observed_at END,
                status_changed_at  = CASE WHEN CAST(:has_status AS boolean) AND site_elements.oper_status <> EXCLUDED.oper_status
                                          THEN EXCLUDED.status_observed_at
                                          ELSE COALESCE(site_elements.status_changed_at, EXCLUDED.status_changed_at) END,
                last_communication_at = COALESCE(EXCLUDED.last_communication_at, site_elements.last_communication_at),
                extra        = site_elements.extra || EXCLUDED.extra,
                is_active    = TRUE,
                updated_at   = now()
        """), elem_rows)
        st.elements = len(elem_rows)
    if hist_rows:
        db.execute(text("""
            INSERT INTO status_history (entity_type, site_id, element_id, old_status, new_status,
                                        changed_at, observed_at, source, reason)
            VALUES ('ELEMENT', :site_id, :eid, :old, :new, :at, :at, :src, :reason)
        """), hist_rows)

    if result.inventory_complete:
        gone = [v[0] for k, v in existing.items() if k not in seen_ext]
        if gone:
            rows = db.execute(text("""
                UPDATE site_elements SET is_active = FALSE, updated_at = now()
                WHERE id = ANY(:ids) AND is_active RETURNING site_id
            """), {"ids": gone}).all()
            st.deactivated_elements = len(rows)
            gone_sites = {r[0] for r in rows}
            affected_sites |= gone_sites
            if gone_sites:
                db.execute(text("""
                    UPDATE sites s SET is_active = FALSE, updated_at = now()
                    WHERE s.id = ANY(:ids) AND NOT s.in_reference
                      AND NOT EXISTS (SELECT 1 FROM site_elements e WHERE e.site_id = s.id AND e.is_active)
                """), {"ids": list(gone_sites)})

    # ---------------------------------------------------------------- alarmes
    if result.alarms or result.alarms_complete:
        elem_ids = {r[0]: (r[1], r[2]) for r in db.execute(text(
            "SELECT external_id, id, site_id FROM site_elements WHERE omc_source_id = :s"), {"s": source.id})}
        alarm_rows, seen_alarms = [], set()
        for a in result.alarms:
            aid = (a.external_alarm_id or "").strip()
            if not aid or aid in seen_alarms:
                continue
            seen_alarms.add(aid)
            el = elem_ids.get(a.element_external_id) if a.element_external_id else None
            sid = el[1] if el else site_ids.get(a.site_external_id) if a.site_external_id else None
            if sid is None:
                st.messages.append(f"Alarme {aid} : site/équipement non identifié (conservée sans rattachement)")
            sev = a.severity if a.severity in SEVERITIES else "INDETERMINATE"
            alarm_rows.append({
                "src": source.id, "aid": aid, "sid": sid, "eid": el[0] if el else None,
                "code": a.alarm_code, "descr": a.description, "sev": sev,
                "state": "CLEARED" if a.cleared_at else "ACTIVE",
                "raised": a.raised_at or now, "cleared": a.cleared_at,
                "extra": json.dumps(a.extra or {}, default=str),
            })
            if sid:
                affected_sites.add(sid)
        if alarm_rows:
            db.execute(text("""
                INSERT INTO alarms (omc_source_id, external_alarm_id, site_id, element_id, alarm_code,
                                    description, severity, state, raised_at, cleared_at, last_seen_at, extra)
                VALUES (:src, :aid, :sid, :eid, :code, :descr, :sev, :state, :raised, :cleared, now(),
                        CAST(:extra AS jsonb))
                ON CONFLICT (omc_source_id, external_alarm_id) DO UPDATE SET
                    site_id = COALESCE(EXCLUDED.site_id, alarms.site_id),
                    element_id = COALESCE(EXCLUDED.element_id, alarms.element_id),
                    alarm_code = EXCLUDED.alarm_code, description = EXCLUDED.description,
                    severity = EXCLUDED.severity, state = EXCLUDED.state,
                    cleared_at = EXCLUDED.cleared_at, last_seen_at = now(),
                    extra = alarms.extra || EXCLUDED.extra
            """), alarm_rows)
            st.alarms = len(alarm_rows)
        if result.alarms_complete:
            rows = db.execute(text("""
                UPDATE alarms SET state = 'CLEARED', cleared_at = :now
                WHERE omc_source_id = :s AND state = 'ACTIVE' AND NOT (external_alarm_id = ANY(:keep))
                RETURNING site_id
            """), {"s": source.id, "keep": list(seen_alarms), "now": now}).all()
            st.cleared_alarms = len(rows)
            affected_sites |= {r[0] for r in rows if r[0]}

    # Tous les sites portés par cette source sont réévalués (fraîcheur des données)
    for (sid,) in db.execute(text(
            "SELECT DISTINCT site_id FROM site_elements WHERE omc_source_id = :s"), {"s": source.id}):
        affected_sites.add(sid)
    if evaluate and affected_sites:
        res = evaluate_sites(db, affected_sites, now=now)
        st.site_transitions = res["transitions"]
    return st
