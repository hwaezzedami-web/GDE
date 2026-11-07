"""Rapprochement référentiel ↔ OMC : détection et suivi des anomalies.

Anomalies calculées (une ligne ouverte par site et par type, résolue automatiquement
quand la condition disparaît) :
  UNKNOWN_SITE       site remonté par un OMC mais absent du référentiel (contrôle actif dès
                     qu'un référentiel a été importé)
  REMOVED_BUT_ACTIVE démonté / désinstallé au référentiel mais UP ou DÉGRADÉ dans l'OMC
  PLANNED_BUT_ACTIVE en projet au référentiel mais déjà en service dans l'OMC
                     (référentiel à mettre à jour)
  SUPERVISION_LOST   en service au référentiel, déjà vu par un OMC, mais plus remonté depuis
                     supervision_lost_days jours
  NEVER_SUPERVISED   en service au référentiel, jamais remonté par un OMC (contrôle optionnel :
                     detect_never_supervised, à activer quand tous les OMC sont raccordés)
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..services.settings_service import get_setting

LABELS = {
    "UNKNOWN_SITE": "Site remonté par un OMC, absent du référentiel",
    "REMOVED_BUT_ACTIVE": "Site démonté au référentiel mais actif dans l'OMC",
    "PLANNED_BUT_ACTIVE": "Site en projet au référentiel mais déjà en service",
    "SUPERVISION_LOST": "Site en service plus remonté par aucun OMC",
    "NEVER_SUPERVISED": "Site en service jamais remonté par un OMC",
}


def reconcile_anomalies(db: Session) -> dict:
    """Recalcule l'ensemble des anomalies. N'effectue pas de commit."""
    cfg = get_setting(db, "reference")
    db.execute(text("SELECT pg_advisory_xact_lock(7421003)"))   # un seul rapprochement à la fois
    params = {"days": int(cfg["supervision_lost_days"]), "never": bool(cfg["detect_never_supervised"])}
    db.execute(text("""
        CREATE TEMP TABLE IF NOT EXISTS _anom (anomaly_type text, site_id bigint, ext text, details jsonb)
        ON COMMIT DROP"""))
    db.execute(text("TRUNCATE _anom"))
    db.execute(text("""
        WITH ref_loaded AS (SELECT EXISTS (SELECT 1 FROM sites WHERE in_reference) AS ok),
        src AS (
            SELECT e.site_id, string_agg(DISTINCT o.code, ', ') AS sources, count(*) AS elements,
                   array_agg(DISTINCT e.technology ORDER BY e.technology) AS techs
            FROM site_elements e JOIN omc_sources o ON o.id = e.omc_source_id
            WHERE e.is_active GROUP BY e.site_id
        )
        INSERT INTO _anom
        SELECT 'UNKNOWN_SITE', s.id, s.external_id,
               jsonb_build_object('sources', src.sources, 'elements', src.elements, 'technologies', src.techs,
                                  'status', s.status, 'vendor', s.vendor)
        FROM sites s JOIN src ON src.site_id = s.id, ref_loaded
        WHERE ref_loaded.ok AND s.is_active AND NOT s.in_reference
        UNION ALL
        SELECT CASE s.ref_status WHEN 'REMOVED' THEN 'REMOVED_BUT_ACTIVE' ELSE 'PLANNED_BUT_ACTIVE' END,
               s.id, s.external_id,
               jsonb_build_object('lifecycle', s.lifecycle, 'status', s.status, 'sources', src.sources,
                                  'technologies', src.techs)
        FROM sites s JOIN src ON src.site_id = s.id
        WHERE s.in_reference AND s.ref_status IN ('REMOVED', 'PLANNED') AND s.status IN ('UP', 'DEGRADED')
        UNION ALL
        SELECT 'SUPERVISION_LOST', s.id, s.external_id,
               jsonb_build_object('last_supervised_at', s.last_supervised_at, 'lifecycle', s.lifecycle)
        FROM sites s
        WHERE s.in_reference AND s.ref_status = 'IN_SERVICE' AND s.last_supervised_at IS NOT NULL
          AND s.last_supervised_at < now() - make_interval(days => :days)
        UNION ALL
        SELECT 'NEVER_SUPERVISED', s.id, s.external_id, jsonb_build_object('lifecycle', s.lifecycle)
        FROM sites s
        WHERE CAST(:never AS boolean) AND s.in_reference AND s.ref_status = 'IN_SERVICE'
          AND s.last_supervised_at IS NULL
    """), params)
    # Suggestion pour les sites inconnus : code du référentiel le plus proche (faute de frappe, préfixe…)
    db.execute(text("""
        UPDATE _anom a SET details = a.details || jsonb_build_object('suggestion', sug.external_id)
        FROM (
            SELECT a2.site_id, (SELECT r.external_id FROM sites r
                                WHERE r.in_reference AND r.external_id % a2.ext AND similarity(r.external_id, a2.ext) >= 0.5
                                ORDER BY similarity(r.external_id, a2.ext) DESC LIMIT 1) AS external_id
            FROM _anom a2 WHERE a2.anomaly_type = 'UNKNOWN_SITE' LIMIT 2000
        ) sug
        WHERE a.site_id = sug.site_id AND a.anomaly_type = 'UNKNOWN_SITE' AND sug.external_id IS NOT NULL
    """))
    created = db.execute(text("""
        WITH ins AS (
            INSERT INTO site_anomalies (anomaly_type, site_id, site_external_id, details)
            SELECT anomaly_type, site_id, ext, details FROM _anom
            ON CONFLICT (anomaly_type, site_id) WHERE resolved_at IS NULL
            DO UPDATE SET last_detected_at = now(), details = EXCLUDED.details, site_external_id = EXCLUDED.site_external_id
            RETURNING (xmax = 0) AS inserted
        ) SELECT count(*) FILTER (WHERE inserted) FROM ins
    """)).scalar()
    resolved = db.execute(text("""
        UPDATE site_anomalies sa SET resolved_at = now(), state = 'RESOLVED'
        WHERE sa.resolved_at IS NULL
          AND NOT EXISTS (SELECT 1 FROM _anom a WHERE a.anomaly_type = sa.anomaly_type AND a.site_id = sa.site_id)
    """)).rowcount
    counts = dict(db.execute(text("""SELECT anomaly_type, count(*) FROM site_anomalies
                                     WHERE resolved_at IS NULL GROUP BY 1""")).all())
    return {"new": created or 0, "resolved": resolved or 0, "open": counts}
