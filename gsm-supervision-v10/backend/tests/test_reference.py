"""Référentiel de sites : lecture des fichiers, différentiel, import, rapprochement avec les OMC.

Toutes les données sont FICTIVES (codes 9xxxx, noms « TEST … »), générées dans le test.
"""
from __future__ import annotations

import io
import json
import os
import time
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from openpyxl import Workbook
from sqlalchemy import text

from app.collector.model import CollectResult, NAlarm, NElement, NSite
from app.reference.mapping import GEOMETRY, detect_mapping, normalize, parse_coord, parse_technologies
from app.reference.parsers import ReferenceFileError, read_reference_file
from app.services.ingest import ingest

SITES = [
    # code, nom, lat, lon, wilaya, DR, cycle de vie, technologies
    ("90001", "TEST ALGER PORT", 36.7700, 3.0600, "Alger Centre", "DR Alger", "en_air", "2G/3G/4G"),
    ("90002", "TEST ORAN FRONT", 35.7000, -0.6400, "Oran", "DR Oran", "en_air", "2G 4G"),
    ("90003", "TEST CONSTANTINE", 36.3600, 6.6100, "Constantine", "DR Constantine", "planning", "4G"),
    ("90004", "TEST OUARGLA", 31.9500, 5.3200, "Ouargla", "DR Ouargla", "desinstalle", "2G"),
    ("09005", "TEST BLIDA", 36.4700, 2.8300, "Blida", "DR Blida", "en_air", "3G/4G"),
    ("90006", "TEST SETIF", 36.1900, 5.4100, "Sétif", "DR Sétif", "halte", "2G/3G"),
]


def kml_doc(rows, extra_footer=True) -> bytes:
    marks = []
    for code, name, lat, lon, wil, dr, lc, tech in rows:
        table = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in [
            ("Code site", code), ("Nom du site", name), ("Wilaya", wil), ("Commune", "Commune test"),
            ("Region", dr), ("Etape cycle de vie", lc), ("Technologies radio", tech), ("Zone test", "Z1")])
        footer = "<p>Pied de page libre (ignoré)</p>" if extra_footer else ""
        marks.append(f"""<Placemark><name>{name}</name>
          <description><![CDATA[<table>{table}</table>{footer}]]></description>
          <Point><coordinates>{lon},{lat},0</coordinates></Point></Placemark>""")
    return (f'<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2">'
            f'<Document><Folder>{"".join(marks)}</Folder></Document></kml>').encode()


def kmz(rows) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", kml_doc(rows))
    return buf.getvalue()


def xlsx(header, rows) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["Référentiel de test (titre)"])
    ws.append(header)
    for r in rows:
        ws.append(list(r))
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# --------------------------------------------------------------------------- lecture / normalisation
def test_kmz_parsing_and_mapping():
    t = read_reference_file("sites.kmz", kmz(SITES))
    assert t.format == "kmz" and t.has_geometry and len(t.rows) == 6
    m = detect_mapping(t)
    assert m["code"] == "Code site" and m["name"] == "Nom du site" and m["dr"] == "Region"
    assert m["latitude"] == m["longitude"] == GEOMETRY
    assert m["lifecycle"] == "Etape cycle de vie" and m["technologies"] == "Technologies radio"
    n = normalize(t, m)
    assert not n.invalid
    s = {x.code: x for x in n.sites}
    assert s["09005"].lat == pytest.approx(36.47) and s["90001"].technologies == ["2G", "3G", "4G"]
    assert s["90001"].attributes == {"Zone test": "Z1"}            # colonne non mappée conservée
    assert all("Pied de page" not in json.dumps(x.attributes) for x in n.sites)


def test_kml_with_dtd_is_refused():
    bomb = b'<?xml version="1.0"?><!DOCTYPE kml [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><kml>&b;</kml>'
    with pytest.raises(ReferenceFileError):
        read_reference_file("x.kml", bomb)


