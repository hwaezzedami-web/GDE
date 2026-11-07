"""Service de collecte : planification, exécution isolée par source, reprise sur erreur.

Lancement : python -m app.collector.runner   (service gsm-collector)

- Chaque source OMC activée est collectée selon son propre intervalle.
- Une source en erreur n'affecte pas les autres (exécutions indépendantes).
- Un verrou PostgreSQL (advisory lock) empêche deux collecteurs de traiter la
  même source en même temps (redondance possible).
- Tâches périodiques : réévaluation des états (vieillissement des données),
  instantanés pour les courbes, battement de cœur, purge des historiques.
"""
from __future__ import annotations

import logging
import signal
import socket
import time
import traceback
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, text

from ..config import get_settings
from ..db import SessionLocal, session_scope
from ..logging_setup import setup_logging
from ..models import CollectionRun, OmcSource
from ..reference.anomalies import reconcile_anomalies
from ..reference.watch import run_watch
from ..services.ingest import ingest
from ..services.settings_service import get_setting
from ..services.status_engine import evaluate_all_locked
from .connectors.base import ConnectorError, SourceSpec
from .registry import build_connector

log = logging.getLogger("gsm.collector")
HOST = socket.gethostname()
LOCK_NS = 7_421_000   # espace de noms des verrous applicatifs


def _spec(o: OmcSource) -> SourceSpec:
    return SourceSpec(id=o.id, code=o.code, vendor=o.vendor, connector_type=o.connector_type,
                      config=o.config or {}, poll_interval_s=o.poll_interval_s, is_demo=o.is_demo)


def run_source(source_id: int, sleep=time.sleep) -> str:
    """Exécute une collecte complète pour une source. Retourne le statut final."""
    db = SessionLocal()
    lock_conn = None
    try:
        # Verrou exclusif par source (connexion dédiée, libéré à la fin)
        lock_conn = db.get_bind().connect()
        got = lock_conn.execute(text("SELECT pg_try_advisory_lock(:ns, :id)"),
                                {"ns": LOCK_NS, "id": source_id}).scalar()
        lock_conn.commit()
        if not got:
            log.info("Source %s déjà en cours de collecte ailleurs : ignorée", source_id)
            return "SKIPPED"

        src = db.get(OmcSource, source_id)
        if src is None or not src.enabled:
            return "SKIPPED"
        cfg = get_setting(db, "collector")
        now = datetime.now(timezone.utc)
        run = CollectionRun(omc_source_id=src.id, status="RUNNING", started_at=now)
        db.add(run)
        src.last_attempt_at = now
        src.last_status = "RUNNING"
        src.sync_requested_at = None
        db.commit()
        spec = _spec(src)

        result, error, attempts = None, None, 0
        max_attempts = int(cfg["max_retries"]) + 1
        while attempts < max_attempts:
            attempts += 1
            connector = None
            try:
                connector = build_connector(spec)
                result = connector.collect()
                error = None
                break
            except ConnectorError as exc:
                error = exc
                log.warning("[%s] tentative %d/%d échouée : %s", spec.code, attempts, max_attempts, exc)
                if not exc.transient:
                    break
            except Exception as exc:  # erreur inattendue d'un connecteur : on isole
                error = exc
                log.error("[%s] erreur inattendue : %s\n%s", spec.code, exc, traceback.format_exc())
                break
            finally:
                if connector is not None:
                    try:
                        connector.close()
                    except Exception:
                        pass
            if attempts < max_attempts:
                sleep(int(cfg["retry_backoff_s"]) * (2 ** (attempts - 1)))

        run = db.get(CollectionRun, run.id)
        src = db.get(OmcSource, source_id)
        run.attempts = attempts
        if error is not None:
            msg = str(error)[:2000]
            run.status, run.error_message = "FAILED", msg
            run.finished_at = datetime.now(timezone.utc)
            src.last_status, src.last_error = "FAILED", msg
            src.consecutive_failures += 1
            db.commit()
            log.error("[%s] collecte en échec (%d tentative(s)) : %s", spec.code, attempts, msg)
            return "FAILED"

        try:
            stats = ingest(db, src, result)
        except Exception as exc:
            db.rollback()
            run = db.get(CollectionRun, run.id)
            src = db.get(OmcSource, source_id)
            msg = f"Erreur d'intégration en base : {exc}"[:2000]
            run.status, run.error_message, run.finished_at = "FAILED", msg, datetime.now(timezone.utc)
            src.last_status, src.last_error = "FAILED", msg
            src.consecutive_failures += 1
            db.commit()
            log.exception("[%s] intégration en échec", spec.code)
            return "FAILED"

        status = "PARTIAL" if stats.rejected else "SUCCESS"
        run.status = status
        run.finished_at = datetime.now(timezone.utc)
        run.sites_processed, run.elements_processed = stats.sites, stats.elements
        run.alarms_processed, run.records_rejected = stats.alarms, stats.rejected
        run.details = {**stats.as_dict(), "connector": result.details}
        src.last_status, src.last_error = status, (f"{stats.rejected} enregistrement(s) rejeté(s)"
                                                   if stats.rejected else None)
        src.last_success_at = run.finished_at
        src.consecutive_failures = 0
        db.commit()
        log.info("[%s] %s : %d sites, %d équipements, %d alarmes, %d rejets, %d transitions de site",
                 spec.code, status, stats.sites, stats.elements, stats.alarms, stats.rejected,
                 stats.site_transitions)
        reconcile()      # sites inconnus du référentiel, sites démontés encore actifs…
        return status
    finally:
        if lock_conn is not None:
            try:
                lock_conn.execute(text("SELECT pg_advisory_unlock(:ns, :id)"), {"ns": LOCK_NS, "id": source_id})
                lock_conn.commit()
            finally:
                lock_conn.close()
        db.close()


