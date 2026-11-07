"""Exécution d'une collecte : connecteur -> ingestion -> moteur d'états -> journal.

Une collecte en échec ne touche jamais aux équipements : elle met la source en FAILED, puis le moteur
recalcule les sites concernés, qui passent à INCONNU (jamais DOWN).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..services.ingest import IngestStats, ingest
from ..services.status_engine import EvaluationStats, evaluate_sites
from .connectors.base import Connector, ConnectorError, ConnectorNotConfigured, SourceSpec
from .connectors.demo import DemoConnector

log = logging.getLogger(__name__)

REGISTRY: dict[str, Connector] = {
    "demo": DemoConnector(),
}

DEMO_CODE = "DEMO-01"
DEMO_VALUE_MAPS = {"status": {"1": "UP", "0": "DOWN", "2": "DEGRADED", "9": "UNKNOWN"}}


@dataclass
class RunOutcome:
    source_code: str
    status: str
    error: str | None = None
    ingest: IngestStats | None = None
    evaluation: EvaluationStats | None = None
    warnings: list[str] = field(default_factory=list)


def load_source(session: Session, source_id: int) -> SourceSpec | None:
    row = session.execute(
        text(
            "SELECT id, code, vendor, connector, config, value_maps, stale_after_s, interval_s "
            "FROM omc_sources WHERE id = :id"
        ),
        {"id": source_id},
    ).one_or_none()
    if row is None:
        return None
    return SourceSpec(
        id=row.id,
        code=row.code,
        vendor=row.vendor,
        connector=row.connector,
        config=row.config or {},
        value_maps=row.value_maps or {},
        stale_after_s=row.stale_after_s,
        interval_s=row.interval_s,
    )


def ensure_demo_source(session: Session) -> int:
    """Crée (si besoin) la source de démonstration fictive et renvoie son identifiant."""
    session.execute(
        text(
            """
            INSERT INTO omc_sources (code, name, vendor, connector, config, value_maps, enabled)
            VALUES (:code, 'Source de démonstration (données fictives)', 'DEMO', 'demo',
                    CAST(:config AS jsonb), CAST(:maps AS jsonb), true)
            ON CONFLICT (code) DO NOTHING
            """
        ),
        {"code": DEMO_CODE, "config": json.dumps({"sites": 40, "seed": 42}), "maps": json.dumps(DEMO_VALUE_MAPS)},
    )
    session.commit()
    return session.scalar(text("SELECT id FROM omc_sources WHERE code = :c"), {"c": DEMO_CODE})


def _sites_of_source(session: Session, source_id: int) -> list[int]:
    return list(session.scalars(text("SELECT DISTINCT site_id FROM site_elements WHERE source_id = :s"), {"s": source_id}))


def run_source(session: Session, source_id: int, now: datetime | None = None) -> RunOutcome:
    now = now or datetime.now(UTC)
    spec = load_source(session, source_id)
    if spec is None:
        raise LookupError(f"Source {source_id} introuvable")

    run_id = session.scalar(
        text("INSERT INTO collection_runs (source_id, started_at, status) VALUES (:s, :now, 'RUNNING') RETURNING id"),
        {"s": spec.id, "now": now},
    )
    session.commit()

    try:
        connector = REGISTRY.get(spec.connector)
        if connector is None:
            raise ConnectorNotConfigured(f"Connecteur « {spec.connector} » non disponible")
        result = connector.collect(spec, now)
        stats = ingest(session, spec, result, now)
        session.execute(
            text(
                "UPDATE omc_sources SET last_status = 'OK', last_run_at = :now, last_success_at = :now, "
                "last_error = NULL, updated_at = now() WHERE id = :id"
            ),
            {"now": now, "id": spec.id},
        )
        session.execute(
            text(
                "UPDATE collection_runs SET status = 'OK', finished_at = :now, elements_count = :e, "
                "alarms_count = :a, unmapped_count = :u WHERE id = :id"
            ),
            {"now": now, "e": stats.elements, "a": stats.alarms, "u": stats.unmapped, "id": run_id},
        )
        # Sites du référentiel qu'aucun OMC ne remonte : ils passent en NON SUPERVISÉ.
        stats.site_ids |= set(
            session.scalars(
                text("SELECT id FROM sites WHERE in_reference AND NOT is_supervised AND display_status <> 'UNSUPERVISED'")
            )
        )
        evaluation = evaluate_sites(session, stats.site_ids, now)
        session.commit()
        return RunOutcome(spec.code, "OK", ingest=stats, evaluation=evaluation, warnings=stats.warnings)
    except Exception as exc:  # noqa: BLE001 - toute erreur de collecte est journalisée
        session.rollback()
        message = str(exc)[:500] or exc.__class__.__name__
        if not isinstance(exc, ConnectorError):
            log.exception("Erreur inattendue pendant la collecte de %s", spec.code)
        session.execute(
            text(
                "UPDATE omc_sources SET last_status = 'FAILED', last_run_at = :now, last_error = :err, "
                "updated_at = now() WHERE id = :id"
            ),
            {"now": now, "err": message, "id": spec.id},
        )
        session.execute(
            text("UPDATE collection_runs SET status = 'FAILED', finished_at = :now, error = :err WHERE id = :id"),
            {"now": now, "err": message, "id": run_id},
        )
        # Les équipements ne sont pas modifiés : le moteur les passe à INCONNU, pas à DOWN.
        evaluation = evaluate_sites(session, _sites_of_source(session, spec.id), now)
        session.commit()
        return RunOutcome(spec.code, "FAILED", error=message, evaluation=evaluation)
