"""Gestion manuelle du référentiel et traitement des sites inconnus (données FICTIVES)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.services.ingest import ingest
from tests.test_reference import SITES, _map, _omc, _upload, kmz

NEW = {"code": "91001", "name": "TEST NOUVEAU SITE", "latitude": 36.70, "longitude": 3.10,
       "dr": "DR Alger", "lifecycle": "en_air", "technologies": ["2G", "4G"]}


def _ids(client, h, **params):
    r = client.get("/api/site-reference/sites", headers=h, params=params)
    assert r.status_code == 200, r.text
    return {i["external_id"]: i for i in r.json()["items"]}


def test_crud_sites(client, login, db):
    h = login("admin")
    _upload(client, h, kmz(SITES), path="apply")
    assert client.post("/api/site-reference/sites", headers=login("lecteur"), json=NEW).status_code == 403

    r = client.post("/api/site-reference/sites", headers=h, json=NEW)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert client.post("/api/site-reference/sites", headers=h, json=NEW).status_code == 409       # doublon
    bad = dict(NEW, code="91002", latitude=48.8, longitude=2.3)
    assert client.post("/api/site-reference/sites", headers=h, json=bad).status_code == 422       # hors Algérie
    assert client.post("/api/site-reference/sites", headers=h, json=dict(NEW, code="9 1")).status_code == 422

    s = _ids(client, h, q="91001")["91001"]
    assert s["wilaya_code"] == 16 and s["ref_status"] == "IN_SERVICE" and s["ref_source"] == "MANUAL"
    assert s["ref_updated_by"] == "admin" and s["status"] == "UNSUPERVISED"
    assert "91001" in _map(client, h)

    upd = dict(NEW, name="TEST RENOMMÉ", lifecycle="planning")
    upd.pop("code")
    r = client.put(f"/api/site-reference/sites/{sid}", headers=h, json=upd)
    assert r.status_code == 200 and set(r.json()["changes"]) == {"name", "lifecycle"}
    s = _ids(client, h, source="MANUAL")["91001"]
    assert s["name"] == "TEST RENOMMÉ" and s["ref_status"] == "PLANNED"
    assert set(_ids(client, h, ref="PLANNED")) == {"90003", "91001"}

    # Un réimport du fichier signale les sites saisis à la main qu'il retirerait
    p = _upload(client, h, kmz(SITES), mode="sync").json()
    assert any("manuellement" in w for w in p["warnings"])

    # Retrait puis suppression définitive
    r = client.post("/api/site-reference/sites/delete", headers=h, json={"ids": [sid], "mode": "remove"})
    assert r.json()["done"] == ["91001"]
    assert "91001" not in _ids(client, h)
    r = client.post("/api/site-reference/sites/delete", headers=h, json={"ids": [sid], "mode": "purge"})
    assert r.json()["done"] == ["91001"]
    db.expire_all()
    assert db.execute(text("SELECT count(*) FROM sites WHERE external_id = '91001'")).scalar() == 0
    audit = [r[0] for r in db.execute(text("SELECT action FROM audit_log ORDER BY id"))]
    assert {"REFERENCE_SITE_CREATED", "REFERENCE_SITE_UPDATED", "REFERENCE_SITE_REMOVED",
            "REFERENCE_SITE_PURGED"} <= set(audit)
    assert client.get("/api/site-reference/sites/export?format=csv", headers=h).text.count("\n") == 7
    opts = client.get("/api/site-reference/options", headers=h).json()
    assert "en_air" in [o["value"] for o in opts["lifecycles"]] and "DR Oran" in opts["drs"]


def test_unknown_sites_link_add_ack(client, login, db, make_source):
    h = login("admin")
    src = make_source()
    _upload(client, h, kmz(SITES), path="apply")
    now = datetime.now(timezone.utc)
    ingest(db, src, _omc(["90001", "9000X", "77777", "88888"], now, names={"9000X": "OMC TYPO"}), now=now)
    from app.reference.anomalies import reconcile_anomalies
    reconcile_anomalies(db)
    db.commit()

    u = client.get("/api/site-reference/unknown-sites", headers=h).json()
    items = {i["external_id"]: i for i in u["items"]}
    assert set(items) == {"9000X", "77777", "88888"} and u["counts"]["open"] == 3
    assert items["9000X"]["suggestion"] and items["9000X"]["sources"] == "TEST-HUAWEI"
    assert items["9000X"]["elements"] == 1

    # Purge refusée : site encore remonté par un OMC
    r = client.post("/api/site-reference/sites/delete", headers=h,
                    json={"ids": [items["77777"]["site_id"]], "mode": "purge"})
    assert r.json()["done"] == [] and r.json()["skipped"]

    # 1. Rattachement à un site du référentiel (faute de frappe dans l'OMC)
    r = client.post(f"/api/site-reference/unknown-sites/{items['9000X']['site_id']}/link", headers=h,
                    json={"target_code": "90002", "note": "faute de frappe OMC"})
    assert r.status_code == 200, r.text
    assert r.json()["elements_moved"] == 1
    assert client.post(f"/api/site-reference/unknown-sites/{items['77777']['site_id']}/link", headers=h,
                       json={"target_code": "NOPE"}).status_code == 422
    s = _ids(client, h, q="9000X")
    assert list(s) == ["90002"] and s["90002"]["aliases"] == ["9000X"] and s["90002"]["status"] == "UP"

    # La collecte suivante applique la correspondance : aucun site inconnu recréé
    later = now + timedelta(minutes=5)
    ingest(db, src, _omc(["90001", "9000X", "77777", "88888"], later), now=later)
    reconcile_anomalies(db)
    db.commit()
    db.expire_all()
    assert db.execute(text("SELECT count(*) FROM sites WHERE external_id = '9000X'")).scalar() == 0

    # 2. Ajout au référentiel d'un site inconnu (conserve équipements et historique)
    body = dict(NEW, code="77777", name="TEST AJOUTÉ DEPUIS OMC")
    r = client.post("/api/site-reference/sites", headers=h, json=body)
    assert r.status_code == 201 and r.json()["adopted_from_omc"]
    s = _ids(client, h, q="77777")["77777"]
    assert s["is_supervised"] and s["status"] == "UP"

    # 3. Ignorer (prise en compte) en lot
    u = client.get("/api/site-reference/unknown-sites", headers=h).json()
    assert [i["external_id"] for i in u["items"]] == ["88888"]
    assert client.post("/api/site-reference/unknown-sites/ack", headers=login("lecteur"),
                       json={"anomaly_ids": [u["items"][0]["anomaly_id"]]}).status_code == 403
    r = client.post("/api/site-reference/unknown-sites/ack", headers=login("superviseur"),
                    json={"anomaly_ids": [u["items"][0]["anomaly_id"]], "note": "site de test constructeur"})
    assert r.json()["acknowledged"] == 1
    u = client.get("/api/site-reference/unknown-sites", headers=h, params={"state": "OPEN"}).json()
    assert u["total"] == 0
    assert client.get("/api/site-reference/unknown-sites/export?format=csv", headers=h).status_code == 200

    # Correspondances : liste et suppression
    a = client.get("/api/site-reference/aliases", headers=h).json()["items"]
    assert a[0]["omc_code"] == "9000X" and a[0]["site_external_id"] == "90002"
    assert client.delete("/api/site-reference/aliases/9000X", headers=h).status_code == 200
    assert client.get("/api/site-reference/aliases", headers=h).json()["items"] == []
