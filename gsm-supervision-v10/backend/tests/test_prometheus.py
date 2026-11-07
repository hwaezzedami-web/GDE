"""Connecteur Prometheus : réponses simulées (API HTTP Prometheus / Alertmanager) et, si
PROMETHEUS_TEST_URL est défini, test d'intégration contre un vrai Prometheus alimenté
par l'exporteur de démonstration (tools/demo_exporter)."""
import json
import os
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import text

from app.collector.connectors.base import ConnectorError, ConnectorNotConfigured, SourceSpec
from app.collector.connectors.prometheus import PrometheusConnector
from app.collector.model import CollectResult, NSite
from app.services.ingest import ingest

TS = 1761742800.5      # 2025-10-29 13:00:00.5 UTC


def vec(*series):
    return {"status": "success", "data": {"resultType": "vector", "result": [
        {"metric": m, "value": [TS, v]} for m, v in series]}}


INFO = vec(
    ({"__name__": "gsm_ne_info", "site_id": "S1", "site_name": "Site 1", "ne_id": "S1-2G", "ne_type": "BTS",
      "technology": "2G", "latitude": "36.75", "longitude": "3.05", "wilaya_code": "16", "omc": "OMC-A",
      "vendor": "huawei"}, "1"),
    ({"__name__": "gsm_ne_info", "site_id": "S1", "site_name": "Site 1", "ne_id": "S1-4G", "ne_type": "ENODEB",
      "technology": "LTE", "latitude": "36.75", "longitude": "3.05", "wilaya_code": "16", "vendor": "huawei"}, "1"),
)
STATUS = vec(
    ({"site_id": "S1", "ne_id": "S1-2G", "technology": "2G", "vendor": "huawei"}, "1"),
    ({"site_id": "S1", "ne_id": "S1-4G", "technology": "4G", "vendor": "huawei"}, "0"),
    ({"site_id": "S2", "ne_id": "S2-3G", "technology": "3G", "vendor": "huawei"}, "1"),
    ({"site_id": "S2", "ne_id": "S2-4G", "technology": "4G", "vendor": "huawei"}, "NaN"),
)
UP_OK = vec(({"job": "gsm-omc-huawei", "instance": "exp:9800", "vendor": "huawei"}, "1"))
AM = [
    {"labels": {"alertname": "GsmAlarmeOmc", "site_id": "S1", "ne_id": "S1-4G", "severity": "critical",
                "vendor": "huawei"},
     "annotations": {"summary": "C-01 Perte de liaison"}, "fingerprint": "abc123",
     "startsAt": "2026-10-29T12:00:00.123456789Z", "status": {"state": "active"}},
    {"labels": {"alertname": "Silenced", "site_id": "S1"}, "annotations": {}, "fingerprint": "zzz",
     "startsAt": "2026-10-29T12:00:00Z", "status": {"state": "suppressed"}},
]


def make(responses: dict, config: dict | None = None, seen: list | None = None):
    """responses : {requête PromQL ou chemin : (code HTTP, corps JSON)}."""
    def handler(req: httpx.Request):
        q = parse_qs(urlparse(str(req.url)).query)
        if seen is not None:
            seen.append((req.url.path, q, dict(req.headers)))
        key = q.get("query", [req.url.path])[0]
        for k, (code, body) in responses.items():
            if k == key or (k.startswith("~") and k[1:] in key):
                return httpx.Response(code, json=body)
        return httpx.Response(200, json=vec())
    cfg = {"url": "http://prom.test:9090", "alarms": {"source": None}} | (config or {})
    return PrometheusConnector(SourceSpec(1, "PROM-H", "HUAWEI", "prometheus", cfg),
                               transport=httpx.MockTransport(handler))


BASE = {"~up{": (200, UP_OK), "~gsm_ne_info": (200, INFO), "~gsm_ne_oper_status": (200, STATUS)}


