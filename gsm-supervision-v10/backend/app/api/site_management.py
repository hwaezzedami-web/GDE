"""Gestion des sites du référentiel et traitement des sites inconnus remontés par les OMC.

  GET    /api/site-reference/options                    listes de choix (cycles de vie, DR, technologies)
  GET    /api/site-reference/sites                      sites du référentiel (recherche, filtres, tri, pages)
  POST   /api/site-reference/sites                      (admin) ajout manuel ; adopte un site inconnu de même code
  PUT    /api/site-reference/sites/{id}                 (admin) modification
  POST   /api/site-reference/sites/delete               (admin) retrait du référentiel ou suppression, en lot
  GET    /api/site-reference/sites/export               (export) liste filtrée
  GET    /api/site-reference/unknown-sites              sites remontés par un OMC, absents du référentiel
  POST   /api/site-reference/unknown-sites/{id}/link    (admin) rattachement à un site du référentiel
  POST   /api/site-reference/unknown-sites/ack          (superviseur) ignorer / prendre en compte, en lot
  GET    /api/site-reference/unknown-sites/export       (export)
  GET    /api/site-reference/aliases                    correspondances de codes OMC -> référentiel
  DELETE /api/site-reference/aliases/{omc_code}         (admin)
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, get_current_user, require_admin, require_export, require_supervisor
from ..filters import display_status_sql
from ..models import REF_STATUSES, TECHNOLOGIES, User
from ..reference.manage import ManageError, SiteInput, create_site, delete_alias, link_unknown, remove_sites, update_site
from ..services.settings_service import get_setting
from .export import _render

router = APIRouter(prefix="/api/site-reference", tags=["référentiel"])

CODE_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-/]{0,59}$")
DS = display_status_sql("s")


def _like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")[:80] + "%"


def _err(exc: ManageError) -> HTTPException:
    return HTTPException(exc.status, str(exc))


# --------------------------------------------------------------------------- modèles
class SiteBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    wilaya_code: int | None = Field(None, ge=1, le=69)
    commune: str | None = Field(None, max_length=120)
    address: str | None = Field(None, max_length=300)
    dr: str | None = Field(None, max_length=100)
    lifecycle: str | None = Field(None, max_length=80)
    technologies: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("technologies")
    @classmethod
    def _techs(cls, v):
        bad = [t for t in v if t not in TECHNOLOGIES]
        if bad:
            raise ValueError(f"technologies inconnues : {', '.join(bad)} (attendu : {', '.join(TECHNOLOGIES)})")
        return v

    def to_input(self) -> SiteInput:
        return SiteInput(**self.model_dump(exclude={"code"}))


class SiteCreate(SiteBody):
    code: str = Field(min_length=1, max_length=60)

    @field_validator("code")
    @classmethod
    def _code(cls, v):
        v = v.strip()
        if not CODE_RX.match(v):
            raise ValueError("code site : lettres, chiffres, « _ . - / » (60 caractères max.)")
        return v


class DeleteBody(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=5000)
    mode: str = Field("remove", pattern="^(remove|purge)$")


class LinkBody(BaseModel):
    target_code: str = Field(min_length=1, max_length=60)
    note: str | None = Field(None, max_length=500)


class AckBody(BaseModel):
    anomaly_ids: list[int] = Field(min_length=1, max_length=5000)
    note: str | None = Field(None, max_length=500)


# --------------------------------------------------------------------------- listes de choix
@router.get("/options")
def options(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cfg = get_setting(db, "reference")
    used = dict(db.execute(text("""SELECT lifecycle, count(*) FROM sites WHERE in_reference AND lifecycle IS NOT NULL
                                   GROUP BY 1""")).all())
    values = sorted(set(cfg["lifecycle_map"]) | set(used))
    from ..reference.service import classify
    return {
        "lifecycles": [{"value": v, "category": classify(v, cfg), "sites": used.get(v, 0)} for v in values],
        "lifecycle_missing": cfg["lifecycle_missing"],
        "drs": [r[0] for r in db.execute(text(
            "SELECT DISTINCT dr FROM sites WHERE in_reference AND dr IS NOT NULL ORDER BY 1"))],
        "technologies": list(TECHNOLOGIES),
        "omc_sources": [r[0] for r in db.execute(text("SELECT code FROM omc_sources ORDER BY code"))],
    }


# --------------------------------------------------------------------------- sites du référentiel
SORTS = {
    "code": "s.external_id", "name": "s.name", "wilaya": "s.wilaya_code", "dr": "s.dr", "lifecycle": "s.lifecycle",
    "status": DS, "updated": "s.ref_updated_at", "supervised": "s.last_supervised_at",
}


def _sites_where(q, wilaya, dr, ref, supervised, source, anomalies) -> tuple[str, dict]:
    cond, p = ["s.in_reference"], {}
    if q:
        cond.append("""(s.external_id ILIKE :q OR s.name ILIKE :q OR s.commune ILIKE :q OR s.address ILIKE :q
                        OR EXISTS (SELECT 1 FROM site_code_aliases a WHERE a.site_external_id = s.external_id
                                   AND a.omc_code ILIKE :q))""")
        p["q"] = _like(q.strip())
    if wilaya:
        cond.append("s.wilaya_code = ANY(:w)")
        p["w"] = wilaya
    if dr:
        cond.append("s.dr = ANY(:dr)")
        p["dr"] = dr
    if ref:
        bad = [r for r in ref if r not in REF_STATUSES]
        if bad:
            raise HTTPException(422, f"ref : {', '.join(REF_STATUSES)}")
        cond.append("s.ref_status = ANY(:ref)")
        p["ref"] = ref
    if supervised is not None:
        cond.append("s.is_supervised = :sup")
        p["sup"] = supervised
    if source:
        cond.append("s.ref_source = :src")
        p["src"] = source
    if anomalies:
        cond.append("EXISTS (SELECT 1 FROM site_anomalies x WHERE x.site_id = s.id AND x.resolved_at IS NULL)")
    return " AND ".join(cond), p


def _split(values: list[str] | None, cast=str) -> list:
    out = []
    for v in values or []:
        for part in v.split(","):
            if part.strip():
                try:
                    out.append(cast(part.strip()))
                except ValueError:
                    raise HTTPException(422, f"Valeur invalide : {part}")
    return out


SITE_SELECT = f"""
    SELECT s.id, s.external_id, s.name, s.latitude, s.longitude, s.wilaya_code, w.name AS wilaya_name, s.commune,
           s.address, s.dr, s.lifecycle, s.ref_status, s.ref_technologies, s.technologies, s.vendor,
           {DS} AS status, s.is_supervised, s.last_supervised_at, s.ref_source, s.ref_updated_at, s.ref_updated_by,
           (SELECT array_agg(a.omc_code ORDER BY a.omc_code) FROM site_code_aliases a
             WHERE a.site_external_id = s.external_id) AS aliases,
           (SELECT count(*) FROM site_anomalies x WHERE x.site_id = s.id AND x.resolved_at IS NULL) AS anomalies
    FROM sites s LEFT JOIN wilayas w ON w.code = s.wilaya_code
