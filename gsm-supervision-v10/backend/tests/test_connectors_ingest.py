"""Tests des connecteurs (fichiers d'export fictifs), de l'ingestion et du service de collecte."""
import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from app.collector.connectors.base import ConnectorError, ConnectorNotConfigured, SourceSpec
from app.collector.connectors.file_export import FileExportConnector
from app.collector.connectors.vendor import EricssonConnector, HuaweiConnector, ZteConnector
from app.collector.model import CollectResult, NAlarm, NElement, NSite
from app.collector.runner import run_source
from app.services.ingest import ingest
from app.services.status_engine import evaluate_sites

FIX = Path(__file__).parent / "fixtures" / "file_export"


def export_config(path: str) -> dict:
    """Configuration d'exemple pour le format FICTIF des fixtures."""
    return {
        "transport": "local",
        "local": {"path": path},
        "files": {"inventory": {"pattern": "inventaire_*.csv"}, "status": {"pattern": "etat_*.csv"},
                  "alarms": {"pattern": "alarmes_*.csv", "required": False}},
        "csv": {"delimiter": ";"},
        "columns": {
            "inventory": {"element_id": "NOM_EQUIPEMENT", "element_name": "LIBELLE", "latitude": "LAT",
                          "longitude": "LON", "element_type": "TYPE_EQ", "wilaya_code": "WILAYA_NO",
                          "commune": "COMMUNE"},
            "status": {"element_id": "NOM_EQUIPEMENT", "status": "ETAT_CNX", "observed_at": "HORODATAGE"},
            "alarms": {"alarm_id": "ID_ALARME", "element_id": "NOM_EQUIPEMENT", "code": "CODE",
                       "description": "TEXTE", "severity": "NIVEAU", "raised_at": "DEBUT"},
        },
        "derive": {"site_id_regex": r"^(?P<site>TST_\d{4})_"},
        "value_maps": {
            "status": {"CONNECTE": "UP", "DECONNECTE": "DOWN"},
            "severity": {"NIV1": "CRITICAL", "NIV2": "MAJOR", "NIV3": "MINOR"},
            "element_type_technology": {"TYPE_A": "2G", "TYPE_B": "3G", "TYPE_C": "4G"},
        },
        "timestamps": {"format": "%Y-%m-%d %H:%M:%S", "timezone": "Africa/Algiers"},
        "extra_columns": ["ZONE_TEST"],
    }


@pytest.fixture
def export_dir(tmp_path):
    d = tmp_path / "exports"
    shutil.copytree(FIX, d)
    for f in d.iterdir():          # exports « tout juste déposés »
        os.utime(f, None)
    return d


def spec(cfg, vendor="HUAWEI", ctype="file_export", code="TEST-HUAWEI"):
    return SourceSpec(id=1, code=code, vendor=vendor, connector_type=ctype, config=cfg)


def test_file_export_mapping(export_dir):
    res = FileExportConnector(spec(export_config(str(export_dir)))).collect()
    sites = {s.external_id: s for s in res.sites}
    assert set(sites) == {"TST_0001", "TST_0002", "TST_0003", "TST_0004"}
    assert sites["TST_0001"].wilaya_code == 16 and sites["TST_0001"].latitude == 36.70
    els = {e.external_id: e for e in res.elements}
    assert els["TST_0001_E"].technology == "4G" and els["TST_0001_E"].oper_status == "UP"
    assert els["TST_0002_B"].oper_status == "DOWN" and els["TST_0002_B"].raw_status == "DECONNECTE"
    # Horodatage local Algérie (UTC+1) converti en UTC
    assert els["TST_0002_B"].observed_at == datetime(2026, 10, 28, 9, 0, tzinfo=timezone.utc)
    assert els["TST_0001_B"].extra == {"ZONE_TEST": "Z1"}
    assert len(res.rejected) == 2      # SANS_CODE (pas de code site) + TYPE_Z (techno inconnue)
    assert {a.severity for a in res.alarms} == {"CRITICAL", "MINOR"}


def test_placeholders_and_vendor_templates_refuse_to_run(export_dir):
    cfg = export_config(str(export_dir))
    cfg["columns"]["status"]["status"] = "A_COMPLETER"
    with pytest.raises(ConnectorNotConfigured):
        FileExportConnector(spec(cfg)).collect()
    for cls, vendor in [(EricssonConnector, "ERICSSON"), (HuaweiConnector, "HUAWEI"), (ZteConnector, "ZTE")]:
        with pytest.raises(ConnectorNotConfigured, match="A_COMPLETER|interface"):
            cls(spec({}, vendor=vendor, ctype=vendor.lower())).collect()