def test_contract_mapping_and_vendor_filter():
    seen = []
    res = make(BASE, seen=seen).collect()
    queries = [q["query"][0] for _, q, _ in seen]
    assert all('vendor="huawei"' in q for q in queries)
    els = {e.external_id: e for e in res.elements}
    assert els["S1-2G"].oper_status == "UP" and els["S1-4G"].oper_status == "DOWN"
    assert els["S1-4G"].technology == "4G" and els["S1-4G"].element_type == "ENODEB"
    assert els["S2-4G"].oper_status == "UNKNOWN"          # NaN : jamais DOWN
    assert els["S1-2G"].observed_at.isoformat().startswith("2025-10-29T13:00:00.5")
    assert els["S1-2G"].extra == {"omc": "OMC-A"}
    sites = {s.external_id: s for s in res.sites}
    assert sites["S1"].latitude == 36.75 and sites["S1"].name == "Site 1" and sites["S1"].wilaya_code == 16
    assert sites["S2"].name is None                        # créé sans écraser un référentiel existant
    assert res.inventory_complete is False and res.alarms_complete is False
    assert any("non reconnue" in w for w in res.warnings)


def test_status_from_label_and_custom_queries():
    cfg = {"health_query": None, "info": {"query": None},
           "status": {"query": "omc_ne_state", "from": "label", "label": "state"},
           "labels": {"element_id": "ne", "site_id": None, "technology": "rat"},
           "derive": {"site_id_regex": r"^(?P<site>[A-Z]+\d+)_"},
           "value_maps": {"status": {"connected": "UP", "disconnected": "DOWN"}}}
    body = vec(({"ne": "ALG01_L", "rat": "LTE", "state": "disconnected"}, "1"),
               ({"ne": "ALG01_G", "rat": "GSM", "state": "connected"}, "1"))
    res = make({"omc_ne_state": (200, body)}, cfg).collect()
    assert {(e.site_external_id, e.technology, e.oper_status) for e in res.elements} == {
        ("ALG01", "4G", "DOWN"), ("ALG01", "2G", "UP")}


def test_exporter_down_is_a_collection_failure_not_an_outage():
    down = vec(({"job": "gsm-omc-huawei", "instance": "exp:9800"}, "0"))
    with pytest.raises(ConnectorError, match="pas une panne radio") as e:
        make(BASE | {"~up{": (200, down)}).collect()
    assert e.value.transient
    with pytest.raises(ConnectorError, match="aucune cible"):
        make(BASE | {"~up{": (200, vec())}).collect()
    partial = vec(({"instance": "a"}, "1"), ({"instance": "b"}, "0"))
    res = make(BASE | {"~up{": (200, partial)}).collect()
    assert res.details["targets"] == {"total": 2, "down": 1} and any("up == 0" in w for w in res.warnings)
    with pytest.raises(ConnectorError, match="0 série"):
        make(BASE | {"~gsm_ne_oper_status": (200, vec())}).collect()


def test_prometheus_errors():
    bad = {"status": "error", "errorType": "bad_data", "error": "parse error"}
    with pytest.raises(ConnectorError) as e:
        make(BASE | {"~gsm_ne_oper_status": (400, bad)}).collect()
    assert not e.value.transient and "parse error" in str(e.value)
    busy = {"status": "error", "errorType": "unavailable", "error": "overloaded"}
    with pytest.raises(ConnectorError) as e:
        make(BASE | {"~gsm_ne_oper_status": (503, busy)}).collect()
    assert e.value.transient
    with pytest.raises(ConnectorError) as e:
        make(BASE | {"~up{": (401, {"x": 1})}).collect()
    assert not e.value.transient and "Accès refusé" in str(e.value)
    matrix = {"status": "success", "data": {"resultType": "matrix", "result": []}}
    with pytest.raises(ConnectorError, match="vecteur instantané"):
        make(BASE | {"~gsm_ne_oper_status": (200, matrix)}).collect()
    with pytest.raises(ConnectorNotConfigured):
        make(BASE, {"url": "prometheus:9090"}).collect()


def test_unreachable_prometheus_is_transient():
    c = PrometheusConnector(SourceSpec(1, "PROM-H", "HUAWEI", "prometheus",
                                       {"url": "http://127.0.0.1:9", "timeout_s": 2}))
    with pytest.raises(ConnectorError) as e:
        c.collect()
    assert e.value.transient and "injoignable" in str(e.value)


