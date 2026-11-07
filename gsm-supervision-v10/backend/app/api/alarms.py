"""Alarmes : liste filtrable et paginée."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..filters import SiteFilters, site_filters
from ..models import SEVERITIES

router = APIRouter(prefix="/api/alarms", tags=["alarms"], dependencies=[Depends(get_current_user)])


def alarm_query(f: SiteFilters, state: str, severity: list[str] | None) -> tuple[str, dict]:
    where, p = f.where()
    cond = [f"a.site_id IN (SELECT s.id FROM sites s WHERE {where})"]
    if state != "ALL":
        cond.append("a.state = :state")
        p["state"] = state
    sev = [x.strip().upper() for v in (severity or []) for x in v.split(",") if x.strip()]
    for x in sev:
        if x not in SEVERITIES:
            raise HTTPException(422, f"Gravité invalide : {x}")
    if sev:
        cond.append("a.severity = ANY(:sev)")
        p["sev"] = sev
    return " AND ".join(cond), p


@router.get("")
def list_alarms(
    f: SiteFilters = Depends(site_filters),
    state: str = Query("ACTIVE", pattern="^(ACTIVE|CLEARED|ALL)$"),
    severity: list[str] | None = Query(None),
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    cond, p = alarm_query(f, state, severity)
    total = db.execute(text(f"SELECT count(*) FROM alarms a WHERE {cond}"), p).scalar()
    counts = db.execute(text(f"SELECT a.severity, count(*) FROM alarms a WHERE {cond} GROUP BY 1"), p).all()
    p.update(lim=page_size, off=(page - 1) * page_size)
    rows = db.execute(text(f"""
        SELECT a.id, a.external_alarm_id, a.alarm_code, a.description, a.severity, a.state,
               a.raised_at, a.cleared_at, a.site_id, s.external_id AS site_external_id, s.name AS site_name,
               s.wilaya_code, w.name AS wilaya_name, s.status AS site_status, o.code AS omc_code, o.vendor,
               e.technology
        FROM alarms a JOIN omc_sources o ON o.id = a.omc_source_id
        LEFT JOIN sites s ON s.id = a.site_id LEFT JOIN wilayas w ON w.code = s.wilaya_code
        LEFT JOIN site_elements e ON e.id = a.element_id
        WHERE {cond}
        ORDER BY CASE a.severity WHEN 'CRITICAL' THEN 0 WHEN 'MAJOR' THEN 1 WHEN 'MINOR' THEN 2
                 WHEN 'WARNING' THEN 3 ELSE 4 END, a.raised_at DESC NULLS LAST, a.id DESC
        LIMIT :lim OFFSET :off
    """), p).mappings().all()
    return {"total": total, "by_severity": {k: v for k, v in counts}, "page": page,
            "page_size": page_size, "items": [dict(r) for r in rows]}