def test_xlsx_fixes_and_rejections():
    header = ["Code", "Nom", "Lat", "Long", "Wilaya", "Statut site"]
    content = xlsx(header, [
        (9101, "TEST A", "36°45'09\"N", "3°03'33\"E", "16", "en_air"),     # DMS + code numérique
        ("9102", "TEST B", 3.06, 36.75, "Alger", "en_air"),                # latitude/longitude inversées
        ("9103", "TEST C", 48.85, 2.35, "Alger", "en_air"),                # hors Algérie
        ("9101", "TEST D", 36.7, 3.0, "Alger", "en_air"),                  # doublon
        ("", "TEST E", 36.7, 3.0, "Alger", "en_air"),                      # code vide
    ])
    t = read_reference_file("ref.xlsx", content)
    m = detect_mapping(t)
    assert (m["code"], m["latitude"], m["longitude"], m["lifecycle"]) == ("Code", "Lat", "Long", "Statut site")
    n = normalize(t, m, code_digits=5)
    assert [s.code for s in n.sites] == ["09101", "09102"]
    assert n.sites[0].lat == pytest.approx(36.7525, abs=1e-4) and n.sites[1].lat == 36.75
    assert len(n.fixes) == 1 and len(n.invalid) == 3


def test_csv_semicolon_latin1():
    content = "Code site;Nom du site;Latitude;Longitude;Wilaya\n90011;TEST Béjaïa;36,75;5,06;Béjaïa\n".encode("cp1252")
    t = read_reference_file("ref.csv", content)
    n = normalize(t, detect_mapping(t))
    assert n.sites[0].name == "TEST Béjaïa" and n.sites[0].lon == 5.06


def test_value_helpers():
    assert parse_coord("36,5") == 36.5 and parse_coord("---") is None
    assert parse_coord("0°30'W") == pytest.approx(-0.5)
    assert parse_technologies("GSM/UMTS/LTE") == ["2G", "3G", "4G"] and parse_technologies("???") == []


# --------------------------------------------------------------------------- import (API)
def _upload(client, h, content, name="sites.kmz", path="preview", **form):
    data = {k: (json.dumps(v) if isinstance(v, dict) else str(v)) for k, v in form.items()}
    return client.post(f"/api/site-reference/import/{path}", headers=h,
                       files={"file": (name, content, "application/octet-stream")}, data=data)


def _map(client, h, **params):
    r = client.get("/api/sites/map", headers=h, params=params)
    assert r.status_code == 200, r.text
    f = r.json()["fields"]
    return {row[f.index("external_id")]: dict(zip(f, row)) for row in r.json()["rows"]}


def test_import_preview_apply_and_scope(client, login):
    h = login("admin")
    assert _upload(client, login("lecteur"), kmz(SITES)).status_code == 403
    r = _upload(client, h, kmz(SITES))
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["counts"]["new"] == 6 and p["counts"]["by_status"] == {
        "IN_SERVICE": 3, "PLANNED": 1, "REMOVED": 1, "TEMP_OFF": 1}
    r = _upload(client, h, kmz(SITES), path="apply", expected_sha256=p["sha256"])
    assert r.status_code == 200 and r.json()["status"] == "APPLIED", r.text

    pts = _map(client, h)
    # En projet / démonté et non supervisés : masqués par défaut
    assert set(pts) == {"90001", "90002", "09005", "90006"}
    assert {p["status"] for p in pts.values()} == {"UNSUPERVISED"}
    assert pts["90001"]["dr"] == "DR Alger" and pts["90001"]["ref"] == "IN_SERVICE"
    assert set(_map(client, h, ref="ALL")) == {s[0] for s in SITES}
    assert set(_map(client, h, ref="PLANNED")) == {"90003"}
    assert set(_map(client, h, dr="DR Oran")) == {"90002"}

    d = client.get("/api/dashboard/summary", headers=h).json()
    assert d["totals"]["unsupervised"] == 4 and d["totals"]["unknown"] == 0
    assert d["reference"]["sites"] == 6
    s = client.get("/api/site-reference/summary", headers=h).json()
    assert s["sites"]["reference"] == 6 and s["last_import"]["status"] == "APPLIED"
    # Wilaya : libellé du fichier (« Alger Centre » -> 16)
    det = client.get(f"/api/sites/{pts['90001']['id']}", headers=h).json()
    assert det["site"]["wilaya_code"] == 16 and det["site"]["in_reference"]
    assert det["site"]["extra"]["reference"]["Zone test"] == "Z1"

    # Réimport identique : rien ne change ; fichier modifié : différentiel
    p2 = _upload(client, h, kmz(SITES)).json()
    assert p2["counts"]["unchanged"] == 6 and p2["counts"]["new"] == 0
    moved = [list(x) for x in SITES]
    moved[0][2] += 0.01
    moved[2][6] = "en_air"
    p3 = _upload(client, h, kmz([tuple(x) for x in moved])).json()
    assert p3["counts"]["updated"] == 2
    assert any("déplacé" in c for u in p3["sample_updated"] for c in u["changes"])

    assert client.get("/api/site-reference/template", headers=h).status_code == 200
    assert client.get("/api/site-reference/export?format=csv", headers=h).text.count("\n") == 7
    assert client.get("/api/site-reference/imports", headers=h).json()["items"][0]["origin"] == "UI"


