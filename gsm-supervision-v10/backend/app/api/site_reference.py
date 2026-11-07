"""Référentiel des sites : import (KMZ, KML, Excel, CSV, GeoJSON), anomalies de rapprochement OMC.

  GET  /api/site-reference/summary              état du référentiel et des anomalies
  POST /api/site-reference/import/preview       (admin) lecture du fichier + différentiel, sans écriture
  POST /api/site-reference/import/apply         (admin) application (même fichier, mêmes options)
  GET  /api/site-reference/imports              historique des imports
  GET  /api/site-reference/anomalies            anomalies (filtrables) + compteurs
  POST /api/site-reference/anomalies/{id}/ack   (superviseur) prise en compte, avec commentaire
  POST /api/site-reference/anomalies/{id}/reopen
  POST /api/site-reference/reconcile            (superviseur) rapprochement immédiat
  GET  /api/site-reference/anomalies/export     (droit d'export)
  GET  /api/site-reference/export               (droit d'export) référentiel courant
  GET  /api/site-reference/template             modèle Excel vierge (données fictives)
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, get_current_user, require_admin, require_export, require_supervisor
from ..models import ANOMALY_TYPES, REF_STATUSES, User
from ..reference.anomalies import LABELS, reconcile_anomalies
from ..reference.mapping import TARGET_LABELS, TARGETS
from ..reference.parsers import ReferenceFileError
from ..reference.service import apply_plan, build_plan, export_reference_rows, plan_summary
from ..services.settings_service import get_setting
from .export import _render

router = APIRouter(prefix="/api/site-reference", tags=["référentiel"])

MAX_UPLOAD = 50 * 1024 * 1024
IMPORT_LOCK = 7421004
REF_LABELS = {"IN_SERVICE": "En service", "TEMP_OFF": "Arrêt temporaire", "PLANNED": "En projet",
              "REMOVED": "Démonté", "OTHER": "Autre"}


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, f"Fichier trop volumineux (maximum {MAX_UPLOAD // 1024 // 1024} Mo)")
    if not data:
        raise HTTPException(422, "Fichier vide")
    return data


def _options(mapping: str | None, mode: str, code_digits: int | None) -> tuple[dict | None, int | None]:
    if mode not in ("update", "sync"):
        raise HTTPException(422, "mode : update ou sync")
    m = None
    if mapping:
        try:
            m = json.loads(mapping)
        except ValueError:
            raise HTTPException(422, "mapping : JSON invalide")
        if not isinstance(m, dict) or any(k not in TARGETS for k in m) \
                or any(v is not None and not isinstance(v, str) for v in m.values()):
            raise HTTPException(422, f"mapping : objet {{champ: colonne}} attendu (champs : {', '.join(TARGETS)})")
        m = {k: (v or None) for k, v in m.items()}
    if code_digits is not None and not 1 <= code_digits <= 20:
        raise HTTPException(422, "code_digits doit être compris entre 1 et 20")
    return m, code_digits


# --------------------------------------------------------------------------- synthèse
@router.get("/summary")
def summary(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sites = db.execute(text("""
        SELECT count(*) FILTER (WHERE in_reference) AS reference,
               count(*) FILTER (WHERE in_reference AND is_supervised) AS reference_supervised,
               count(*) FILTER (WHERE in_reference AND NOT is_supervised AND ref_status = 'IN_SERVICE')
                 AS in_service_unsupervised,
               count(*) FILTER (WHERE is_active AND is_supervised AND NOT in_reference) AS supervised_not_in_reference,
               count(*) FILTER (WHERE is_active AND is_supervised) AS supervised
        FROM sites""")).mappings().one()
    wilaya_mismatch = db.execute(text("""
        SELECT count(*) FROM sites s JOIN wilayas w ON w.code = s.wilaya_code
        WHERE s.in_reference AND s.geom IS NOT NULL AND w.boundary IS NOT NULL
          AND NOT ST_Covers(w.boundary, s.geom)""")).scalar()
    by_status = dict(db.execute(text("""SELECT ref_status, count(*) FROM sites WHERE in_reference
                                         GROUP BY 1""")).all())
    by_dr = [dict(r) for r in db.execute(text("""
        SELECT coalesce(dr, 'Non renseignée') AS dr, count(*) AS sites,
               count(*) FILTER (WHERE is_supervised) AS supervised
        FROM sites WHERE in_reference GROUP BY 1 ORDER BY 1""")).mappings()]
    lifecycles = [dict(r) for r in db.execute(text("""
        SELECT lifecycle, ref_status, count(*) AS sites FROM sites WHERE in_reference
        GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 100""")).mappings()]
    anomalies = dict(db.execute(text("""SELECT anomaly_type, count(*) FROM site_anomalies
                                        WHERE resolved_at IS NULL AND state = 'OPEN' GROUP BY 1""")).all())
    last = db.execute(text("""SELECT id, started_at, finished_at, username, origin, file_name, file_format, mode,
                                     status, counts FROM reference_imports
                              WHERE status = 'APPLIED' ORDER BY started_at DESC LIMIT 1""")).mappings().first()
    return {
        "sites": dict(sites, wilaya_mismatch=wilaya_mismatch), "by_status": by_status, "by_dr": by_dr, "lifecycles": lifecycles,
        "anomalies": {"total": sum(anomalies.values()), "by_type": anomalies},
        "last_import": dict(last) if last else None, "settings": get_setting(db, "reference"),
        "labels": {"targets": TARGET_LABELS, "ref_status": REF_LABELS, "anomalies": LABELS},
    }


@router.get("/anomalies/count")
def anomalies_count(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Compteur léger (badge de navigation) : anomalies à traiter."""
    return {"open": db.execute(text("SELECT count(*) FROM site_anomalies WHERE resolved_at IS NULL AND state = 'OPEN'")).scalar()}