"""


@router.get("/sites")
def list_sites(
    q: str | None = Query(None, max_length=80), wilaya: list[str] | None = Query(None),
    dr: list[str] | None = Query(None), ref: list[str] | None = Query(None),
    supervised: bool | None = Query(None), source: str | None = Query(None, pattern="^(IMPORT|MANUAL)$"),
    anomalies: bool = Query(False), sort: str = Query("code"),
    page: int = Query(1, ge=1, le=100000), page_size: int = Query(50, ge=1, le=500),
    _: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    where, p = _sites_where(q, _split(wilaya, int), _split(dr), _split(ref), supervised, source, anomalies)
    col = SORTS.get(sort.lstrip("-"))
    if col is None:
        raise HTTPException(422, f"Tri : {', '.join(SORTS)}")
    order = f"{col} {'DESC' if sort.startswith('-') else 'ASC'} NULLS LAST, s.external_id"
    total = db.execute(text(f"SELECT count(*) FROM sites s WHERE {where}"), p).scalar()
    p.update(lim=page_size, off=(page - 1) * page_size)
    rows = db.execute(text(f"{SITE_SELECT} WHERE {where} ORDER BY {order} LIMIT :lim OFFSET :off"), p).mappings().all()
    return {"total": total, "page": page, "page_size": page_size, "items": [dict(r) for r in rows]}


SITE_COLUMNS = [
    ("external_id", "Code site"), ("name", "Nom du site"), ("latitude", "Latitude"), ("longitude", "Longitude"),
    ("wilaya_name", "Wilaya"), ("commune", "Commune"), ("address", "Adresse"), ("dr", "Region"),
    ("lifecycle", "Etape cycle de vie"), ("ref_technologies", "Technologies radio"), ("ref_status", "Catégorie"),
    ("status", "État"), ("is_supervised", "Supervisé"), ("last_supervised_at", "Dernière remontée OMC (UTC)"),
    ("aliases", "Codes OMC rattachés"), ("ref_source", "Origine"), ("ref_updated_at", "Modifié le (UTC)"),
    ("ref_updated_by", "Modifié par"),
]


@router.get("/sites/export")
def export_sites(
    request: Request, q: str | None = Query(None, max_length=80), wilaya: list[str] | None = Query(None),
    dr: list[str] | None = Query(None), ref: list[str] | None = Query(None),
    supervised: bool | None = Query(None), source: str | None = Query(None, pattern="^(IMPORT|MANUAL)$"),
    anomalies: bool = Query(False), format: str = Query("xlsx", pattern="^(csv|xlsx)$"),
    user: User = Depends(require_export), db: Session = Depends(get_db),
):
    where, p = _sites_where(q, _split(wilaya, int), _split(dr), _split(ref), supervised, source, anomalies)
    rows = db.execute(text(f"{SITE_SELECT} WHERE {where} ORDER BY s.external_id LIMIT 300000"), p).mappings().all()
    audit(db, user, "EXPORT_REFERENCE_SITES", format, {"rows": len(rows)}, request)
    db.commit()
    return _render(rows, SITE_COLUMNS, format, "sites_referentiel")


@router.post("/sites", status_code=201)
def add_site(body: SiteCreate, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        res = create_site(db, body.code, body.to_input(), admin.username)
    except ManageError as exc:
        db.rollback()
        raise _err(exc)
    audit(db, admin, "REFERENCE_SITE_CREATED", res["code"],
          {**body.model_dump(exclude={"code"}), "adopted_from_omc": res["adopted_from_omc"]}, request)
    db.commit()
    return res


@router.put("/sites/{site_id}")
def edit_site(site_id: int, body: SiteBody, request: Request, admin: User = Depends(require_admin),
              db: Session = Depends(get_db)):
    try:
        res = update_site(db, site_id, body.to_input(), admin.username)
    except ManageError as exc:
        db.rollback()
        raise _err(exc)
    audit(db, admin, "REFERENCE_SITE_UPDATED", res["code"], {"changes": res["changes"]}, request)
    db.commit()
    return res


@router.post("/sites/delete")
def delete_sites(body: DeleteBody, request: Request, admin: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    try:
        res = remove_sites(db, body.ids, body.mode)
    except ManageError as exc:
        db.rollback()
        raise _err(exc)
    audit(db, admin, "REFERENCE_SITE_PURGED" if body.mode == "purge" else "REFERENCE_SITE_REMOVED",
          f"{len(res['done'])} site(s)", {"codes": res["done"][:500], "skipped": res["skipped"][:100]}, request)
    db.commit()
    return res


# --------------------------------------------------------------------------- sites inconnus (OMC)
def _unknown_where(q, source, state) -> tuple[str, dict]:
    cond, p = ["a.anomaly_type = 'UNKNOWN_SITE'", "a.resolved_at IS NULL"], {}
    if state in ("OPEN", "ACKNOWLEDGED"):
        cond.append("a.state = :st")
        p["st"] = state
    if q:
        cond.append("(s.external_id ILIKE :q OR s.name ILIKE :q OR a.details->>'suggestion' ILIKE :q)")
        p["q"] = _like(q.strip())
    if source:
        cond.append("""EXISTS (SELECT 1 FROM site_elements e JOIN omc_sources o ON o.id = e.omc_source_id
                               WHERE e.site_id = s.id AND e.is_active AND o.code = :src)""")
        p["src"] = source
    return " AND ".join(cond), p


UNKNOWN_SELECT = f"""
    SELECT a.id AS anomaly_id, a.state, a.note, a.acknowledged_by, a.first_detected_at, a.last_detected_at,
           s.id AS site_id, s.external_id, s.name, s.vendor, {DS} AS status, s.status_since, s.technologies,
           s.latitude, s.longitude, s.wilaya_code, w.name AS wilaya_name, s.commune, s.last_observed_at,
           (SELECT count(*) FROM site_elements e WHERE e.site_id = s.id AND e.is_active) AS elements,
           (SELECT string_agg(DISTINCT o.code, ', ') FROM site_elements e JOIN omc_sources o ON o.id = e.omc_source_id
             WHERE e.site_id = s.id AND e.is_active) AS sources,
           (SELECT count(*) FROM alarms al WHERE al.site_id = s.id AND al.state = 'ACTIVE') AS active_alarms,
           a.details->>'suggestion' AS suggestion, r.name AS suggestion_name, rw.name AS suggestion_wilaya,
           CASE WHEN r.id IS NOT NULL AND s.geom IS NOT NULL AND r.geom IS NOT NULL
                THEN round(ST_Distance(s.geom, r.geom)) END AS suggestion_distance_m
    FROM site_anomalies a
    JOIN sites s ON s.id = a.site_id
    LEFT JOIN wilayas w ON w.code = s.wilaya_code
    LEFT JOIN sites r ON r.external_id = a.details->>'suggestion' AND r.in_reference
    LEFT JOIN wilayas rw ON rw.code = r.wilaya_code