def test_sync_removal_safeguard(client, login):
    h = login("admin")
    _upload(client, h, kmz(SITES), path="apply")
    r = _upload(client, h, kmz(SITES[:2]), path="apply", mode="sync")
    assert r.json()["status"] == "REFUSED"                                # 4/6 retirés > 10 %
    r = _upload(client, h, kmz(SITES[:2]), path="apply", mode="sync", confirm_large_removal="true")
    assert r.json()["status"] == "APPLIED" and r.json()["counts"]["removed_applied"] == 4
    assert set(_map(client, h, ref="ALL")) == {"90001", "90002"}         # non supervisés : retirés


# --------------------------------------------------------------------------- rapprochement OMC
def _omc(codes, now, status="UP", complete=False, names=None):
    res = CollectResult(inventory_complete=complete)
    for c in codes:
        res.sites.append(NSite(external_id=c, name=(names or {}).get(c), latitude=35.0, longitude=1.0))
        res.elements.append(NElement(external_id=f"NE-{c}", site_external_id=c, technology="2G",
                                     oper_status=status, observed_at=now))
    return res


def _anoms(db):
    return {(t, c) for t, c in db.execute(text(
        "SELECT anomaly_type, site_external_id FROM site_anomalies WHERE resolved_at IS NULL"))}


