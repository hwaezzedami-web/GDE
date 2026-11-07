"""Sites : points de la carte, tableau paginé, fiche détaillée, historique."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import get_current_user
from ..filters import SiteFilters, display_status_sql, site_filters
from ..services.settings_service import get_setting

router = APIRouter(prefix="/api/sites", tags=["sites"], dependencies=[Depends(get_current_user)])

DS = display_status_sql("s")
STATUS_ORDER = (f"CASE {DS} WHEN 'DOWN' THEN 0 WHEN 'DEGRADED' THEN 1 WHEN 'UNKNOWN' THEN 2 "
                "WHEN 'UP' THEN 3 ELSE 4 END")

SORTS = {
    "dr": "s.dr", "lifecycle": "s.lifecycle",
    "name": "s.name", "external_id": "s.external_id", "status": "s.status",
    "status_since": "s.status_since", "wilaya": "s.wilaya_code", "vendor": "s.vendor",
    "last_observed_at": "s.last_observed_at",
}


@router.get("/map")
def map_points(f: SiteFilters = Depends(site_filters), db: Session = Depends(get_db)):
    """Tous les sites géolocalisés correspondant aux filtres, au format compact (tableau de tableaux)."""
    where, p = f.where()
    limit = get_settings().map_max_points
    p["lim"] = limit + 1
    rows = db.execute(text(f"""
        SELECT s.id, round(s.latitude::numeric, 6), round(s.longitude::numeric, 6), {DS}, s.vendor,
               array_to_string(s.technologies, ','), s.name, s.external_id, s.wilaya_code, s.is_stale,
               s.dr, s.ref_status
        FROM sites s
        WHERE {where} AND s.geom IS NOT NULL
        ORDER BY {STATUS_ORDER}, s.id
        LIMIT :lim
    """), p).all()
    without_geo = db.execute(text(f"SELECT count(*) FROM sites s WHERE {where} AND s.geom IS NULL"), p).scalar()
    truncated = len(rows) > limit
    return {
        "fields": ["id", "lat", "lon", "status", "vendor", "techs", "name", "external_id", "wilaya", "stale",
                   "dr", "ref"],
        "rows": [[r[0], float(r[1]), float(r[2]), r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11]]
                 for r in rows[:limit]],
        "truncated": truncated,
        "without_coordinates": without_geo,
        "generated_at": datetime.now(timezone.utc),
    }


@router.get("")
def list_sites(
    f: SiteFilters = Depends(site_filters),
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(50, ge=1, le=500),
    sort: str = Query("status", description=f"Tri : {', '.join(SORTS)} (préfixe - pour décroissant)"),
    db: Session = Depends(get_db),
):
    where, p = f.where()
    desc = sort.startswith("-")
    col = SORTS.get(sort.lstrip("-"))
    if col is None:
        raise HTTPException(422, "Tri invalide")
    if sort.lstrip("-") == "status":
        order = STATUS_ORDER + (" DESC" if desc else "") + ", s.status_since DESC"
    else:
        order = f"{col} {'DESC' if desc else 'ASC'} NULLS LAST"
    total = db.execute(text(f"SELECT count(*) FROM sites s WHERE {where}"), p).scalar()
    p.update(lim=page_size, off=(page - 1) * page_size)
    rows = db.execute(text(f"""
        SELECT s.id, s.external_id, s.name, s.vendor, s.wilaya_code, w.name AS wilaya_name, s.commune,
               s.latitude, s.longitude, s.technologies, {DS} AS status, s.status_since, s.status_reason,
               s.last_observed_at, s.is_stale, s.dr, s.lifecycle, s.ref_status, s.in_reference, s.is_supervised
        FROM sites s LEFT JOIN wilayas w ON w.code = s.wilaya_code
        WHERE {where}
        ORDER BY {order}, s.id
        LIMIT :lim OFFSET :off
    """), p).mappings().all()
    return {"total": total, "page": page, "page_size": page_size, "items": [dict(r) for r in rows]}


@router.get("/{site_id}")
def site_detail(site_id: int, db: Session = Depends(get_db)):
    site = db.execute(text(f"""
        SELECT s.id, s.external_id, s.name, s.vendor, s.wilaya_code, w.name AS wilaya_name, w.region,
               s.commune, s.address, s.latitude, s.longitude, s.technologies, {DS} AS status, s.status_since,
               s.status_reason, s.pending_status, s.pending_since, s.last_observed_at, s.is_stale,
               s.is_active, s.extra, s.first_seen_at, s.updated_at,
               s.in_reference, s.ref_status, s.lifecycle, s.dr, s.ref_technologies, s.reference_seen_at,
               s.is_supervised, s.last_supervised_at
        FROM sites s LEFT JOIN wilayas w ON w.code = s.wilaya_code WHERE s.id = :id
    """), {"id": site_id}).mappings().first()
    if site is None:
        raise HTTPException(404, "Site introuvable")
    rules = get_setting(db, "status_rules")
    now = datetime.now(timezone.utc)
    elements = db.execute(text("""
        SELECT e.id, e.external_id, e.technology, e.element_type, e.name, e.oper_status, e.raw_status,
               e.status_observed_at, e.status_changed_at, e.last_communication_at, e.is_active, e.extra,
               o.code AS omc_code, o.name AS omc_name, o.vendor, o.is_demo, o.integration_validated,
               o.last_success_at AS omc_last_success, o.last_status AS omc_last_status,
               CASE WHEN o.stale_after_s IS NOT NULL THEN o.stale_after_s
                    WHEN o.connector_type = 'manual_csv' THEN NULL ELSE :dstale END AS stale_after_s
        FROM site_elements e JOIN omc_sources o ON o.id = e.omc_source_id
        WHERE e.site_id = :id ORDER BY e.is_active DESC, e.technology, e.external_id
    """), {"id": site_id, "dstale": rules["default_stale_after_s"]}).mappings().all()
    els = []
    for e in elements:
        d = dict(e)
        d["is_stale"] = bool(
            d["stale_after_s"] is not None and d["status_observed_at"] is not None
            and (now - d["status_observed_at"]).total_seconds() > d["stale_after_s"])
        els.append(d)
    active_alarms = db.execute(text("""
        SELECT a.id, a.external_alarm_id, a.alarm_code, a.description, a.severity, a.state,
               a.raised_at, a.cleared_at, a.element_id, o.code AS omc_code
        FROM alarms a JOIN omc_sources o ON o.id = a.omc_source_id
        WHERE a.site_id = :id AND a.state = 'ACTIVE'
        ORDER BY CASE a.severity WHEN 'CRITICAL' THEN 0 WHEN 'MAJOR' THEN 1 WHEN 'MINOR' THEN 2
                 WHEN 'WARNING' THEN 3 ELSE 4 END, a.raised_at DESC
        LIMIT 100
    """), {"id": site_id}).mappings().all()
    last_alarm = db.execute(text("""
        SELECT a.id, a.alarm_code, a.description, a.severity, a.state, a.raised_at, a.cleared_at,
               o.code AS omc_code
        FROM alarms a JOIN omc_sources o ON o.id = a.omc_source_id
        WHERE a.site_id = :id ORDER BY a.raised_at DESC NULLS LAST LIMIT 1
    """), {"id": site_id}).mappings().first()
    history = _history(db, site_id, 1, 30)
    anomalies = db.execute(text("""
        SELECT id, anomaly_type, state, details, first_detected_at, last_detected_at, acknowledged_by, note
        FROM site_anomalies WHERE site_id = :id AND resolved_at IS NULL ORDER BY first_detected_at
    """), {"id": site_id}).mappings().all()
    warnings = []
    if site["is_stale"]:
        warnings.append("Une partie des données de ce site est périmée : l'état affiché peut être obsolète.")
    for e in els:
        if e["omc_last_status"] == "FAILED":
            warnings.append(f"La dernière collecte de l'OMC {e['omc_code']} a échoué : "
                            "les informations peuvent ne pas être à jour.")
        if e["is_demo"]:
            warnings.append(f"Source {e['omc_code']} : DONNÉES FICTIVES (démonstration).")
    return {
        "site": dict(site),
        "elements": els,
        "active_alarms": [dict(a) for a in active_alarms],
        "last_alarm": dict(last_alarm) if last_alarm else None,
        "history": history,
        "anomalies": [dict(a) for a in anomalies],
        "warnings": sorted(set(warnings)),
    }


def _history(db: Session, site_id: int, page: int, page_size: int, level: str | None = None) -> dict:
    cond = "h.site_id = :id"
    if level in ("SITE", "ELEMENT"):
        cond += " AND h.entity_type = :lvl"
    p = {"id": site_id, "lim": page_size, "off": (page - 1) * page_size, "lvl": level}
    total = db.execute(text(f"SELECT count(*) FROM status_history h WHERE {cond}"), p).scalar()
    rows = db.execute(text(f"""
        SELECT h.id, h.entity_type, h.old_status, h.new_status, h.changed_at, h.observed_at, h.source,
               h.reason, e.technology, e.external_id AS element_external_id,
               lead(h.changed_at) OVER (PARTITION BY h.entity_type, h.element_id ORDER BY h.changed_at)
                 AS ended_at
        FROM status_history h LEFT JOIN site_elements e ON e.id = h.element_id
        WHERE {cond}
        ORDER BY h.changed_at DESC, h.id DESC
        LIMIT :lim OFFSET :off
    """), p).mappings().all()
    return {"total": total, "items": [dict(r) for r in rows]}


@router.get("/{site_id}/history")
def site_history(site_id: int, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                 level: str | None = Query(None, pattern="^(SITE|ELEMENT)$"), db: Session = Depends(get_db)):
    return _history(db, site_id, page, page_size, level)
