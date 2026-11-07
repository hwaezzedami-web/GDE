"""Import du référentiel de sites : prévisualisation (différentiel), application, reclassement.

Deux modes :
  update : ajoute les nouveaux sites et met à jour les sites présents dans le fichier ;
  sync   : idem, et les sites du référentiel ABSENTS du fichier en sortent (non supprimés :
           ils restent visibles s'ils sont encore remontés par un OMC, et sont alors signalés).
Garde-fou : une synchronisation qui retirerait plus de max_removal_pct % des sites est refusée
sans confirmation explicite (fichier tronqué, mauvaise feuille…).
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..services.settings_service import get_setting
from ..services.status_engine import evaluate_sites
from .anomalies import reconcile_anomalies
from .mapping import TARGETS, Normalized, RefSite, build_wilaya_resolver, detect_mapping, normalize
from .parsers import ParsedTable, read_reference_file

log = logging.getLogger(__name__)
MOVE_THRESHOLD_M = 30
SAMPLE = 300


def _dist_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def classify(lifecycle: str | None, settings: dict) -> str:
    if not lifecycle:
        return settings["lifecycle_missing"]
    return settings["lifecycle_map"].get(lifecycle.strip().lower(), settings["lifecycle_unknown"])


@dataclass
class Plan:
    table: ParsedTable
    mapping: dict
    norm: Normalized
    new: list[dict]
    updated: list[dict]
    unchanged: int
    removed: list[dict]
    counts: dict
    warnings: list[str]
    sha256: str
    rows: list[dict]          # lignes prêtes à écrire


def build_plan(db: Session, filename: str, content: bytes, mapping: dict | None, mode: str,
               code_digits: int | None, sheet: str | None = None) -> Plan:
    settings = get_setting(db, "reference")
    table = read_reference_file(filename, content, sheet)
    detected = detect_mapping(table)
    used = {t: (mapping or {}).get(t, detected.get(t)) for t in TARGETS}
    for t, c in used.items():
        valid = set(table.columns) | ({"__geometry__"} if table.has_geometry else set()) | {"__placemark__"}
        if c and c not in valid:
            raise ValueError(f"Colonne « {c} » absente du fichier (champ {t})")
    norm = normalize(table, used, code_digits)

    wil = db.execute(text("SELECT code, name, chef_lieu FROM wilayas")).all()
    resolve = build_wilaya_resolver([tuple(r) for r in wil])
    existing = {r["external_id"]: r for r in db.execute(text("""
        SELECT external_id, name, latitude, longitude, wilaya_code, commune, address, dr, lifecycle, ref_status,
               ref_technologies, in_reference, is_supervised, ref_source
        FROM sites""")).mappings()}

    warnings: list[str] = []
    unresolved: dict[str, int] = {}
    rows, new, updated = [], [], []
    unchanged = 0
    status_counts: dict[str, int] = {}
    for s in norm.sites:
        ref_status = classify(s.lifecycle, settings)
        status_counts[ref_status] = status_counts.get(ref_status, 0) + 1
        wcode = resolve(s.wilaya_label) if settings["wilaya_from"] == "file" else None
        if settings["wilaya_from"] == "file" and s.wilaya_label and wcode is None:
            unresolved[s.wilaya_label] = unresolved.get(s.wilaya_label, 0) + 1
        row = {"code": s.code, "name": s.name, "lat": s.lat, "lon": s.lon, "wilaya": wcode,
               "commune": s.commune, "address": s.address, "dr": s.dr, "lifecycle": s.lifecycle,
               "ref_status": ref_status, "techs": s.technologies,
               "attrs": dict(s.attributes, **({"Wilaya (fichier)": s.wilaya_label} if s.wilaya_label else {}))}
        rows.append(row)
        old = existing.get(s.code)
        if old is None or not old["in_reference"]:
            new.append({"code": s.code, "name": s.name, "wilaya": s.wilaya_label, "ref_status": ref_status,
                        "omc": bool(old and old["is_supervised"])})
            continue
        changes = []
        if old["latitude"] is not None and _dist_m(old["latitude"], old["longitude"], s.lat, s.lon) > MOVE_THRESHOLD_M:
            changes.append(f"déplacé de {_dist_m(old['latitude'], old['longitude'], s.lat, s.lon):.0f} m")
        if (s.name or old["name"]) != old["name"] and s.name:
            changes.append(f"nom : {old['name']} → {s.name}")
        if s.lifecycle != old["lifecycle"]:
            changes.append(f"cycle de vie : {old['lifecycle'] or '—'} → {s.lifecycle or '—'}")
        if s.dr and s.dr != old["dr"]:
            changes.append(f"DR : {old['dr'] or '—'} → {s.dr}")
        if wcode and wcode != old["wilaya_code"]:
            changes.append(f"wilaya : {old['wilaya_code'] or '—'} → {wcode}")
        if sorted(s.technologies) != sorted(old["ref_technologies"] or []):
            changes.append(f"technologies : {'/'.join(old['ref_technologies'] or []) or '—'} → "
                           f"{'/'.join(s.technologies) or '—'}")
        if s.commune and s.commune != old["commune"]:
            changes.append(f"commune : {old['commune'] or '—'} → {s.commune}")
        if changes:
            updated.append({"code": s.code, "name": s.name or old["name"], "changes": changes})
        else:
            unchanged += 1

    in_file = {s.code for s in norm.sites}
    removed = []
    if mode == "sync":
        removed = [{"code": c, "name": r["name"], "omc": r["is_supervised"]}
                   for c, r in existing.items() if r["in_reference"] and c not in in_file]
    ref_total = sum(1 for r in existing.values() if r["in_reference"])
    removal_pct = round(100 * len(removed) / ref_total, 1) if ref_total else 0.0
    supervised_absent = sum(1 for c, r in existing.items() if r["is_supervised"] and c not in in_file)
    manual_updated = sum(1 for u in updated if existing[u["code"]]["ref_source"] == "MANUAL")
    manual_removed = sum(1 for r in removed if existing[r["code"]]["ref_source"] == "MANUAL")
    if manual_updated:
        warnings.append(f"{manual_updated} site(s) modifié(s) manuellement dans l'application seront remplacés "
                        "par les valeurs du fichier")
    if manual_removed:
        warnings.append(f"{manual_removed} site(s) ajouté(s) ou modifié(s) manuellement sont absents du fichier "
                        "et sortiront du référentiel")
    for label, n in sorted(unresolved.items(), key=lambda x: -x[1])[:20]:
        warnings.append(f"Wilaya « {label} » non reconnue ({n} sites) : déduite des coordonnées")
    if code_digits is None and table.format in ("xlsx", "csv"):
        lens = [len(s.code) for s in norm.sites if s.code.isdigit()]
        ref_lens = [len(c) for c, r in existing.items() if r["in_reference"] and c.isdigit()]
        if lens and ref_lens and min(lens) < min(ref_lens):
            warnings.append(f"Des codes numériques ont moins de {min(ref_lens)} chiffres : zéros de tête perdus "
                            f"par Excel ? Utiliser l'option « compléter à {min(ref_lens)} chiffres ».")

    counts = {
        "rows": len(table.rows), "valid": len(norm.sites), "invalid": len(norm.invalid), "fixed": len(norm.fixes),
        "new": len(new), "updated": len(updated), "unchanged": unchanged, "removed": len(removed),
        "removal_pct": removal_pct, "reference_before": ref_total, "by_status": status_counts,
        "new_already_in_omc": sum(1 for x in new if x["omc"]), "supervised_not_in_file": supervised_absent,
        "code_digits": code_digits,
    }
    return Plan(table, used, norm, new, updated, unchanged, removed, counts, warnings + table.warnings,
                hashlib.sha256(content).hexdigest(), rows)


def plan_summary(plan: Plan, settings: dict) -> dict:
    safe = plan.counts["removal_pct"] <= settings["max_removal_pct"]
    return {
        "format": plan.table.format, "sheet": plan.table.sheet, "columns": plan.table.columns,
        "has_geometry": plan.table.has_geometry, "mapping": plan.mapping,
        "detected_mapping": detect_mapping(plan.table), "counts": plan.counts, "warnings": plan.warnings,
        "sample_new": plan.new[:SAMPLE], "sample_updated": plan.updated[:SAMPLE],
        "sample_removed": plan.removed[:SAMPLE], "invalid": plan.norm.invalid[:SAMPLE],
        "fixes": plan.norm.fixes[:SAMPLE], "safe_to_apply": safe,
        "max_removal_pct": settings["max_removal_pct"], "sha256": plan.sha256,
        "preview_rows": [{k: r.get(k) for k in ("code", "name", "lat", "lon", "wilaya", "dr", "lifecycle",
                                                 "ref_status", "techs")} for r in plan.rows[:20]],
    }


def _adopt_omc_codes(db: Session, codes: list[str]) -> int:
    """Un site créé par un OMC sous « 5474 » prend le code du référentiel « 05474 » (correspondance
    unique, code du référentiel encore inconnu) : son historique et ses équipements sont conservés."""
    pairs = db.execute(text("""
        WITH f AS (SELECT DISTINCT unnest(CAST(:codes AS text[])) AS code),
        m AS (
            SELECT s.id, f.code, count(*) OVER (PARTITION BY f.code) AS n_site,
                   count(*) OVER (PARTITION BY s.id) AS n_code
            FROM sites s JOIN f ON ltrim(s.external_id, '0') = ltrim(f.code, '0') AND ltrim(f.code, '0') <> ''
            WHERE NOT s.in_reference AND s.external_id <> f.code
              AND NOT EXISTS (SELECT 1 FROM sites x WHERE x.external_id = f.code)
        ) SELECT id, code FROM m WHERE n_site = 1 AND n_code = 1"""), {"codes": codes}).all()
    if pairs:
        db.execute(text("""UPDATE sites SET extra = extra || jsonb_build_object('omc_code', external_id),
                           external_id = :code, updated_at = now() WHERE id = :id"""),
                   [{"id": i, "code": c} for i, c in pairs])
    return len(pairs)


def apply_plan(db: Session, plan: Plan, mode: str, username: str | None, origin: str, filename: str,
               confirm_large_removal: bool = False) -> dict:
    settings = get_setting(db, "reference")
    now = datetime.now(timezone.utc)
    imp_id = db.execute(text("""
        INSERT INTO reference_imports (username, origin, file_name, file_sha256, file_format, mode, status,
                                       mapping, counts, messages)
        VALUES (:u, :o, :f, :h, :fmt, :m, 'FAILED', CAST(:map AS jsonb), CAST(:c AS jsonb), '[]'::jsonb)
        RETURNING id"""), {"u": username, "o": origin, "f": filename[:200], "h": plan.sha256,
                           "fmt": plan.table.format, "m": mode, "map": json.dumps(plan.mapping),
                           "c": json.dumps(plan.counts)}).scalar()
    if mode == "sync" and plan.counts["removal_pct"] > settings["max_removal_pct"] and not confirm_large_removal:
        msg = (f"Synchronisation refusée : elle retirerait {plan.counts['removed']} sites "
               f"({plan.counts['removal_pct']} % du référentiel, seuil {settings['max_removal_pct']} %). "
               "Vérifier le fichier, ou confirmer explicitement.")
        db.execute(text("""UPDATE reference_imports SET status = 'REFUSED', finished_at = now(),
                           messages = CAST(:m AS jsonb) WHERE id = :i"""), {"m": json.dumps([msg]), "i": imp_id})
        return {"import_id": imp_id, "status": "REFUSED", "message": msg, "counts": plan.counts}
    if not plan.rows:
        raise ValueError("Aucun site valide dans le fichier")

    payload = [{
        "ext": r["code"], "name": (r["name"] or r["code"])[:200], "name_given": bool(r["name"]),
        "lat": r["lat"], "lon": r["lon"], "wilaya": r["wilaya"], "commune": r["commune"],
        "address": r["address"], "dr": r["dr"], "lifecycle": r["lifecycle"], "ref_status": r["ref_status"],
        "techs": r["techs"], "imp": imp_id, "now": now, "user": username or origin.lower(),
        "extra": json.dumps({"reference": r["attrs"]}, default=str, ensure_ascii=False),
    } for r in plan.rows]
    renamed = _adopt_omc_codes(db, [r["code"] for r in plan.rows]) if settings["match_leading_zeros"] else 0
    sql = text("""
        INSERT INTO sites (external_id, name, vendor, latitude, longitude, wilaya_code, commune, address, dr,
                           lifecycle, ref_status, ref_technologies, in_reference, reference_seen_at,
                           reference_import_id, extra, status_since, status_reason,
                           ref_source, ref_updated_at, ref_updated_by)
        VALUES (:ext, :name, 'UNKNOWN', :lat, :lon, :wilaya, :commune, :address, :dr, :lifecycle, :ref_status,
                CAST(:techs AS text[]), TRUE, :now, :imp, CAST(:extra AS jsonb), now(),
                'Non supervisé : aucun OMC ne remonte ce site', 'IMPORT', :now, :user)
        ON CONFLICT (external_id) DO UPDATE SET
            name = CASE WHEN CAST(:name_given AS boolean) THEN EXCLUDED.name ELSE sites.name END,
            latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude,
            wilaya_code = coalesce(EXCLUDED.wilaya_code, sites.wilaya_code),
            commune = coalesce(EXCLUDED.commune, sites.commune),
            address = coalesce(EXCLUDED.address, sites.address),
            dr = coalesce(EXCLUDED.dr, sites.dr),
            lifecycle = EXCLUDED.lifecycle, ref_status = EXCLUDED.ref_status,
            ref_technologies = EXCLUDED.ref_technologies,
            in_reference = TRUE, reference_seen_at = EXCLUDED.reference_seen_at,
            reference_import_id = EXCLUDED.reference_import_id,
            ref_source = 'IMPORT', ref_updated_at = EXCLUDED.ref_updated_at, ref_updated_by = EXCLUDED.ref_updated_by,
            extra = sites.extra || EXCLUDED.extra, is_active = TRUE, updated_at = now()
    """)
    for i in range(0, len(payload), 2000):
        db.execute(sql, payload[i:i + 2000])
    codes = [r["code"] for r in plan.rows]

    # Wilaya : déduite des coordonnées (paramètre, ou libellé non reconnu)
    db.execute(text(f"""
        UPDATE sites s SET wilaya_code = w.code FROM wilayas w
        WHERE s.reference_import_id = :imp AND w.boundary IS NOT NULL AND s.geom IS NOT NULL
          AND {'TRUE' if settings['wilaya_from'] == 'coordinates' else 's.wilaya_code IS NULL'}
          AND ST_Covers(w.boundary, s.geom) AND s.wilaya_code IS DISTINCT FROM w.code
    """), {"imp": imp_id})

    removed_ids: list[int] = []
    if mode == "sync":
        removed_ids = [r[0] for r in db.execute(text("""
            UPDATE sites SET in_reference = FALSE, ref_status = NULL, ref_source = NULL, is_active = is_supervised, updated_at = now()
            WHERE in_reference AND NOT (external_id = ANY(:codes)) RETURNING id"""), {"codes": codes})]

    site_ids = [r[0] for r in db.execute(text("SELECT id FROM sites WHERE reference_import_id = :i"), {"i": imp_id})]
    ev = evaluate_sites(db, site_ids + removed_ids)
    anomalies = reconcile_anomalies(db)
    counts = dict(plan.counts, applied=len(payload), removed_applied=len(removed_ids), omc_codes_adopted=renamed)
    msgs = [f"{len(payload)} sites écrits", *plan.warnings[:20]]
    if renamed:
        msgs.append(f"{renamed} site(s) remonté(s) par un OMC rapproché(s) de leur code au référentiel (zéros de tête)")
    db.execute(text("""UPDATE reference_imports SET status = 'APPLIED', finished_at = now(),
                       counts = CAST(:c AS jsonb), messages = CAST(:m AS jsonb) WHERE id = :i"""),
               {"c": json.dumps(counts), "m": json.dumps(msgs, ensure_ascii=False), "i": imp_id})
    log.info("Référentiel importé (%s, %s) : %s", origin, mode, counts)
    return {"import_id": imp_id, "status": "APPLIED", "counts": counts, "evaluation": ev, "anomalies": anomalies}


def reclassify(db: Session) -> int:
    """Recalcule ref_status après une modification de la table des cycles de vie."""
    settings = get_setting(db, "reference")
    rows = db.execute(text("SELECT id, lifecycle, ref_status FROM sites WHERE in_reference")).all()
    upd = [{"id": i, "st": classify(lc, settings)} for i, lc, st in rows if classify(lc, settings) != st]
    if upd:
        db.execute(text("UPDATE sites SET ref_status = :st, updated_at = now() WHERE id = :id"), upd)
    reconcile_anomalies(db)
    return len(upd)


def export_reference_rows(db: Session) -> list[dict]:
    return [dict(r) for r in db.execute(text("""
        SELECT s.external_id, s.name, s.latitude, s.longitude, s.wilaya_code, w.name AS wilaya_name, s.commune,
               s.address, s.dr, s.lifecycle, s.ref_status, array_to_string(s.ref_technologies, '|') AS technologies,
               s.reference_seen_at
        FROM sites s LEFT JOIN wilayas w ON w.code = s.wilaya_code
        WHERE s.in_reference ORDER BY s.external_id""")).mappings()]


__all__ = ["build_plan", "plan_summary", "apply_plan", "reclassify", "RefSite", "export_reference_rows"]
