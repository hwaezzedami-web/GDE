"""Exports CSV / Excel des résultats filtrés (droit d'export requis, opération journalisée)."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from openpyxl import Workbook
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import audit, require_export
from ..filters import SiteFilters, display_status_sql, site_filters
from ..models import User
from .alarms import alarm_query

router = APIRouter(prefix="/api/export", tags=["export"])

SITE_COLUMNS = [
    ("external_id", "Code site"), ("name", "Nom du site"), ("vendor", "Équipementier"),
    ("wilaya_code", "Code wilaya"), ("wilaya_name", "Wilaya"), ("commune", "Commune"),
    ("latitude", "Latitude"), ("longitude", "Longitude"), ("technologies", "Technologies"),
    ("status", "État"), ("status_since", "État depuis (UTC)"), ("status_reason", "Motif"),
    ("last_observed_at", "Dernière observation (UTC)"), ("is_stale", "Données périmées"),
    ("omc_sources", "OMC source"), ("dr", "DR"), ("lifecycle", "Cycle de vie (référentiel)"),
    ("ref_status", "Catégorie référentiel"), ("in_reference", "Au référentiel"), ("is_supervised", "Supervisé"),
    ("last_supervised_at", "Dernière remontée OMC (UTC)"),
]
OUTAGE_COLUMNS = [
    ("external_id", "Code site"), ("name", "Nom du site"), ("vendor", "Équipementier"),
    ("wilaya_name", "Wilaya"), ("started_at", "Début panne (UTC)"), ("ended_at", "Fin panne (UTC)"),
    ("duration_min", "Durée (min)"), ("reason", "Motif"),
]
ALARM_COLUMNS = [
    ("site_external_id", "Code site"), ("site_name", "Nom du site"), ("wilaya_name", "Wilaya"),
    ("omc_code", "OMC"), ("technology", "Technologie"), ("alarm_code", "Code alarme"),
    ("description", "Description"), ("severity", "Gravité"), ("state", "État"),
    ("raised_at", "Début (UTC)"), ("cleared_at", "Fin (UTC)"),
]


def _cell(v):
    if isinstance(v, datetime):
        return v.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, list):
        return "|".join(str(x) for x in v)
    if isinstance(v, bool):
        return "OUI" if v else "NON"
    return v


def _render(rows, columns, fmt: str, basename: str) -> Response:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    if fmt == "csv":
        buf = io.StringIO()
        buf.write("﻿")  # BOM : ouverture correcte des accents dans Excel
        w = csv.writer(buf, delimiter=";")
        w.writerow([c[1] for c in columns])
        for r in rows:
            w.writerow([_cell(r[c[0]]) for c in columns])
        return Response(buf.getvalue().encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{basename}_{stamp}.csv"'})
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(basename[:31])
    ws.append([c[1] for c in columns])
    for r in rows:
        ws.append([_cell(r[c[0]]) for c in columns])
    out = io.BytesIO()
    wb.save(out)
    return Response(out.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{basename}_{stamp}.xlsx"'})


def _check_size(n: int) -> None:
    if n > get_settings().export_max_rows:
        raise HTTPException(413, f"Export trop volumineux ({n} lignes) : affinez les filtres.")


@router.get("/sites")
def export_sites(request: Request, f: SiteFilters = Depends(site_filters),
                 format: str = Query("xlsx", pattern="^(csv|xlsx)$"),
                 user: User = Depends(require_export), db: Session = Depends(get_db)):
    where, p = f.where()
    n = db.execute(text(f"SELECT count(*) FROM sites s WHERE {where}"), p).scalar()
    _check_size(n)
    rows = db.execute(text(f"""
        SELECT s.external_id, s.name, s.vendor, s.wilaya_code, w.name AS wilaya_name, s.commune,
               s.latitude, s.longitude, s.technologies, {display_status_sql("s")} AS status, s.status_since,
               s.status_reason, s.last_observed_at, s.is_stale, s.dr, s.lifecycle, s.ref_status, s.in_reference,
               s.is_supervised, s.last_supervised_at,
               (SELECT string_agg(DISTINCT o.code, '|') FROM site_elements e
                  JOIN omc_sources o ON o.id = e.omc_source_id WHERE e.site_id = s.id AND e.is_active) AS omc_sources
        FROM sites s LEFT JOIN wilayas w ON w.code = s.wilaya_code
        WHERE {where} ORDER BY s.wilaya_code, s.external_id
    """), p).mappings().all()
    audit(db, user, "EXPORT_SITES", format, {"rows": len(rows), "filters": f.describe()}, request)
    db.commit()
    return _render(rows, SITE_COLUMNS, format, "sites")


@router.get("/outages")
def export_outages(request: Request, f: SiteFilters = Depends(site_filters),
                   hours: int = Query(24 * 7, ge=1, le=24 * 365),
                   format: str = Query("xlsx", pattern="^(csv|xlsx)$"),
                   user: User = Depends(require_export), db: Session = Depends(get_db)):
    where, p = f.where()
    p["since"] = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = db.execute(text(f"""
        WITH h AS (
            SELECT h.*, lead(h.changed_at) OVER (PARTITION BY h.site_id ORDER BY h.changed_at, h.id) AS ended_at
            FROM status_history h WHERE h.entity_type = 'SITE'
              AND h.site_id IN (SELECT s.id FROM sites s WHERE {where})
        )
        SELECT s.external_id, s.name, s.vendor, w.name AS wilaya_name, h.changed_at AS started_at, h.ended_at,
               round(extract(epoch FROM coalesce(h.ended_at, now()) - h.changed_at) / 60) AS duration_min,
               h.reason
        FROM h JOIN sites s ON s.id = h.site_id LEFT JOIN wilayas w ON w.code = s.wilaya_code
        WHERE h.new_status = 'DOWN' AND h.changed_at >= :since ORDER BY h.changed_at DESC
    """), p).mappings().all()
    _check_size(len(rows))
    audit(db, user, "EXPORT_OUTAGES", format, {"rows": len(rows), "hours": hours, "filters": f.describe()}, request)
    db.commit()
    return _render(rows, OUTAGE_COLUMNS, format, "pannes")


@router.get("/alarms")
def export_alarms(request: Request, f: SiteFilters = Depends(site_filters),
                  state: str = Query("ACTIVE", pattern="^(ACTIVE|CLEARED|ALL)$"),
                  severity: list[str] | None = Query(None),
                  format: str = Query("xlsx", pattern="^(csv|xlsx)$"),
                  user: User = Depends(require_export), db: Session = Depends(get_db)):
    cond, p = alarm_query(f, state, severity)
    n = db.execute(text(f"SELECT count(*) FROM alarms a WHERE {cond}"), p).scalar()
    _check_size(n)
    rows = db.execute(text(f"""
        SELECT s.external_id AS site_external_id, s.name AS site_name, w.name AS wilaya_name,
               o.code AS omc_code, e.technology, a.alarm_code, a.description, a.severity, a.state,
               a.raised_at, a.cleared_at
        FROM alarms a JOIN omc_sources o ON o.id = a.omc_source_id
        LEFT JOIN sites s ON s.id = a.site_id LEFT JOIN wilayas w ON w.code = s.wilaya_code
        LEFT JOIN site_elements e ON e.id = a.element_id
        WHERE {cond} ORDER BY a.raised_at DESC NULLS LAST
    """), p).mappings().all()
    audit(db, user, "EXPORT_ALARMS", format, {"rows": len(rows), "filters": f.describe()}, request)
    db.commit()
    return _render(rows, ALARM_COLUMNS, format, "alarmes")