# --------------------------------------------------------------------------- import
@router.post("/import/preview")
async def import_preview(
    file: UploadFile = File(...),
    mapping: str | None = Form(None, description='JSON {"code": "Code site", "latitude": "Lat", …}'),
    mode: str = Form("update"),
    code_digits: int | None = Form(None),
    sheet: str | None = Form(None),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    content = await _read_upload(file)
    m, digits = _options(mapping, mode, code_digits)
    try:
        plan = build_plan(db, file.filename or "", content, m, mode, digits, sheet or None)
    except (ReferenceFileError, ValueError) as exc:
        raise HTTPException(422, str(exc))
    return dict(plan_summary(plan, get_setting(db, "reference")), mode=mode, file_name=file.filename,
                labels=TARGET_LABELS)


@router.post("/import/apply")
async def import_apply(
    request: Request,
    file: UploadFile = File(...),
    mapping: str | None = Form(None),
    mode: str = Form("update"),
    code_digits: int | None = Form(None),
    sheet: str | None = Form(None),
    expected_sha256: str | None = Form(None, description="Empreinte renvoyée par la prévisualisation"),
    confirm_large_removal: bool = Form(False),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    content = await _read_upload(file)
    m, digits = _options(mapping, mode, code_digits)
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": IMPORT_LOCK})   # un import à la fois
    try:
        plan = build_plan(db, file.filename or "", content, m, mode, digits, sheet or None)
        if expected_sha256 and expected_sha256 != plan.sha256:
            raise HTTPException(409, "Le fichier diffère de celui prévisualisé : relancer la prévisualisation")
        res = apply_plan(db, plan, mode, admin.username, "UI", file.filename or "", confirm_large_removal)
    except (ReferenceFileError, ValueError) as exc:
        db.rollback()
        raise HTTPException(422, str(exc))
    audit(db, admin, "REFERENCE_IMPORT", file.filename,
          {"mode": mode, "status": res["status"], "counts": res["counts"], "sha256": plan.sha256}, request)
    db.commit()
    return res


@router.get("/imports")
def imports(_: User = Depends(get_current_user), limit: int = Query(50, ge=1, le=500),
            db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT id, started_at, finished_at, username, origin, file_name, file_sha256, file_format, mode, status,
               counts, messages
        FROM reference_imports ORDER BY started_at DESC LIMIT :l"""), {"l": limit}).mappings().all()
    return {"items": [dict(r) for r in rows]}


# --------------------------------------------------------------------------- anomalies
def _anomaly_query(type_: list[str] | None, state: str, q: str | None, wilaya: int | None) -> tuple[str, dict]:
    cond, p = [], {}
    if state == "CURRENT":
        cond.append("a.resolved_at IS NULL")
    elif state in ("OPEN", "ACKNOWLEDGED", "RESOLVED"):
        cond.append("a.state = :state")
        p["state"] = state
    types = [t.strip().upper() for v in (type_ or []) for t in v.split(",") if t.strip()]
    if any(t not in ANOMALY_TYPES for t in types):
        raise HTTPException(422, f"type : {', '.join(ANOMALY_TYPES)}")
    if types:
        cond.append("a.anomaly_type = ANY(:types)")
        p["types"] = types
    if q:
        cond.append("(a.site_external_id ILIKE :q OR s.name ILIKE :q)")
        p["q"] = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")[:60] + "%"
    if wilaya is not None:
        cond.append("s.wilaya_code = :w")
        p["w"] = wilaya
    return (" AND ".join(cond) or "TRUE"), p


ANOMALY_SELECT = """
    SELECT a.id, a.anomaly_type, a.state, a.site_id, a.site_external_id, s.name AS site_name, s.vendor,
           s.wilaya_code, w.name AS wilaya_name, s.dr, s.lifecycle, s.status, s.latitude, s.longitude,
           a.details, a.first_detected_at, a.last_detected_at, a.resolved_at, a.acknowledged_by,
           a.acknowledged_at, a.note
    FROM site_anomalies a LEFT JOIN sites s ON s.id = a.site_id LEFT JOIN wilayas w ON w.code = s.wilaya_code
"""


@router.get("/anomalies")
def anomalies(
    type: list[str] | None = Query(None),
    state: str = Query("CURRENT", pattern="^(CURRENT|OPEN|ACKNOWLEDGED|RESOLVED|ALL)$"),
    q: str | None = Query(None, max_length=60),
    wilaya: int | None = Query(None, ge=1, le=99),
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
    _: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    where, p = _anomaly_query(type, state, q, wilaya)
    total = db.execute(text(f"""SELECT count(*) FROM site_anomalies a LEFT JOIN sites s ON s.id = a.site_id
                                WHERE {where}"""), p).scalar()
    p.update(lim=page_size, off=(page - 1) * page_size)
    rows = db.execute(text(f"""{ANOMALY_SELECT} WHERE {where}
        ORDER BY a.resolved_at DESC NULLS FIRST, a.state, a.first_detected_at DESC, a.id DESC
        LIMIT :lim OFFSET :off"""), p).mappings().all()
    counts = db.execute(text("""
        SELECT anomaly_type, count(*) FILTER (WHERE state = 'OPEN') AS open,
               count(*) FILTER (WHERE state = 'ACKNOWLEDGED') AS acknowledged
        FROM site_anomalies WHERE resolved_at IS NULL GROUP BY 1""")).mappings().all()
    return {"total": total, "page": page, "page_size": page_size, "items": [dict(r) for r in rows],
            "counts": {r["anomaly_type"]: {"open": r["open"], "acknowledged": r["acknowledged"]} for r in counts},
            "labels": LABELS}


class AckIn(BaseModel):
    note: str | None = Field(None, max_length=500)


@router.post("/anomalies/{anomaly_id}/ack")
def ack(anomaly_id: int, body: AckIn, request: Request, user: User = Depends(require_supervisor),
        db: Session = Depends(get_db)):
    row = db.execute(text("""
        UPDATE site_anomalies SET state = 'ACKNOWLEDGED', acknowledged_by = :u, acknowledged_at = now(), note = :n
        WHERE id = :i AND resolved_at IS NULL RETURNING id, site_external_id, anomaly_type"""),
        {"u": user.username, "n": body.note, "i": anomaly_id}).first()
    if row is None:
        raise HTTPException(404, "Anomalie introuvable ou déjà résolue")
    audit(db, user, "ANOMALY_ACK", row[1], {"type": row[2], "note": body.note}, request)
    db.commit()
    return {"ok": True}


@router.post("/anomalies/{anomaly_id}/reopen")
def reopen(anomaly_id: int, request: Request, user: User = Depends(require_supervisor),
           db: Session = Depends(get_db)):
    row = db.execute(text("""
        UPDATE site_anomalies SET state = 'OPEN', acknowledged_by = NULL, acknowledged_at = NULL
        WHERE id = :i AND resolved_at IS NULL RETURNING site_external_id"""), {"i": anomaly_id}).first()
    if row is None:
        raise HTTPException(404, "Anomalie introuvable ou déjà résolue")
    audit(db, user, "ANOMALY_REOPEN", row[0], {}, request)
    db.commit()
    return {"ok": True}


@router.post("/reconcile")
def reconcile(request: Request, user: User = Depends(require_supervisor), db: Session = Depends(get_db)):
    res = reconcile_anomalies(db)
    audit(db, user, "REFERENCE_RECONCILE", None, {"new": res["new"], "resolved": res["resolved"]}, request)
    db.commit()
    return res


ANOMALY_COLUMNS = [
    ("anomaly_label", "Anomalie"), ("site_external_id", "Code site"), ("site_name", "Nom du site"),
    ("wilaya_name", "Wilaya"), ("dr", "DR"), ("lifecycle", "Cycle de vie"), ("status", "État"),
    ("vendor", "Équipementier"), ("sources", "OMC"), ("suggestion", "Code proche au référentiel"),
    ("state", "Traitement"), ("first_detected_at", "Détectée le (UTC)"), ("last_detected_at", "Vue le (UTC)"),
    ("resolved_at", "Résolue le (UTC)"), ("acknowledged_by", "Pris en compte par"), ("note", "Commentaire"),
]


@router.get("/anomalies/export")
def anomalies_export(
    request: Request, type: list[str] | None = Query(None),
    state: str = Query("CURRENT", pattern="^(CURRENT|OPEN|ACKNOWLEDGED|RESOLVED|ALL)$"),
    format: str = Query("xlsx", pattern="^(csv|xlsx)$"),
    user: User = Depends(require_export), db: Session = Depends(get_db),
):
    where, p = _anomaly_query(type, state, None, None)
    rows = []
    for r in db.execute(text(f"{ANOMALY_SELECT} WHERE {where} ORDER BY a.anomaly_type, a.site_external_id LIMIT 200000"),
                        p).mappings():
        d = dict(r)
        det = d.get("details") or {}
        d.update(anomaly_label=LABELS.get(d["anomaly_type"], d["anomaly_type"]),
                 sources=det.get("sources"), suggestion=det.get("suggestion"))
        rows.append(d)
    audit(db, user, "EXPORT_ANOMALIES", format, {"rows": len(rows)}, request)
    db.commit()
    return _render(rows, ANOMALY_COLUMNS, format, "anomalies_referentiel")


REFERENCE_COLUMNS = [
    ("external_id", "Code site"), ("name", "Nom du site"), ("latitude", "Latitude"), ("longitude", "Longitude"),
    ("wilaya_name", "Wilaya"), ("commune", "Commune"), ("address", "Adresse"), ("dr", "Region"),
    ("lifecycle", "Etape cycle de vie"), ("technologies", "Technologies radio"),
    ("ref_status", "Catégorie"), ("reference_seen_at", "Importé le (UTC)"),
]


@router.get("/export")
def reference_export(request: Request, format: str = Query("xlsx", pattern="^(csv|xlsx)$"),
                     user: User = Depends(require_export), db: Session = Depends(get_db)):
    rows = export_reference_rows(db)
    audit(db, user, "EXPORT_REFERENCE", format, {"rows": len(rows)}, request)
    db.commit()
    return _render(rows, REFERENCE_COLUMNS, format, "referentiel_sites")


@router.get("/template")
def template(_: User = Depends(get_current_user)):
    """Modèle Excel : en-têtes reconnus automatiquement + deux lignes FICTIVES à remplacer."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sites"
    ws.append(["Code site", "Nom du site", "Latitude", "Longitude", "Wilaya", "Commune", "Adresse", "Region",
               "Etape cycle de vie", "Technologies radio"])
    ws.append(["00001", "EXEMPLE FICTIF 1", 36.7525, 3.04197, "Alger", "Alger Centre", "", "DR Alger",
               "en_air", "2G/3G/4G"])
    ws.append(["00002", "EXEMPLE FICTIF 2", 35.6976, -0.6337, "Oran", "Oran", "", "DR Oran", "planning", "4G"])
    for col, width in zip("ABCDEFGHIJ", (12, 28, 12, 12, 16, 18, 28, 14, 18, 18)):
        ws.column_dimensions[col].width = width
    for c in ws["A"]:
        c.number_format = "@"          # code site en texte : zéros de tête conservés
    info = wb.create_sheet("Lisez-moi")
    for line in (
        ["Modèle de référentiel de sites — les lignes de la feuille « Sites » sont FICTIVES, à remplacer."],
        ["Colonnes obligatoires : Code site, Latitude, Longitude (degrés décimaux WGS84)."],
        ["Le code site doit être saisi en TEXTE pour conserver les zéros de tête."],
        ["Etape cycle de vie : valeur libre, classée selon la table paramétrée dans l'application."],
        ["Technologies radio : 2G, 3G, 4G, 5G séparées par / , ou espace."],
        ["Toute autre colonne est conservée et affichée dans la fiche du site."],
    ):
        info.append(line)
    out = io.BytesIO()
    wb.save(out)
    return Response(out.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="modele_referentiel_sites.xlsx"'})


__all__ = ["router", "REF_STATUSES"]