"""


@router.get("/unknown-sites")
def unknown_sites(
    q: str | None = Query(None, max_length=80), source: str | None = Query(None, max_length=60),
    state: str = Query("CURRENT", pattern="^(CURRENT|OPEN|ACKNOWLEDGED)$"),
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
    _: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    where, p = _unknown_where(q, source, state)
    total = db.execute(text(f"""SELECT count(*) FROM site_anomalies a JOIN sites s ON s.id = a.site_id
                                WHERE {where}"""), p).scalar()
    p.update(lim=page_size, off=(page - 1) * page_size)
    rows = db.execute(text(f"""{UNKNOWN_SELECT} WHERE {where}
        ORDER BY a.state, a.first_detected_at DESC, s.external_id LIMIT :lim OFFSET :off"""), p).mappings().all()
    counts = db.execute(text("""SELECT count(*) FILTER (WHERE state = 'OPEN') AS open,
                                       count(*) FILTER (WHERE state = 'ACKNOWLEDGED') AS acknowledged
                                FROM site_anomalies WHERE anomaly_type = 'UNKNOWN_SITE' AND resolved_at IS NULL"""
                             )).mappings().one()
    reference = db.execute(text("SELECT EXISTS (SELECT 1 FROM sites WHERE in_reference)")).scalar()
    return {"total": total, "page": page, "page_size": page_size, "items": [dict(r) for r in rows],
            "counts": dict(counts), "reference_loaded": reference}


UNKNOWN_COLUMNS = [
    ("external_id", "Code remonté par l'OMC"), ("name", "Nom OMC"), ("sources", "OMC"), ("vendor", "Équipementier"),
    ("technologies", "Technologies"), ("elements", "Équipements actifs"), ("status", "État"),
    ("active_alarms", "Alarmes actives"), ("latitude", "Latitude"), ("longitude", "Longitude"),
    ("wilaya_name", "Wilaya"), ("suggestion", "Code proche au référentiel"), ("suggestion_name", "Nom (référentiel)"),
    ("suggestion_distance_m", "Distance (m)"), ("first_detected_at", "Détecté le (UTC)"),
    ("last_observed_at", "Dernière remontée (UTC)"), ("state", "Traitement"), ("note", "Commentaire"),
]


@router.get("/unknown-sites/export")
def unknown_export(request: Request, state: str = Query("CURRENT", pattern="^(CURRENT|OPEN|ACKNOWLEDGED)$"),
                   format: str = Query("xlsx", pattern="^(csv|xlsx)$"),
                   user: User = Depends(require_export), db: Session = Depends(get_db)):
    where, p = _unknown_where(None, None, state)
    rows = db.execute(text(f"{UNKNOWN_SELECT} WHERE {where} ORDER BY s.external_id LIMIT 200000"), p).mappings().all()
    audit(db, user, "EXPORT_UNKNOWN_SITES", format, {"rows": len(rows)}, request)
    db.commit()
    return _render(rows, UNKNOWN_COLUMNS, format, "sites_inconnus_omc")


@router.post("/unknown-sites/{site_id}/link")
def link(site_id: int, body: LinkBody, request: Request, admin: User = Depends(require_admin),
         db: Session = Depends(get_db)):
    try:
        res = link_unknown(db, site_id, body.target_code, admin.username, body.note)
    except ManageError as exc:
        db.rollback()
        raise _err(exc)
    audit(db, admin, "OMC_CODE_LINKED", res["omc_code"], {"site": res["site"], "note": body.note,
                                                          "elements_moved": res["elements_moved"]}, request)
    db.commit()
    return res


@router.post("/unknown-sites/ack")
def ack_unknown(body: AckBody, request: Request, user: User = Depends(require_supervisor),
                db: Session = Depends(get_db)):
    codes = [r[0] for r in db.execute(text("""
        UPDATE site_anomalies SET state = 'ACKNOWLEDGED', acknowledged_by = :u, acknowledged_at = now(), note = :n
        WHERE id = ANY(:ids) AND anomaly_type = 'UNKNOWN_SITE' AND resolved_at IS NULL
        RETURNING site_external_id"""), {"u": user.username, "n": body.note, "ids": body.anomaly_ids})]
    audit(db, user, "ANOMALY_ACK", f"{len(codes)} site(s) inconnu(s)", {"codes": codes[:500], "note": body.note},
          request)
    db.commit()
    return {"acknowledged": len(codes)}


# --------------------------------------------------------------------------- correspondances
@router.get("/aliases")
def aliases(q: str | None = Query(None, max_length=80), _: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    cond, p = "TRUE", {}
    if q:
        cond, p = "(a.omc_code ILIKE :q OR a.site_external_id ILIKE :q OR s.name ILIKE :q)", {"q": _like(q.strip())}
    rows = db.execute(text(f"""
        SELECT a.omc_code, a.site_external_id, s.id AS site_id, s.name AS site_name, a.note, a.created_by, a.created_at
        FROM site_code_aliases a JOIN sites s ON s.external_id = a.site_external_id
        WHERE {cond} ORDER BY a.created_at DESC LIMIT 2000"""), p).mappings().all()
    return {"items": [dict(r) for r in rows]}


@router.delete("/aliases/{omc_code}")
def remove_alias(omc_code: str, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if not delete_alias(db, omc_code):
        raise HTTPException(404, "Correspondance introuvable")
    audit(db, admin, "OMC_CODE_UNLINKED", omc_code, {}, request)
    db.commit()
    return {"ok": True}
