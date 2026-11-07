"""Tableau de bord : compteurs, répartitions, pannes récentes, évolution, disponibilité.

Tous les compteurs sont calculés à partir de la base, avec les mêmes filtres
que la carte (filters.SiteFilters) : carte et tableau de bord sont cohérents.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..filters import SiteFilters, display_status_sql, site_filters

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"], dependencies=[Depends(get_current_user)])

DS = display_status_sql("s")
# « unknown » : site supervisé dont l'état est inconnu (collecte interrompue…) ;
# « unsupervised » : site du référentiel qu'aucun OMC ne remonte.
STATUS_COLS = f"""count(*) AS total,
    count(*) FILTER (WHERE {DS} = 'UP') AS up,
    count(*) FILTER (WHERE {DS} = 'DOWN') AS down,
    count(*) FILTER (WHERE {DS} = 'DEGRADED') AS degraded,
    count(*) FILTER (WHERE {DS} = 'UNKNOWN') AS unknown,
    count(*) FILTER (WHERE {DS} = 'UNSUPERVISED') AS unsupervised"""


@router.get("/summary")
def summary(f: SiteFilters = Depends(site_filters), recent_hours: int = Query(24, ge=1, le=720),
            db: Session = Depends(get_db)):
    where, p = f.where()
    totals = db.execute(text(f"""SELECT {STATUS_COLS},
            count(*) FILTER (WHERE s.is_stale) AS stale,
            count(*) FILTER (WHERE s.geom IS NULL) AS without_coordinates
        FROM sites s WHERE {where}"""), p).mappings().one()
    by_vendor = db.execute(text(f"""SELECT s.vendor AS key, {STATUS_COLS}
        FROM sites s WHERE {where} GROUP BY s.vendor ORDER BY s.vendor"""), p).mappings().all()
    by_tech = db.execute(text(f"""SELECT t AS key, {STATUS_COLS}
        FROM sites s, unnest(s.technologies) t WHERE {where} GROUP BY t ORDER BY t"""), p).mappings().all()
    by_wilaya = db.execute(text(f"""SELECT s.wilaya_code AS code, coalesce(w.name, 'Non renseignée') AS name,
            w.region, {STATUS_COLS}
        FROM sites s LEFT JOIN wilayas w ON w.code = s.wilaya_code
        WHERE {where} GROUP BY s.wilaya_code, w.name, w.region
        ORDER BY count(*) FILTER (WHERE s.status = 'DOWN' AND s.is_supervised) DESC, count(*) DESC"""), p).mappings().all()
    by_dr = db.execute(text(f"""SELECT coalesce(s.dr, 'Non renseignée') AS key, {STATUS_COLS}
        FROM sites s WHERE {where} AND s.in_reference GROUP BY 1 ORDER BY 1"""), p).mappings().all()
    anomalies = dict(db.execute(text("""SELECT anomaly_type, count(*) FROM site_anomalies
        WHERE resolved_at IS NULL AND state = 'OPEN' GROUP BY 1""")).all())
    reference = db.execute(text("""SELECT count(*) FILTER (WHERE in_reference) AS sites,
            count(*) FILTER (WHERE in_reference AND is_supervised) AS supervised,
            max(reference_seen_at) AS last_import
        FROM sites""")).mappings().one()
    by_region = db.execute(text(f"""SELECT coalesce(w.region, 'Non renseignée') AS key, {STATUS_COLS}
        FROM sites s LEFT JOIN wilayas w ON w.code = s.wilaya_code
        WHERE {where} GROUP BY 1 ORDER BY 1"""), p).mappings().all()
    p["since"] = datetime.now(timezone.utc) - timedelta(hours=recent_hours)
    recent = db.execute(text(f"""SELECT count(*) AS outages, count(DISTINCT h.site_id) AS sites
        FROM status_history h JOIN sites s ON s.id = h.site_id
        WHERE h.entity_type = 'SITE' AND h.new_status = 'DOWN' AND h.changed_at >= :since AND {where}"""),
        p).mappings().one()
    return {
        "generated_at": datetime.now(timezone.utc),
        "totals": dict(totals),
        "by_vendor": [dict(r) for r in by_vendor],
        "by_technology": [dict(r) for r in by_tech],
        "by_region": [dict(r) for r in by_region],
        "by_wilaya": [dict(r) for r in by_wilaya],
        "by_dr": [dict(r) for r in by_dr],
        "anomalies": {"total": sum(anomalies.values()), "by_type": anomalies},
        "reference": dict(reference),
        "recent_outages": {"hours": recent_hours, **dict(recent)},
        "omc_sources": omc_status(db),
        "services": services_status(db),
        "filters": f.describe(),
    }


def omc_status(db: Session) -> list[dict]:
    rows = db.execute(text("""
        SELECT o.id, o.code, o.name, o.vendor, o.connector_type, o.enabled, o.is_demo,
               o.integration_validated, o.poll_interval_s, o.last_attempt_at, o.last_success_at,
               o.last_status, o.last_error, o.consecutive_failures,
               (SELECT count(*) FROM site_elements e WHERE e.omc_source_id = o.id AND e.is_active) AS elements,
               CASE WHEN o.last_success_at IS NULL THEN NULL
                    ELSE extract(epoch FROM now() - o.last_success_at)::int END AS age_s
        FROM omc_sources o ORDER BY o.vendor, o.code
    """)).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        if not d["enabled"]:
            d["health"] = "DISABLED"
        elif d["connector_type"] == "manual_csv":
            d["health"] = "MANUAL"
        elif d["last_status"] == "FAILED":
            d["health"] = "FAILED"
        elif d["age_s"] is None or d["age_s"] > 3 * d["poll_interval_s"] + 120:
            d["health"] = "LATE"
        else:
            d["health"] = "OK"
        out.append(d)
    return out


def services_status(db: Session) -> list[dict]:
    rows = db.execute(text("""
        SELECT service, host, last_beat, started_at, info,
               extract(epoch FROM now() - last_beat)::int AS age_s
        FROM service_heartbeats ORDER BY service, host
    """)).mappings().all()
    return [dict(r, alive=r["age_s"] < 180) for r in rows]


@router.get("/trend")
def trend(days: int = Query(7, ge=1, le=400),
          vendor: str | None = Query(None, pattern="^(ERICSSON|HUAWEI|ZTE|MULTI)$"),
          wilaya: int | None = Query(None, ge=0, le=99),
          db: Session = Depends(get_db)):
    """Évolution des compteurs (instantanés périodiques écrits par le service de collecte).

    Les instantanés étant agrégés par équipementier et wilaya, seuls ces deux filtres s'appliquent.
    """
    cond = ["taken_at >= now() - make_interval(days => :days)"]
    p: dict = {"days": days}
    if vendor:
        cond.append("vendor = :vendor")
        p["vendor"] = vendor
    if wilaya is not None:
        cond.append("wilaya_code = :wilaya")
        p["wilaya"] = wilaya
    # Au-delà de 2 jours : un point par heure pour garder une courbe lisible
    bucket = "date_trunc('hour', taken_at)" if days > 2 else "taken_at"
    rows = db.execute(text(f"""
        WITH t AS (
            SELECT taken_at, sum(total) total, sum(up) up, sum(down) down,
                   sum(degraded) degraded, sum(unknown) unknown
            FROM kpi_snapshots WHERE {' AND '.join(cond)} GROUP BY taken_at
        )
        SELECT {bucket} AS t, round(avg(total)) total, round(avg(up)) up, round(avg(down)) down,
               round(avg(degraded)) degraded, round(avg(unknown)) unknown
        FROM t GROUP BY 1 ORDER BY 1
    """), p).mappings().all()
    return {"points": [{k: (int(v) if k != "t" else v) for k, v in r.items()} for r in rows]}


@router.get("/outages")
def outages(f: SiteFilters = Depends(site_filters), hours: int = Query(24, ge=1, le=24 * 90),
            limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db)):
    """Pannes (passages à DOWN) détectées sur la période, avec heure de rétablissement et durée."""
    where, p = f.where()
    p.update(since=datetime.now(timezone.utc) - timedelta(hours=hours), lim=limit)
    rows = db.execute(text(f"""
        WITH h AS (
            SELECT h.*, lead(h.changed_at) OVER (PARTITION BY h.site_id ORDER BY h.changed_at, h.id) AS ended_at,
                        lead(h.new_status) OVER (PARTITION BY h.site_id ORDER BY h.changed_at, h.id) AS next_status
            FROM status_history h WHERE h.entity_type = 'SITE'
              AND h.site_id IN (SELECT s.id FROM sites s WHERE {where})
        )
        SELECT h.site_id, s.external_id, s.name, s.vendor, s.wilaya_code, w.name AS wilaya_name,
               h.changed_at AS started_at, h.ended_at, h.next_status, h.reason,
               extract(epoch FROM coalesce(h.ended_at, now()) - h.changed_at)::int AS duration_s,
               {DS} AS current_status
        FROM h JOIN sites s ON s.id = h.site_id LEFT JOIN wilayas w ON w.code = s.wilaya_code
        WHERE h.new_status = 'DOWN' AND h.changed_at >= :since
        ORDER BY h.changed_at DESC LIMIT :lim
    """), p).mappings().all()
    return {"hours": hours, "items": [dict(r) for r in rows]}


@router.get("/availability")
def availability(f: SiteFilters = Depends(site_filters), days: int = Query(7, ge=1, le=365),
                 group: str = Query("wilaya", pattern="^(wilaya|vendor|region|site)$"),
                 limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db)):
    """Disponibilité = 1 − temps DOWN / temps observé (les périodes UNKNOWN sont exclues du calcul)."""
    where, p = f.where()
    p.update(start=datetime.now(timezone.utc) - timedelta(days=days), lim=limit)
    key = {
        "wilaya": "coalesce(w.name, 'Non renseignée')",
        "vendor": "s.vendor",
        "region": "coalesce(w.region, 'Non renseignée')",
        "site": "s.external_id || ' — ' || s.name",
    }[group]
    rows = db.execute(text(f"""
        WITH fs AS (SELECT s.id, s.first_seen_at FROM sites s
                    WHERE {where} AND (NOT s.in_reference OR s.last_supervised_at IS NOT NULL)),
        h AS (
            SELECT h.site_id, h.new_status, h.changed_at,
                   lead(h.changed_at) OVER (PARTITION BY h.site_id ORDER BY h.changed_at, h.id) AS next_at
            FROM status_history h JOIN fs ON fs.id = h.site_id WHERE h.entity_type = 'SITE'
        ),
        per_site AS (
            SELECT fs.id AS site_id,
                   extract(epoch FROM now() - greatest(:start, fs.first_seen_at)) AS window_s,
                   coalesce(sum(extract(epoch FROM least(coalesce(h.next_at, now()), now())
                                 - greatest(h.changed_at, :start)))
                            FILTER (WHERE h.new_status = 'DOWN'), 0) AS down_s,
                   coalesce(sum(extract(epoch FROM least(coalesce(h.next_at, now()), now())
                                 - greatest(h.changed_at, :start)))
                            FILTER (WHERE h.new_status = 'UNKNOWN'), 0) AS unknown_s
            FROM fs LEFT JOIN h ON h.site_id = fs.id AND coalesce(h.next_at, now()) > :start
            GROUP BY fs.id, fs.first_seen_at
        )
        SELECT {key} AS key, count(*) AS sites,
               round(sum(down_s)::numeric / 3600, 2) AS down_hours,
               round(sum(unknown_s)::numeric / 3600, 2) AS unknown_hours,
               round(100 * (1 - sum(down_s) / nullif(sum(greatest(window_s - unknown_s, 0)), 0))::numeric, 3)
                 AS availability_pct
        FROM per_site ps JOIN sites s ON s.id = ps.site_id LEFT JOIN wilayas w ON w.code = s.wilaya_code
        GROUP BY 1 ORDER BY availability_pct ASC NULLS LAST, 1 LIMIT :lim
    """), p).mappings().all()
    return {"days": days, "group": group, "items": [dict(r) for r in rows]}
