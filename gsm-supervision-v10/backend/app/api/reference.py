"""Référentiels pour les listes de filtres et la carte."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import STATUSES, TECHNOLOGIES, VENDORS

router = APIRouter(prefix="/api/reference", tags=["reference"], dependencies=[Depends(get_current_user)])


@router.get("")
def reference(db: Session = Depends(get_db)):
    wilayas = db.execute(text("""
        SELECT code, name, name_ar, region, chef_lieu, center_lat, center_lon, parent_code, created_year,
               boundary IS NOT NULL AS has_boundary, boundary_source
        FROM wilayas ORDER BY code""")).mappings().all()
    regions = [r[0] for r in db.execute(text("SELECT DISTINCT region FROM wilayas ORDER BY 1"))]
    omc = db.execute(text("""SELECT code, name, vendor, is_demo, integration_validated
                             FROM omc_sources ORDER BY vendor, code""")).mappings().all()
    drs = [r[0] for r in db.execute(text("SELECT DISTINCT dr FROM sites WHERE in_reference AND dr IS NOT NULL ORDER BY 1"))]
    return {
        "drs": drs,
        "ref_statuses": ["IN_SERVICE", "TEMP_OFF", "PLANNED", "REMOVED", "OTHER"],
        "wilayas": [dict(w) for w in wilayas],
        "regions": regions,
        "vendors": list(VENDORS),
        "technologies": list(TECHNOLOGIES),
        "statuses": list(STATUSES),
        "omc_sources": [dict(o) for o in omc],
    }


@router.get("/communes")
def communes(wilaya: int | None = Query(None), q: str | None = Query(None, max_length=60),
             db: Session = Depends(get_db)):
    cond, p = ["commune IS NOT NULL", "is_active"], {}
    if wilaya is not None:
        cond.append("wilaya_code = :w")
        p["w"] = wilaya
    if q:
        cond.append("commune ILIKE :q")
        p["q"] = f"%{q}%"
    rows = db.execute(text(f"""SELECT commune, wilaya_code, count(*) FROM sites WHERE {' AND '.join(cond)}
                               GROUP BY 1, 2 ORDER BY 1 LIMIT 500"""), p).all()
    return [{"commune": r[0], "wilaya_code": r[1], "sites": r[2]} for r in rows]


@router.get("/wilaya-boundaries")
def wilaya_boundaries(db: Session = Depends(get_db)):
    """Contours des wilayas en GeoJSON (si chargés en base), simplifiés pour l'affichage."""
    rows = db.execute(text("""
        SELECT code, name, region,
               ST_AsGeoJSON(ST_SimplifyPreserveTopology(boundary::geometry, 0.005), 4) AS g
        FROM wilayas WHERE boundary IS NOT NULL ORDER BY code""")).all()
    features = [{"type": "Feature", "properties": {"code": r[0], "name": r[1], "region": r[2]},
                 "geometry": json.loads(r[3])} for r in rows]
    sources = {r[0] for r in db.execute(text("SELECT DISTINCT boundary_source FROM wilayas WHERE boundary IS NOT NULL"))}
    attribution = "© contributeurs OpenStreetMap (ODbL)" if "osm-geoalgeria" in sources else ""
    return Response(json.dumps({"type": "FeatureCollection", "attribution": attribution, "features": features}),
                    media_type="application/geo+json",
                    headers={"Cache-Control": "private, max-age=3600"})