def test_vendor_connector_with_completed_profile(export_dir):
    """Un profil équipementier complété fonctionne via l'interface file_export."""
    cfg = export_config(str(export_dir)) | {"interface": "file_export"}
    with pytest.raises(ConnectorNotConfigured, match="columns.inventory.site_id"):
        HuaweiConnector(spec(cfg)).collect()
    # Les champs sans objet pour ce format sont explicitement neutralisés (null)
    cfg["columns"]["inventory"].update(site_id=None, site_name=None, technology=None)
    res = HuaweiConnector(spec(cfg)).collect()
    assert len(res.elements) == 5 and res.details["profile"] == "huawei"
    with pytest.raises(ConnectorNotConfigured):
        HuaweiConnector(spec(cfg, vendor="ZTE"))


def test_stale_export_file_is_refused(export_dir):
    cfg = export_config(str(export_dir)) | {"max_file_age_s": 3600}
    old = time.time() - 7200
    for f in export_dir.iterdir():
        os.utime(f, (old, old))
    with pytest.raises(ConnectorError, match="trop ancien"):
        FileExportConnector(spec(cfg)).collect()


def test_ingest_idempotent_and_history(db, make_source, export_dir):
    src = make_source(config=export_config(str(export_dir)))
    res = FileExportConnector(spec(src.config)).collect()
    now = datetime(2026, 10, 28, 9, 5, tzinfo=timezone.utc)
    ingest(db, src, res, now=now)
    db.commit()
    counts = lambda: db.execute(text(
        "SELECT (SELECT count(*) FROM sites), (SELECT count(*) FROM site_elements), (SELECT count(*) FROM alarms)"
    )).one()
    assert tuple(counts()) == (4, 5, 2)
    st = dict(db.execute(text("SELECT external_id, status FROM sites")).all())
    assert st == {"TST_0001": "UP", "TST_0002": "DEGRADED", "TST_0003": "DOWN", "TST_0004": "UNKNOWN"}
    # Deuxième passage identique : aucun doublon, aucune nouvelle transition
    hist_before = db.execute(text("SELECT count(*) FROM status_history")).scalar()
    ingest(db, src, FileExportConnector(spec(src.config)).collect(), now=now)
    db.commit()
    assert tuple(counts()) == (4, 5, 2)
    assert db.execute(text("SELECT count(*) FROM status_history")).scalar() == hist_before
    # Rétablissement d'un équipement : transition équipement + site historisées
    res = FileExportConnector(spec(src.config)).collect()
    for e in res.elements:
        if e.external_id == "TST_0003_E":
            e.oper_status, e.observed_at = "UP", now + timedelta(minutes=1)
    ingest(db, src, res, now=now + timedelta(minutes=1))
    db.commit()
    rows = db.execute(text("""SELECT h.entity_type, h.old_status, h.new_status FROM status_history h
                              JOIN sites s ON s.id = h.site_id WHERE s.external_id = 'TST_0003'
                              ORDER BY h.id""")).all()
    assert ("ELEMENT", "DOWN", "UP") in rows and ("SITE", "DOWN", "UP") in rows


def test_inventory_and_alarm_completeness(db, make_source):
    src = make_source(code="T2", vendor="ZTE")
    now = datetime.now(timezone.utc)
    full = CollectResult(
        sites=[NSite("S1", latitude=36.7, longitude=3.0), NSite("S2", latitude=36.7, longitude=3.1)],
        elements=[NElement("S1-2G", "S1", "2G", oper_status="UP", observed_at=now),
                  NElement("S2-2G", "S2", "2G", oper_status="UP", observed_at=now)],
        alarms=[NAlarm("AL1", site_external_id="S1", severity="MAJOR")],
        inventory_complete=True, alarms_complete=True)
    ingest(db, src, full, now=now)
    db.commit()
    assert db.execute(text("SELECT status FROM sites WHERE external_id='S1'")).scalar() == "DEGRADED"
    partial = CollectResult(sites=[full.sites[0]], elements=[full.elements[0]], alarms=[],
                            inventory_complete=True, alarms_complete=True)
    ingest(db, src, partial, now=now)
    db.commit()
    assert db.execute(text("SELECT is_active FROM sites WHERE external_id='S2'")).scalar() is False
    assert db.execute(text("SELECT state FROM alarms WHERE external_alarm_id='AL1'")).scalar() == "CLEARED"
    assert db.execute(text("SELECT status FROM sites WHERE external_id='S1'")).scalar() == "UP"