def evaluate_all() -> None:
    res = evaluate_all_locked()
    if res and res["transitions"]:
        log.info("Réévaluation : %d transition(s) d'état", res["transitions"])


def reconcile() -> None:
    """Rapprochement référentiel <-> OMC (anomalies). Une erreur ici n'affecte pas la collecte."""
    try:
        with session_scope() as db:
            res = reconcile_anomalies(db)
        if res["new"] or res["resolved"]:
            log.info("Rapprochement référentiel : %d nouvelle(s) anomalie(s), %d résolue(s)",
                     res["new"], res["resolved"])
    except Exception:
        log.exception("Rapprochement référentiel en échec")


def watch_reference() -> None:
    try:
        run_watch()
    except Exception:
        log.exception("Import automatique du référentiel en échec")


def take_snapshot() -> None:
    with session_scope() as db:
        db.execute(text("""
            INSERT INTO kpi_snapshots (taken_at, vendor, wilaya_code, total, up, down, degraded, unknown)
            SELECT date_trunc('minute', now()), vendor, coalesce(wilaya_code, 0), count(*),
                   count(*) FILTER (WHERE status = 'UP'), count(*) FILTER (WHERE status = 'DOWN'),
                   count(*) FILTER (WHERE status = 'DEGRADED'), count(*) FILTER (WHERE status = 'UNKNOWN')
            FROM sites WHERE is_active AND (NOT in_reference OR is_supervised)   -- sites supervisés uniquement
            GROUP BY vendor, coalesce(wilaya_code, 0)
            ON CONFLICT DO NOTHING
        """))


def heartbeat(started_at: datetime, info: dict) -> None:
    with session_scope() as db:
        db.execute(text("""
            INSERT INTO service_heartbeats (service, host, last_beat, started_at, info)
            VALUES ('collector', :h, now(), :s, CAST(:i AS jsonb))
            ON CONFLICT (service, host) DO UPDATE SET last_beat = now(), started_at = EXCLUDED.started_at,
                                                    info = EXCLUDED.info
        """), {"h": HOST, "s": started_at, "i": __import__("json").dumps(info)})