def test_alertmanager_alarms_and_auth(monkeypatch):
    monkeypatch.setenv("OMC_PROM_H_USERNAME", "lecture")
    monkeypatch.setenv("OMC_PROM_H_PASSWORD", "secret")
    seen = []
    res = make(BASE | {"/api/v2/alerts": (200, AM)},
               {"alarms": {"source": "alertmanager", "url": "http://am.test:9093"}}, seen=seen).collect()
    assert len(res.alarms) == 1 and res.alarms_complete
    a = res.alarms[0]
    assert a.external_alarm_id == "abc123"                 # pas de label alarm_id -> empreinte
    assert (a.alarm_code, a.severity, a.description) == ("GsmAlarmeOmc", "CRITICAL", "C-01 Perte de liaison")
    assert a.element_external_id == "S1-4G" and a.raised_at.microsecond == 123456
    am = [x for x in seen if x[0] == "/api/v2/alerts"][0]
    assert am[1]["filter"] == ['vendor="huawei"'] and am[1]["silenced"] == ["false"]
    assert am[2]["authorization"].startswith("Basic ")


def test_promql_alarms():
    alarms = vec(({"alarm_id": "A-9", "site_id": "S1", "ne_id": "S1-4G", "code": "C-7", "severity": "major",
                   "description": "Défaut alimentation"}, "1761742000"))
    cfg = {"alarms": {"source": "promql", "labels": {"code": "code", "description": "description"}}}
    res = make(BASE | {"~gsm_ne_active_alarm": (200, alarms)}, cfg).collect()
    a = res.alarms[0]
    assert (a.external_alarm_id, a.alarm_code, a.severity) == ("A-9", "C-7", "MAJOR")
    assert a.raised_at.year == 2025


def test_ingest_keeps_reference_names_and_coordinates(db, make_source):
    """Un référentiel (import) puis Prometheus sans nom ni coordonnées : rien n'est écrasé."""
    ref = make_source(code="REF", vendor="HUAWEI", connector_type="manual_csv", stale_after_s=None)
    ingest(db, ref, CollectResult(sites=[NSite("S2", name="Site deux", latitude=35.7, longitude=-0.6)]))
    prom = make_source(code="PROM-H", vendor="HUAWEI", connector_type="prometheus")
    res = make({"~gsm_ne_oper_status": (200, STATUS)}, {"health_query": None, "info": {"query": None}}).collect()
    ingest(db, prom, res, now=datetime.fromtimestamp(TS + 60, timezone.utc))   # données fraîches
    db.commit()
    row = db.execute(text("SELECT name, latitude, wilaya_code, status FROM sites WHERE external_id = 'S2'")).one()
    assert row[0] == "Site deux" and row[1] == 35.7 and row[2] == 31 and row[3] == "UP"
    assert db.execute(text("SELECT name FROM sites WHERE external_id = 'S1'")).scalar() == "S1"


@pytest.mark.skipif(not os.environ.get("PROMETHEUS_TEST_URL"), reason="PROMETHEUS_TEST_URL non défini")
def test_integration_real_prometheus(db, make_source):
    """Chaîne réelle : exporteur de démonstration -> Prometheus (-> Alertmanager) -> collecte -> base."""
    from app.collector.runner import run_source

    cfg = {"url": os.environ["PROMETHEUS_TEST_URL"]}
    if os.environ.get("ALERTMANAGER_TEST_URL"):
        cfg["alarms"] = {"source": "alertmanager", "url": os.environ["ALERTMANAGER_TEST_URL"]}
    src = make_source(code="PROM-ZTE", vendor="ZTE", connector_type="prometheus", config=cfg, stale_after_s=900)
    assert run_source(src.id, sleep=lambda s: None) == "SUCCESS"
    db.expire_all()
    n_sites, n_geo, n_els = db.execute(text("""SELECT count(*), count(geom),
        (SELECT count(*) FROM site_elements WHERE is_active) FROM sites""")).one()
    assert n_sites > 100 and n_geo == n_sites and n_els > n_sites
    assert db.execute(text("SELECT count(DISTINCT status) FROM sites")).scalar() >= 2
    assert db.execute(text("SELECT count(*) FROM sites WHERE wilaya_code IS NULL")).scalar() == 0
    # Rejouer : aucun doublon
    assert run_source(src.id, sleep=lambda s: None) == "SUCCESS"
    assert db.execute(text("SELECT count(*) FROM sites")).scalar() == n_sites
    print(json.dumps({"sites": n_sites, "elements": n_els}))