def test_omc_reconciliation(client, login, db, make_source):
    from app.reference.anomalies import reconcile_anomalies

    h = login("admin")
    src = make_source()
    # Site déjà remonté par l'OMC sans zéro de tête AVANT l'import du référentiel
    now = datetime.now(timezone.utc)
    ingest(db, src, _omc(["9005"], now), now=now)
    db.commit()
    _upload(client, h, kmz(SITES), path="apply")
    db.expire_all()
    assert db.execute(text("SELECT count(*) FROM sites WHERE external_id IN ('9005', '09005')")).scalar() == 1
    assert db.execute(text("SELECT is_supervised FROM sites WHERE external_id = '09005'")).scalar()

    res = _omc(["90001", "90004", "90003", "90006", "9005", "77777", "9000X"], now,
               names={"90001": "NOM OMC DIFFERENT"})
    res.alarms.append(NAlarm(external_alarm_id="A1", site_external_id="9005", severity="MAJOR",
                             description="Alarme test"))
    st = ingest(db, src, res, now=now)
    reconcile_anomalies(db)
    db.commit()
    assert any("zéros de tête" in m for m in st.messages)
    assert _anoms(db) == {("UNKNOWN_SITE", "77777"), ("UNKNOWN_SITE", "9000X"),
                          ("REMOVED_BUT_ACTIVE", "90004"), ("PLANNED_BUT_ACTIVE", "90003")}
    sug = db.execute(text("""SELECT details->>'suggestion' FROM site_anomalies
                             WHERE site_external_id = '9000X'""")).scalar()
    assert sug and sug.startswith("9000")
    # Le référentiel fait foi pour le nom et la position
    name, lat, extra = db.execute(text("SELECT name, latitude, extra FROM sites WHERE external_id = '90001'")).one()
    assert name == "TEST ALGER PORT" and lat == pytest.approx(36.77) and extra["omc_name"] == "NOM OMC DIFFERENT"
    assert db.execute(text("""SELECT count(*) FROM alarms a JOIN sites s ON s.id = a.site_id
                              WHERE s.external_id = '09005'""")).scalar() == 1

    # Inventaire complet sans 90001 : le site du référentiel reste visible, « non supervisé »
    later = now + timedelta(minutes=5)
    ingest(db, src, _omc(["90004", "90003", "90006", "9005", "77777", "9000X"], later, complete=True), now=later)
    db.commit()
    pts = _map(client, h)
    assert pts["90001"]["status"] == "UNSUPERVISED" and pts["77777"]["status"] == "UP"
    assert pts["90002"]["status"] == "UNSUPERVISED" and pts["09005"]["status"] == "DEGRADED"

    # Plus remonté depuis plus de 2 jours : supervision perdue
    db.execute(text("UPDATE sites SET last_supervised_at = now() - interval '3 days' WHERE external_id = '90001'"))
    reconcile_anomalies(db)
    db.commit()
    assert ("SUPERVISION_LOST", "90001") in _anoms(db)

    # Le référentiel est corrigé (77777 ajouté, 90004 remis en service) : anomalies résolues
    extra_sites = SITES + [("77777", "TEST NOUVEAU", 36.0, 3.0, "Médéa", "DR Blida", "en_air", "2G")]
    fixed = [tuple("en_air" if (i == 6 and s[0] == "90004") else v for i, v in enumerate(s)) for s in extra_sites]
    _upload(client, h, kmz(fixed), path="apply")
    db.expire_all()
    assert ("UNKNOWN_SITE", "77777") not in _anoms(db) and ("REMOVED_BUT_ACTIVE", "90004") not in _anoms(db)

    # Prise en compte par un superviseur
    a = client.get("/api/site-reference/anomalies", headers=h, params={"type": "UNKNOWN_SITE"}).json()
    assert a["total"] == 1 and a["items"][0]["site_external_id"] == "9000X"
    hs = login("superviseur")
    assert client.post(f"/api/site-reference/anomalies/{a['items'][0]['id']}/ack", headers=hs,
                       json={"note": "Erreur de saisie OMC"}).status_code == 200
    assert client.post(f"/api/site-reference/anomalies/{a['items'][0]['id']}/ack", headers=login("lecteur"),
                       json={}).status_code == 403
    a = client.get("/api/site-reference/anomalies", headers=h, params={"state": "ACKNOWLEDGED"}).json()
    assert a["items"][0]["note"] == "Erreur de saisie OMC"
    assert client.get("/api/site-reference/anomalies/export?format=csv", headers=h).status_code == 200


def test_lifecycle_settings_reclassify(client, login, db):
    h = login("admin")
    _upload(client, h, kmz(SITES), path="apply")
    r = client.put("/api/admin/settings/reference", headers=h, json={"lifecycle_map": {"Halte": "OTHER"}})
    assert r.status_code == 200 and r.json()["lifecycle_map"] == {"halte": "OTHER"}
    db.expire_all()
    assert db.execute(text("SELECT ref_status FROM sites WHERE external_id = '90006'")).scalar() == "OTHER"
    assert db.execute(text("SELECT ref_status FROM sites WHERE external_id = '90001'")).scalar() == "OTHER"
    assert client.put("/api/admin/settings/reference", headers=h,
                      json={"lifecycle_map": {"x": "NIMPORTE"}}).status_code == 422
    assert "reference" in client.get("/api/admin/settings", headers=h).json()


def test_watch_folder(tmp_path, clean_db, db):
    from app.reference.watch import run_watch

    f = tmp_path / "referentiel.kmz"
    f.write_bytes(kmz(SITES))
    old = time.time() - 120
    os.utime(f, (old, old))
    assert run_watch(str(tmp_path)) is None                      # désactivé par défaut
    assert run_watch(str(tmp_path), force=True)["status"] == "APPLIED"
    assert run_watch(str(tmp_path), force=True) is None          # même fichier : ignoré
    db.expire_all()
    assert db.execute(text("SELECT count(*) FROM sites WHERE in_reference")).scalar() == 6
    assert db.execute(text("SELECT origin FROM reference_imports")).scalar() == "WATCH"
    bad = tmp_path / "zz.csv"
    bad.write_text("pas un référentiel\n")
    os.utime(bad, (old + 60, old + 60))
    assert run_watch(str(tmp_path), force=True)["status"] == "FAILED"