def housekeeping() -> None:
    with session_scope() as db:
        cfg = get_setting(db, "collector")
        db.execute(text("DELETE FROM status_history WHERE changed_at < now() - make_interval(days => :d)"),
                   {"d": int(cfg["history_retention_days"])})
        db.execute(text("DELETE FROM collection_runs WHERE started_at < now() - make_interval(days => :d)"),
                   {"d": int(cfg["runs_retention_days"])})
        db.execute(text("DELETE FROM kpi_snapshots WHERE taken_at < now() - make_interval(days => :d)"),
                   {"d": int(cfg["snapshots_retention_days"])})
        db.execute(text("DELETE FROM alarms WHERE state = 'CLEARED' AND cleared_at < now() - make_interval(days => :d)"),
                   {"d": int(cfg["history_retention_days"])})
    log.info("Purge des historiques effectuée")


class CollectorService:
    def __init__(self):
        self.sched = BlockingScheduler(timezone="UTC", job_defaults={"coalesce": True, "max_instances": 1,
                                                                     "misfire_grace_time": 60})
        self.started_at = datetime.now(timezone.utc)
        self.intervals: dict[int, int] = {}

    def sync_jobs(self) -> None:
        """Aligne les tâches planifiées sur la configuration des sources en base."""
        with session_scope() as db:
            sources = db.scalars(select(OmcSource)).all()
            wanted = {o.id: o for o in sources if o.enabled and o.connector_type != "manual_csv"}
            requested = [o.id for o in wanted.values() if o.sync_requested_at is not None]
        for sid in list(self.intervals):
            if sid not in wanted:
                self.sched.remove_job(f"src-{sid}")
                del self.intervals[sid]
                log.info("Source %s désactivée : collecte arrêtée", sid)
        for sid, o in wanted.items():
            if self.intervals.get(sid) != o.poll_interval_s:
                self.sched.add_job(run_source, IntervalTrigger(seconds=o.poll_interval_s), args=[sid],
                                   id=f"src-{sid}", replace_existing=True, next_run_time=datetime.now(timezone.utc))
                self.intervals[sid] = o.poll_interval_s
                log.info("Source %s (%s) planifiée toutes les %d s", o.code, o.connector_type, o.poll_interval_s)
        for sid in requested:   # synchronisation immédiate demandée depuis l'interface
            job = self.sched.get_job(f"src-{sid}")
            if job:
                job.modify(next_run_time=datetime.now(timezone.utc))

    def start(self) -> None:
        with session_scope() as db:
            cfg = get_setting(db, "collector")
        self.sched.add_job(self.sync_jobs, IntervalTrigger(seconds=20), id="sync-jobs",
                           next_run_time=datetime.now(timezone.utc))
        self.sched.add_job(evaluate_all, IntervalTrigger(seconds=int(cfg["evaluate_every_s"])), id="evaluate")
        self.sched.add_job(take_snapshot, IntervalTrigger(seconds=int(cfg["snapshot_every_s"])), id="snapshot",
                           next_run_time=datetime.now(timezone.utc))
        self.sched.add_job(lambda: heartbeat(self.started_at, {"sources": len(self.intervals)}),
                           IntervalTrigger(seconds=30), id="heartbeat", next_run_time=datetime.now(timezone.utc))
        self.sched.add_job(housekeeping, IntervalTrigger(hours=24), id="housekeeping")
        self.sched.add_job(reconcile, IntervalTrigger(seconds=300), id="reconcile",
                           next_run_time=datetime.now(timezone.utc))
        with session_scope() as db:
            ref = get_setting(db, "reference")
        self.sched.add_job(watch_reference, IntervalTrigger(seconds=int(ref["watch_interval_s"])),
                           id="reference-watch")

        def _stop(*_):
            log.info("Arrêt demandé")
            self.sched.shutdown(wait=False)
        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)
        log.info("Service de collecte démarré sur %s", HOST)
        self.sched.start()


def main() -> None:
    s = get_settings()
    setup_logging("collector", s.log_level, s.log_dir)
    # Attente de la base au démarrage (reprise après incident / démarrage simultané)
    for i in range(60):
        try:
            with session_scope() as db:
                db.execute(text("SELECT 1 FROM omc_sources LIMIT 1"))
            break
        except Exception as exc:
            log.warning("Base indisponible (%s), nouvel essai dans 5 s…", exc.__class__.__name__)
            time.sleep(5)
    CollectorService().start()


if __name__ == "__main__":
    main()
