"""Gestion manuelle du référentiel : création, modification, retrait, suppression de sites,
traitement des sites remontés par les OMC mais inconnus du référentiel.

Toutes les fonctions écrivent sans commit (transaction gérée par l'appelant) puis réévaluent
les sites concernés et recalculent les anomalies.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..services.settings_service import get_setting
from ..services.status_engine import evaluate_sites
from .anomalies import reconcile_anomalies
from .mapping import LAT_RANGE, LON_RANGE
from .service import classify

UNSUPERVISED_REASON = "Non supervisé : aucun OMC ne remonte ce site"


class ManageError(ValueError):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


@dataclass
class SiteInput:
    name: str
    latitude: float
    longitude: float
    wilaya_code: int | None = None
    commune: str | None = None
    address: str | None = None
    dr: str | None = None
    lifecycle: str | None = None
    technologies: list[str] | None = None


def _check_position(lat: float, lon: float) -> None:
    if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]):
        raise ManageError(f"Coordonnées hors d'Algérie ({lat}, {lon}) : vérifier latitude / longitude")


def _params(data: SiteInput, user: str) -> dict:
    _check_position(data.latitude, data.longitude)
    lc = (data.lifecycle or "").strip().lower() or None
    return {
        "name": data.name.strip()[:200], "lat": round(data.latitude, 7), "lon": round(data.longitude, 7),
        "wilaya": data.wilaya_code, "commune": (data.commune or "").strip() or None,
        "address": (data.address or "").strip() or None, "dr": (data.dr or "").strip() or None,
        "lifecycle": lc, "techs": sorted(set(data.technologies or [])), "user": user,
        "now": datetime.now(timezone.utc),
    }


def _after_write(db: Session, site_ids: list[int], wilaya_from_coords: bool) -> dict:
    if wilaya_from_coords and site_ids:
        db.execute(text("""
            UPDATE sites s SET wilaya_code = w.code FROM wilayas w
            WHERE s.id = ANY(:ids) AND s.wilaya_code IS NULL AND s.geom IS NOT NULL AND w.boundary IS NOT NULL
              AND ST_Covers(w.boundary, s.geom)"""), {"ids": site_ids})
    if site_ids:
        evaluate_sites(db, site_ids)
    return reconcile_anomalies(db)


def create_site(db: Session, code: str, data: SiteInput, user: str) -> dict:
    """Ajoute un site au référentiel. Si le code existe déjà hors référentiel (site remonté par un
    OMC, inconnu du référentiel), ce site y entre en conservant ses équipements et son historique."""
    code = code.strip().upper()
    p = _params(data, user)
    settings = get_setting(db, "reference")
    p.update(code=code, ref_status=classify(p["lifecycle"], settings))
    row = db.execute(text("SELECT id, in_reference FROM sites WHERE external_id = :c FOR UPDATE"),
                     {"c": code}).first()
    if row and row[1]:
        raise ManageError(f"Le site {code} existe déjà au référentiel", 409)
    alias = db.execute(text("SELECT site_external_id FROM site_code_aliases WHERE omc_code = :c"), {"c": code}).scalar()
    if alias:
        raise ManageError(f"Le code {code} est rattaché au site {alias} (correspondance de codes) : "
                          "supprimer d'abord cette correspondance", 409)
    if row:
        sid = row[0]
        db.execute(text("""
            UPDATE sites SET name = :name, latitude = :lat, longitude = :lon, wilaya_code = :wilaya,
                commune = :commune, address = :address, dr = :dr, lifecycle = :lifecycle, ref_status = :ref_status,
                ref_technologies = CAST(:techs AS text[]), in_reference = TRUE, reference_seen_at = :now,
                ref_source = 'MANUAL', ref_updated_at = :now, ref_updated_by = :user, is_active = TRUE,
                extra = extra || jsonb_build_object('omc_name', name), updated_at = now()
            WHERE id = :id"""), dict(p, id=sid))
        adopted = True
    else:
        sid = db.execute(text("""
            INSERT INTO sites (external_id, name, vendor, latitude, longitude, wilaya_code, commune, address, dr,
                               lifecycle, ref_status, ref_technologies, in_reference, reference_seen_at,
                               ref_source, ref_updated_at, ref_updated_by, status_since, status_reason)
            VALUES (:code, :name, 'UNKNOWN', :lat, :lon, :wilaya, :commune, :address, :dr, :lifecycle, :ref_status,
                    CAST(:techs AS text[]), TRUE, :now, 'MANUAL', :now, :user, now(), :reason)
            RETURNING id"""), dict(p, reason=UNSUPERVISED_REASON)).scalar()
        adopted = False
    anomalies = _after_write(db, [sid], p["wilaya"] is None)
    return {"id": sid, "code": code, "adopted_from_omc": adopted, "anomalies": anomalies}


def update_site(db: Session, site_id: int, data: SiteInput, user: str) -> dict:
    cur = db.execute(text("""SELECT external_id, name, latitude, longitude, wilaya_code, commune, address, dr,
                                    lifecycle, ref_technologies
                             FROM sites WHERE id = :id AND in_reference FOR UPDATE"""),
                     {"id": site_id}).mappings().first()
    if cur is None:
        raise ManageError("Site introuvable au référentiel", 404)
    p = _params(data, user)
    p.update(id=site_id, ref_status=classify(p["lifecycle"], get_setting(db, "reference")))
    db.execute(text("""
        UPDATE sites SET name = :name, latitude = :lat, longitude = :lon, wilaya_code = :wilaya, commune = :commune,
            address = :address, dr = :dr, lifecycle = :lifecycle, ref_status = :ref_status,
            ref_technologies = CAST(:techs AS text[]), ref_source = 'MANUAL', ref_updated_at = :now,
            ref_updated_by = :user, updated_at = now()
        WHERE id = :id"""), p)
    new = {"name": p["name"], "latitude": p["lat"], "longitude": p["lon"], "wilaya_code": p["wilaya"],
           "commune": p["commune"], "address": p["address"], "dr": p["dr"], "lifecycle": p["lifecycle"],
           "ref_technologies": p["techs"]}
    changes = {k: {"avant": cur[k], "après": v} for k, v in new.items()
               if (sorted(cur[k] or []) if k == "ref_technologies" else cur[k]) != v
               and not (k == "wilaya_code" and v is None)}
    anomalies = _after_write(db, [site_id], p["wilaya"] is None)
    return {"id": site_id, "code": cur["external_id"], "changes": changes, "anomalies": anomalies}


def remove_sites(db: Session, ids: list[int], mode: str) -> dict:
    """mode « remove » : le site sort du référentiel (encore visible s'il est remonté par un OMC, et
    alors signalé comme inconnu) ; mode « purge » : suppression définitive, refusée pour un site
    encore remonté par un OMC (il réapparaîtrait à la collecte suivante)."""
    if mode not in ("remove", "purge"):
        raise ManageError("mode : remove ou purge")
    rows = db.execute(text("""SELECT id, external_id, in_reference,
                                     EXISTS (SELECT 1 FROM site_elements e WHERE e.site_id = s.id AND e.is_active)
                              FROM sites s WHERE id = ANY(:ids) FOR UPDATE"""), {"ids": ids}).all()
    done, skipped = [], []
    for sid, code, in_ref, active in rows:
        if mode == "purge" and active:
            skipped.append({"code": code, "reason": "encore remonté par un OMC : retirer du référentiel à la place"})
        elif mode == "remove" and not in_ref:
            skipped.append({"code": code, "reason": "absent du référentiel"})
        else:
            done.append((sid, code))
    ids_ok = [d[0] for d in done]
    if ids_ok and mode == "remove":
        db.execute(text("""
            UPDATE sites SET in_reference = FALSE, ref_status = NULL, ref_source = NULL, ref_updated_at = now(),
                is_active = is_supervised, updated_at = now()
            WHERE id = ANY(:ids)"""), {"ids": ids_ok})
        evaluate_sites(db, ids_ok)
    elif ids_ok:
        db.execute(text("DELETE FROM sites WHERE id = ANY(:ids)"), {"ids": ids_ok})
    missing = len(ids) - len(rows)
    anomalies = reconcile_anomalies(db)
    return {"done": [d[1] for d in done], "skipped": skipped, "not_found": missing, "anomalies": anomalies}


def link_unknown(db: Session, site_id: int, target_code: str, user: str, note: str | None) -> dict:
    """Rattache un site remonté par un OMC (inconnu du référentiel) à un site du référentiel :
    ses équipements, alarmes et historique d'équipements sont transférés, et une correspondance
    de codes est enregistrée pour les collectes suivantes."""
    src = db.execute(text("SELECT id, external_id, in_reference FROM sites WHERE id = :id FOR UPDATE"),
                     {"id": site_id}).first()
    if src is None:
        raise ManageError("Site introuvable", 404)
    if src[2]:
        raise ManageError(f"Le site {src[1]} est déjà au référentiel")
    target_code = target_code.strip().upper()
    tgt = db.execute(text("SELECT id FROM sites WHERE external_id = :c AND in_reference FOR UPDATE"),
                     {"c": target_code}).scalar()
    if tgt is None:
        raise ManageError(f"Le site {target_code} n'existe pas au référentiel")
    if tgt == src[0]:
        raise ManageError("Un site ne peut pas être rattaché à lui-même")
    moved = db.execute(text("UPDATE site_elements SET site_id = :t WHERE site_id = :s"), {"t": tgt, "s": src[0]}).rowcount
    db.execute(text("UPDATE alarms SET site_id = :t WHERE site_id = :s"), {"t": tgt, "s": src[0]})
    db.execute(text("UPDATE status_history SET site_id = :t WHERE site_id = :s AND entity_type = 'ELEMENT'"),
               {"t": tgt, "s": src[0]})
    db.execute(text("""
        INSERT INTO site_code_aliases (omc_code, site_external_id, note, created_by)
        VALUES (:o, :t, :n, :u)
        ON CONFLICT (omc_code) DO UPDATE SET site_external_id = EXCLUDED.site_external_id, note = EXCLUDED.note,
            created_by = EXCLUDED.created_by, created_at = now()"""),
        {"o": src[1], "t": target_code, "n": note, "u": user})
    db.execute(text("UPDATE site_code_aliases SET site_external_id = :t WHERE site_external_id = :o"),
               {"t": target_code, "o": src[1]})
    db.execute(text("DELETE FROM sites WHERE id = :id"), {"id": src[0]})
    evaluate_sites(db, [tgt])
    anomalies = reconcile_anomalies(db)
    return {"omc_code": src[1], "site": target_code, "site_id": tgt, "elements_moved": moved, "anomalies": anomalies}


def delete_alias(db: Session, omc_code: str) -> bool:
    return bool(db.execute(text("DELETE FROM site_code_aliases WHERE omc_code = :o"), {"o": omc_code}).rowcount)


def to_json(v) -> str:
    return json.dumps(v, default=str, ensure_ascii=False)
