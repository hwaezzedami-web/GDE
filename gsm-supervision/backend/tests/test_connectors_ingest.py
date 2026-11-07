"""Connecteurs, ingestion, rapprochement des codes et journal de collecte (base réelle)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.collector.connectors.base import Connector, ConnectorError, ConnectorNotConfigured, ensure_configured
from app.collector.connectors.demo import DemoConnector
from app.collector.model import CollectResult, NAlarm, NElement, NSite
from app.collector.runner import REGISTRY, ensure_demo_source, run_source

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
VALUE_MAPS = {"status": {"1": "UP", "0": "DOWN", "2": "DEGRADED"}}


class Scripted(Connector):
    """Connecteur de test : renvoie un résultat fixé, ou échoue."""

    name = "scripted"

    def __init__(self) -> None:
        self.result: CollectResult | None = None
        self.error: Exception | None = None

    def collect(self, spec, now):
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def scripted(monkeypatch):
    connector = Scripted()
    monkeypatch.setitem(REGISTRY, "vendor", connector)  # connecteur « vendor » : non livré avant la phase 5
    return connector


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


def _make_source(session: Session, code: str, config: dict | None = None) -> int:
    session.execute(
        text(
            "INSERT INTO omc_sources (code, name, vendor, connector, config, value_maps, enabled) "
            "VALUES (:c, :n, 'OTHER', 'vendor', CAST(:cfg AS jsonb), CAST(:vm AS jsonb), true)"
        ),
        {"c": code, "n": f"Test {code}", "cfg": json.dumps(config or {}), "vm": json.dumps(VALUE_MAPS)},
    )
    session.commit()
    return session.scalar(text("SELECT id FROM omc_sources WHERE code = :c"), {"c": code})


def _site_status(session: Session, external_id: str) -> str | None:
    session.expire_all()
    return session.scalar(text("SELECT display_status FROM sites WHERE external_id = :e"), {"e": external_id})


def _result(observed: datetime, sites=(), elements=(), alarms=(), elements_complete=True, alarms_complete=True):
    return CollectResult(
        observed_at=observed,
        sites=list(sites),
        elements=list(elements),
        alarms=list(alarms),
        elements_complete=elements_complete,
        alarms_complete=alarms_complete,
    )


# --- Connecteurs --------------------------------------------------------------------


def test_placeholder_blocks_collection():
    with pytest.raises(ConnectorNotConfigured, match="A_COMPLETER"):
        ensure_configured({"status": {"query": "A_COMPLETER"}})


def test_demo_connector_is_deterministic():
    from app.collector.connectors.base import SourceSpec

    spec = SourceSpec(1, "D", "DEMO", "demo", {"sites": 12, "seed": 7}, {}, 1800, 300)
    first = DemoConnector().collect(spec, NOW)
    second = DemoConnector().collect(spec, NOW)
    assert [e.ne_id for e in first.elements] == [e.ne_id for e in second.elements]
    assert len(first.sites) == 12


# --- Ingestion et rapprochement des codes ---------------------------------------------


def test_demo_run_creates_supervised_sites(session):
    source_id = ensure_demo_source(session)
    outcome = run_source(session, source_id, now=NOW)
    assert outcome.status == "OK", outcome.error
    assert outcome.ingest.sites_created + outcome.ingest.sites_updated >= 40
    supervised = session.scalar(text("SELECT count(*) FROM sites WHERE is_supervised AND NOT in_reference"))
    assert supervised >= 40
    statuses = set(session.scalars(text("SELECT DISTINCT display_status FROM sites")))
    assert statuses <= {"UP", "DOWN", "DEGRADED", "UNKNOWN", "UNSUPERVISED"}
    assert "UP" in statuses


def test_rerun_is_idempotent(session):
    source_id = ensure_demo_source(session)
    run_source(session, source_id, now=NOW)
    before = session.scalar(text("SELECT count(*) FROM sites"))
    run_source(session, source_id, now=NOW + timedelta(minutes=5))
    assert session.scalar(text("SELECT count(*) FROM sites")) == before


def test_leading_zero_code_resolves_to_unique_site(session, scripted):
    session.execute(text("INSERT INTO sites (external_id, name) VALUES ('7700002', 'Site zéros')"))
    session.commit()
    source_id = _make_source(session, "T-ZEROS")
    scripted.result = _result(
        NOW,
        elements=[NElement(ne_id="NE-Z1", site_id="0007700002", raw_status="1")],
    )
    outcome = run_source(session, source_id, now=NOW)
    assert outcome.status == "OK", outcome.error
    linked = session.scalar(
        text("SELECT s.external_id FROM site_elements e JOIN sites s ON s.id = e.site_id WHERE e.ne_id = 'NE-Z1'")
    )
    assert linked == "7700002"
    assert session.scalar(text("SELECT count(*) FROM sites WHERE external_id = '0007700002'")) == 0


def test_alias_resolves_omc_code(session, scripted):
    session.execute(text("INSERT INTO sites (external_id, name) VALUES ('7700003', 'Site alias')"))
    session.execute(text("INSERT INTO site_code_aliases (omc_code, site_code) VALUES ('ALIAS-9', '7700003')"))
    session.commit()
    source_id = _make_source(session, "T-ALIAS")
    scripted.result = _result(NOW, elements=[NElement(ne_id="NE-A1", site_id="ALIAS-9", raw_status="1")])
    assert run_source(session, source_id, now=NOW).status == "OK"
    assert session.scalar(
        text("SELECT s.external_id FROM site_elements e JOIN sites s ON s.id = e.site_id WHERE e.ne_id = 'NE-A1'")
    ) == "7700003"


def test_unknown_site_is_created_outside_reference(session, scripted):
    source_id = _make_source(session, "T-UNKNOWN")
    scripted.result = _result(
        NOW,
        sites=[NSite(external_id="7700005", name="Nouveau site OMC", lat=36.7, lon=3.0)],
        elements=[NElement(ne_id="NE-U1", site_id="7700005", raw_status="1")],
    )
    run_source(session, source_id, now=NOW)
    row = session.execute(
        text("SELECT in_reference, is_supervised, name FROM sites WHERE external_id = '7700005'")
    ).one()
    assert row.in_reference is False and row.is_supervised is True and row.name == "Nouveau site OMC"


def test_reference_fields_are_not_overwritten_by_omc(session, scripted):
    session.execute(
        text(
            "INSERT INTO sites (external_id, name, in_reference, ref_source, ref_status) "
            "VALUES ('7700004', 'Nom du référentiel', true, 'IMPORT', 'IN_SERVICE')"
        )
    )
    session.commit()
    source_id = _make_source(session, "T-REF")
    scripted.result = _result(
        NOW,
        sites=[NSite(external_id="7700004", name="Nom OMC")],
        elements=[NElement(ne_id="NE-R1", site_id="7700004", raw_status="1")],
    )
    run_source(session, source_id, now=NOW)
    row = session.execute(
        text("SELECT name, extra->>'omc_name' AS omc FROM sites WHERE external_id = '7700004'")
    ).one()
    assert row.name == "Nom du référentiel"
    assert row.omc == "Nom OMC"


def test_reference_site_not_supervised_is_unsupervised(session, scripted):
    session.execute(
        text(
            "INSERT INTO sites (external_id, name, in_reference, ref_source, ref_status) "
            "VALUES ('7700006', 'Site jamais vu', true, 'IMPORT', 'IN_SERVICE')"
        )
    )
    session.commit()
    source_id = _make_source(session, "T-NEVER")
    scripted.result = _result(NOW)
    run_source(session, source_id, now=NOW)
    assert _site_status(session, "7700006") == "UNSUPERVISED"


# --- Perte de collecte ≠ panne radio --------------------------------------------------


def test_omc_outage_is_not_a_radio_outage(session, scripted):
    """Un site DOWN devient INCONNU quand la collecte échoue, jamais DOWN."""
    source_id = _make_source(session, "T-OUTAGE")
    scripted.result = _result(
        NOW,
        sites=[NSite(external_id="7700007", name="Site en panne")],
        elements=[
            NElement(ne_id="NE-O1", site_id="7700007", raw_status="0"),
            NElement(ne_id="NE-O2", site_id="7700007", raw_status="0"),
        ],
    )
    assert run_source(session, source_id, now=NOW).status == "OK"
    assert _site_status(session, "7700007") == "DOWN"

    scripted.result = None
    scripted.error = ConnectorError("Connexion refusée par l'OMC")
    outcome = run_source(session, source_id, now=NOW + timedelta(seconds=60))
    assert outcome.status == "FAILED"
    assert _site_status(session, "7700007") == "UNKNOWN"
    states = set(session.scalars(text(
        "SELECT oper_status FROM site_elements e JOIN sites s ON s.id = e.site_id WHERE s.external_id = '7700007'"
    )))
    assert states == {"UNKNOWN"}


def test_failed_run_is_journaled_and_source_marked(session, scripted):
    source_id = _make_source(session, "T-JOURNAL")
    scripted.error = ConnectorError("Délai dépassé")
    run_source(session, source_id, now=NOW)
    row = session.execute(
        text("SELECT last_status, last_error FROM omc_sources WHERE id = :i"), {"i": source_id}
    ).one()
    assert row.last_status == "FAILED" and "Délai" in row.last_error
    run = session.execute(
        text("SELECT status, error FROM collection_runs WHERE source_id = :i ORDER BY id DESC LIMIT 1"),
        {"i": source_id},
    ).one()
    assert run.status == "FAILED" and "Délai" in run.error


def test_unexpected_error_is_also_contained(session, scripted):
    source_id = _make_source(session, "T-BUG")
    scripted.error = RuntimeError("Erreur interne")
    outcome = run_source(session, source_id, now=NOW)
    assert outcome.status == "FAILED" and outcome.error == "Erreur interne"


# --- Complétude et historique ----------------------------------------------------------


def test_missing_elements_are_deactivated_when_collection_is_complete(session, scripted):
    source_id = _make_source(session, "T-COMPLETE")
    scripted.result = _result(
        NOW,
        sites=[NSite(external_id="7700008")],
        elements=[
            NElement(ne_id="NE-C1", site_id="7700008", raw_status="1"),
            NElement(ne_id="NE-C2", site_id="7700008", raw_status="1"),
        ],
    )
    run_source(session, source_id, now=NOW)
    scripted.result = _result(NOW + timedelta(minutes=5), elements=[NElement(ne_id="NE-C1", site_id="7700008", raw_status="1")])
    run_source(session, source_id, now=NOW + timedelta(minutes=5))
    active = set(session.scalars(text(
        "SELECT ne_id FROM site_elements WHERE source_id = :s AND active"
    ), {"s": source_id}))
    assert active == {"NE-C1"}


def test_alarm_cleared_when_absent_from_complete_snapshot(session, scripted):
    source_id = _make_source(session, "T-ALARM")
    scripted.result = _result(
        NOW,
        sites=[NSite(external_id="7700009")],
        elements=[NElement(ne_id="NE-L1", site_id="7700009", raw_status="1")],
        alarms=[NAlarm(alarm_id="AL-1", site_id="7700009", ne_id="NE-L1", code="X", severity="MAJOR")],
    )
    run_source(session, source_id, now=NOW)
    assert session.scalar(text("SELECT is_active FROM alarms WHERE omc_alarm_id = 'AL-1'")) is True

    scripted.result = _result(NOW + timedelta(minutes=5), elements=[NElement(ne_id="NE-L1", site_id="7700009", raw_status="1")])
    run_source(session, source_id, now=NOW + timedelta(minutes=5))
    row = session.execute(text("SELECT is_active, cleared_at FROM alarms WHERE omc_alarm_id = 'AL-1'")).one()
    assert row.is_active is False and row.cleared_at is not None


def test_transitions_are_historized(session, scripted):
    source_id = _make_source(session, "T-HIST")
    scripted.result = _result(
        NOW,
        sites=[NSite(external_id="7700010")],
        elements=[NElement(ne_id="NE-H1", site_id="7700010", raw_status="1")],
    )
    run_source(session, source_id, now=NOW)
    scripted.result = _result(NOW + timedelta(minutes=1), elements=[NElement(ne_id="NE-H1", site_id="7700010", raw_status="0")])
    run_source(session, source_id, now=NOW + timedelta(minutes=1))
    news = list(session.scalars(text(
        "SELECT h.new_status FROM status_history h JOIN sites s ON s.id = h.site_id "
        "WHERE s.external_id = '7700010' AND h.element_id IS NULL ORDER BY h.id"
    )))
    assert news[-1] == "DOWN"