def test_out_of_country_coordinates_ignored(db, make_source):
    src = make_source(code="T3", vendor="ZTE")
    r = CollectResult(sites=[NSite("S9", latitude=48.85, longitude=2.35)],
                      elements=[NElement("S9-4G", "S9", "4G", oper_status="UP")])
    stats = ingest(db, src, r)
    db.commit()
    assert db.execute(text("SELECT latitude FROM sites WHERE external_id='S9'")).scalar() is None
    assert any("hors Algérie" in m for m in stats.messages)


def test_omc_outage_is_not_a_radio_outage(db, make_source, export_dir):
    """Un OMC injoignable : collecte FAILED, sites inchangés puis UNKNOWN à péremption — jamais DOWN."""
    cfg = export_config(str(export_dir))
    del cfg["columns"]["status"]["observed_at"]     # horodatage = date du fichier (récent)
    src = make_source(config=cfg, stale_after_s=600)
    # PARTIAL : les fixtures contiennent volontairement 2 lignes invalides
    assert run_source(src.id, sleep=lambda s: None) == "PARTIAL"
    up_before = db.execute(text("SELECT count(*) FROM sites WHERE status='UP'")).scalar()
    assert up_before == 1
    shutil.rmtree(export_dir)           # l'OMC ne répond plus
    assert run_source(src.id, sleep=lambda s: None) == "FAILED"
    db.expire_all()
    row = db.execute(text("SELECT last_status, consecutive_failures, last_error FROM omc_sources WHERE id=:i"),
                     {"i": src.id}).one()
    assert row[0] == "FAILED" and row[1] == 1 and "inaccessible" in row[2]
    assert db.execute(text("SELECT count(*) FROM sites WHERE status='UP'")).scalar() == up_before
    run = db.execute(text("SELECT status, attempts FROM collection_runs ORDER BY id DESC LIMIT 1")).one()
    assert run[0] == "FAILED" and run[1] == 2          # 1 essai + 1 nouvelle tentative
    # Une heure plus tard, sans nouvelle collecte : données périmées
    evaluate_sites(db, now=datetime.now(timezone.utc) + timedelta(hours=1))
    db.commit()
    statuses = {r[0] for r in db.execute(text("SELECT DISTINCT status FROM sites"))}
    assert statuses == {"UNKNOWN"}
    assert db.execute(text("SELECT bool_and(is_stale) FROM sites WHERE external_id <> 'TST_0004'")).scalar()


def test_demo_connector_and_seed(db, clean_db):
    from app.services.csv_import import import_sites_csv

    rep = import_sites_csv(db, (Path(os.environ["DATA_DIR"]) / "test" / "sites_fictifs.csv").read_bytes(),
                           default_source="DEMO", connector_type="demo", is_demo=True, poll_interval_s=60)
    db.commit()
    assert rep.accepted == rep.rows and not rep.rejected
    assert set(rep.sources) == {"DEMO-ERICSSON", "DEMO-HUAWEI", "DEMO-ZTE"}
    sid = db.execute(text("SELECT id FROM omc_sources WHERE code='DEMO-ZTE'")).scalar()
    assert run_source(sid, sleep=lambda s: None) == "SUCCESS"
    assert db.execute(text("SELECT bool_and(is_demo) FROM omc_sources")).scalar()


def test_watchdog_evaluation_is_exclusive(db, clean_db):
    """La réévaluation de secours (API) et celle du collecteur ne s'exécutent jamais en parallèle."""
    from app.services.status_engine import EVAL_LOCK, evaluate_all_locked

    assert evaluate_all_locked() is not None
    db.execute(text("SELECT pg_advisory_xact_lock(:a, :b)"), {"a": EVAL_LOCK[0], "b": EVAL_LOCK[1]})
    assert evaluate_all_locked() is None          # verrou détenu ailleurs : ignorée
    db.rollback()
    assert evaluate_all_locked() is not None
