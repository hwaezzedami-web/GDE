"""Tests de l'API : authentification, rôles, cohérence carte/tableau de bord, exports, administration."""
import io
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
CSV = """site_code;site_name;wilaya_code;commune;latitude;longitude;vendor;technologies;status;omc_source
TST-A;Site A;16;Alger Centre;36.75;3.05;HUAWEI;2G|4G;UP;CSV-HUAWEI
TST-B;Site B;16;Bab Ezzouar;36.72;3.18;HUAWEI;2G|3G|4G;DOWN;CSV-HUAWEI
TST-C;Site C;31;Oran;35.69;-0.63;ERICSSON;2G|4G;DEGRADED;CSV-ERICSSON
TST-D;Site D;25;Constantine;36.36;6.61;ZTE;2G;UNKNOWN;CSV-ZTE
TST-E;Site E;25;Constantine;36.37;6.62;ZTE;2G|4G|5G;UP;CSV-ZTE
BAD;Mauvais;16;;99;3;HUAWEI;2G;UP;CSV-HUAWEI
"""


def load(client, h):
    r = client.post("/api/admin/import/sites-csv", headers=h,
                    files={"file": ("sites.csv", CSV.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


def test_auth_required_and_health(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/sites").status_code == 401
    assert client.get("/api/sites", headers={"Authorization": "Bearer abc"}).status_code == 401


def test_login_lockout_and_audit(client, users, db):
    for _ in range(3):
        assert client.post("/api/auth/login", json={"username": "lecteur", "password": "faux"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "lecteur", "password": users})
    assert r.status_code == 423                      # verrouillé après 3 échecs (LOGIN_MAX_FAILURES)
    actions = [a for (a,) in db.execute(text("SELECT action FROM audit_log ORDER BY id"))]
    assert actions.count("LOGIN_FAILED") == 3 and "LOGIN_REFUSED_LOCKED" in actions


def test_logout_revokes_token(client, login):
    h = login("lecteur")
    assert client.get("/api/auth/me", headers=h).status_code == 200
    client.post("/api/auth/logout", headers=h)
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_roles(client, login):
    viewer, sup = login("lecteur"), login("superviseur")
    assert client.get("/api/admin/users", headers=viewer).status_code == 403
    assert client.get("/api/export/sites", headers=viewer).status_code == 403
    assert client.get("/api/admin/users", headers=sup).status_code == 403
    assert client.post("/api/admin/import/sites-csv", headers=sup,
                       files={"file": ("x.csv", b"a", "text/csv")}).status_code == 403


def test_csv_import_and_map_dashboard_consistency(client, login):
    h = login()
    rep = load(client, h)
    assert rep["accepted"] == 5 and len(rep["rejected"]) == 1
    m = client.get("/api/sites/map", headers=h).json()
    assert len(m["rows"]) == 5
    s = client.get("/api/dashboard/summary", headers=h).json()
    t = s["totals"]
    assert (t["total"], t["up"], t["down"], t["degraded"], t["unknown"]) == (5, 2, 1, 1, 1)
    # Cohérence carte / compteurs avec filtres combinés
    for q in ["status=DOWN", "vendor=ZTE", "wilaya=25&tech=5G", "q=site%20b", "vendor=HUAWEI,ZTE&status=UP",
              "region=Est", "bbox=2.9,36.6,3.2,36.8"]:
        mp = client.get(f"/api/sites/map?{q}", headers=h).json()
        sm = client.get(f"/api/dashboard/summary?{q}", headers=h).json()
        ls = client.get(f"/api/sites?{q}", headers=h).json()
        assert len(mp["rows"]) == sm["totals"]["total"] == ls["total"], q
    assert client.get("/api/sites/map?status=DOWN", headers=h).json()["rows"][0][7] == "TST-B"
    by_tech = {r["key"]: r["total"] for r in s["by_technology"]}
    assert by_tech == {"2G": 5, "3G": 1, "4G": 4, "5G": 1}
    assert client.get("/api/sites?status=PANNE", headers=h).status_code == 422


def test_site_detail_and_history(client, login):
    h = login()
    load(client, h)
    sid = client.get("/api/sites?q=TST-B", headers=h).json()["items"][0]["id"]
    d = client.get(f"/api/sites/{sid}", headers=h).json()
    assert d["site"]["status"] == "DOWN" and d["site"]["wilaya_name"] == "Alger"
    assert {e["technology"] for e in d["elements"]} == {"2G", "3G", "4G"}
    assert d["history"]["items"][0]["new_status"] == "DOWN"
    assert client.get("/api/sites/999999", headers=h).status_code == 404
    out = client.get("/api/dashboard/outages?hours=1", headers=h).json()
    assert [o["external_id"] for o in out["items"]] == ["TST-B"]
    av = client.get("/api/dashboard/availability?group=vendor&days=1", headers=h).json()
    assert {i["key"] for i in av["items"]} == {"HUAWEI", "ERICSSON", "ZTE"}


def test_exports(client, login, db):
    h = login("superviseur")
    load(client, login())
    r = client.get("/api/export/sites?format=xlsx&status=DOWN,DEGRADED", headers=h)
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.content)).active
    rows = list(ws.values)
    assert rows[0][0] == "Code site" and len(rows) == 3
    r = client.get("/api/export/sites?format=csv&vendor=ZTE", headers=h)
    body = r.content.decode("utf-8-sig").splitlines()
    assert len(body) == 3 and body[0].startswith("Code site;")
    assert client.get("/api/export/outages?format=csv", headers=h).status_code == 200
    assert client.get("/api/export/alarms?format=xlsx&state=ALL", headers=h).status_code == 200
    assert db.execute(text("SELECT count(*) FROM audit_log WHERE action LIKE 'EXPORT_%'")).scalar() == 4


def test_settings_validation_and_alarm_rules(client, login):
    h = login()
    load(client, h)
    assert client.put("/api/admin/settings/status_rules", headers=h,
                      json={"down_confirm_s": -5}).status_code == 422
    assert client.put("/api/admin/settings/status_rules", headers=h,
                      json={"inconnu": 1}).status_code == 422
    r = client.put("/api/admin/settings/status_rules", headers=h, json={"down_confirm_s": 120})
    assert r.status_code == 200 and r.json()["down_confirm_s"] == 120
    # Règle d'alarme : sans effet tant qu'elle n'est pas validée
    r = client.post("/api/admin/alarm-rules", headers=h,
                    json={"vendor": "ZTE", "text_pattern": "(", "effect": "DOWN"})
    assert r.status_code == 422
    r = client.post("/api/admin/alarm-rules", headers=h,
                    json={"vendor": "ZTE", "alarm_code": "X1", "effect": "DOWN", "scope": "SITE"})
    assert r.status_code == 201 and r.json()["validated_at"] is None
    v = client.post(f"/api/admin/alarm-rules/{r.json()['id']}/validate", headers=h).json()
    assert v["validated_by"] == "admin"


def test_omc_source_config_rejects_secrets(client, login):
    h = login()
    base = {"code": "ERIC-OMC-1", "name": "OMC Ericsson 1", "vendor": "ERICSSON", "connector_type": "ericsson"}
    r = client.post("/api/admin/omc-sources", headers=h, json=base | {"config": {"sftp": {"password": "x"}}})
    assert r.status_code == 422
    r = client.post("/api/admin/omc-sources", headers=h, json=base | {"config": {"interface": "file_export"}})
    assert r.status_code == 201 and r.json()["integration_validated"] is False
    sid = r.json()["id"]
    assert client.post(f"/api/admin/omc-sources/{sid}/sync", headers=h).status_code == 400  # désactivée


def test_user_management_and_forced_password_change(client, login):
    h = login()
    r = client.post("/api/admin/users", headers=h, json={"username": "nouveau", "role": "VIEWER", "password": "court"})
    assert r.status_code == 400
    r = client.post("/api/admin/users", headers=h,
                    json={"username": "nouveau", "role": "VIEWER", "password": "Nouveau-Mot-2026"})
    assert r.status_code == 201
    t = client.post("/api/auth/login", json={"username": "nouveau", "password": "Nouveau-Mot-2026"}).json()
    hn = {"Authorization": f"Bearer {t['access_token']}"}
    assert t["user"]["must_change_password"] is True
    assert client.get("/api/sites", headers=hn).status_code == 403
    r = client.post("/api/auth/change-password", headers=hn,
                    json={"current_password": "Nouveau-Mot-2026", "new_password": "Autre-Mot-2026!"})
    assert r.status_code == 200
    hn = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/sites", headers=hn).status_code == 200
    me = client.get("/api/auth/me", headers=h).json()
    r = client.patch(f"/api/admin/users/{me['id']}", headers=h, json={"role": "VIEWER"})
    assert r.status_code == 400


def test_reference_and_alarms(client, login):
    h = login()
    load(client, h)
    ref = client.get("/api/reference", headers=h).json()
    assert len(ref["wilayas"]) == 69 and "Sud" in ref["regions"]
    assert any(c["commune"] == "Bab Ezzouar" for c in client.get("/api/reference/communes?wilaya=16",
                                                                   headers=h).json())
    gj = client.get("/api/reference/wilaya-boundaries", headers=h).json()
    assert len(gj["features"]) == 69 and "OpenStreetMap" in gj["attribution"]
    assert client.get("/api/alarms?state=ALL", headers=h).status_code == 200
