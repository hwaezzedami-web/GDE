"""API phase 1 : authentification, rôles, verrouillage, audit."""

from __future__ import annotations

from sqlalchemy import text

from .conftest import ADMIN_PASSWORD, auth


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["schema_version"] == 4


def test_docs_available(client):
    assert client.get("/api/docs").status_code == 200


def test_requires_authentication(client, initialized_db):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/admin/users", headers=auth("jeton-invalide")).status_code == 401


def test_admin_must_change_password_first(client, admin_token):
    me = client.get("/api/auth/me", headers=auth(admin_token)).json()
    assert me["role"] == "ADMIN" and me["must_change_password"] is False
    assert client.get("/api/admin/users", headers=auth(admin_token)).status_code == 200


def test_pending_password_change_blocks_other_routes(client, admin_token):
    resp = client.post(
        "/api/admin/users",
        json={"username": "nouveau-venu", "password": "Temporaire-123", "role": "VIEWER"},
        headers=auth(admin_token),
    )
    assert resp.status_code == 201
    token = client.post(
        "/api/auth/login", json={"username": "nouveau-venu", "password": "Temporaire-123"}
    ).json()["access_token"]
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 200
    resp = client.get("/api/admin/users", headers=auth(token))
    assert resp.status_code == 403 and "mot de passe" in resp.json()["detail"]


def test_password_policy(client, admin_token):
    resp = client.post(
        "/api/admin/users",
        json={"username": "faible", "password": "court", "role": "VIEWER"},
        headers=auth(admin_token),
    )
    assert resp.status_code == 400
    assert "Mot de passe refusé" in resp.json()["detail"]


def test_roles_are_enforced(client, make_user):
    _, _, viewer = make_user("VIEWER")
    _, _, supervisor = make_user("SUPERVISOR")
    assert client.get("/api/admin/users", headers=auth(viewer)).status_code == 403
    assert client.get("/api/admin/users", headers=auth(supervisor)).status_code == 403
    assert client.get("/api/admin/audit", headers=auth(viewer)).status_code == 403


def test_lockout_after_failures(client, make_user, engine):
    username, password, _ = make_user("VIEWER")
    for _ in range(3):  # LOGIN_MAX_FAILURES=3 dans les tests
        assert client.post("/api/auth/login", json={"username": username, "password": "mauvais"}).status_code == 401
    # même avec le bon mot de passe, le compte reste verrouillé
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 423
    with engine.connect() as conn:
        actions = set(
            conn.execute(text("SELECT action FROM audit_log WHERE username = :u"), {"u": username}).scalars()
        )
    assert {"LOGIN_FAILED", "USER_LOCKED", "LOGIN_REFUSED_LOCKED"} <= actions


def test_admin_can_unlock(client, admin_token, make_user):
    username, password, _ = make_user("VIEWER")
    for _ in range(3):
        client.post("/api/auth/login", json={"username": username, "password": "mauvais"})
    users = client.get("/api/admin/users", headers=auth(admin_token)).json()
    user_id = next(u["id"] for u in users if u["username"] == username)
    assert client.post(f"/api/admin/users/{user_id}/unlock", headers=auth(admin_token)).status_code == 200
    assert client.post("/api/auth/login", json={"username": username, "password": password}).status_code == 200


def test_unknown_user_same_message(client, initialized_db):
    resp = client.post("/api/auth/login", json={"username": "inconnu", "password": "x"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Identifiant ou mot de passe incorrect"


def test_logout_revokes_token(client, make_user):
    username, password, _ = make_user("VIEWER")
    token = client.post("/api/auth/login", json={"username": username, "password": password}).json()["access_token"]
    assert client.post("/api/auth/logout", headers=auth(token)).status_code == 204
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 401


def test_role_change_revokes_token(client, admin_token, make_user):
    username, _, token = make_user("SUPERVISOR")
    users = client.get("/api/admin/users", headers=auth(admin_token)).json()
    user_id = next(u["id"] for u in users if u["username"] == username)
    resp = client.put(f"/api/admin/users/{user_id}", json={"role": "VIEWER"}, headers=auth(admin_token))
    assert resp.status_code == 200 and resp.json()["role"] == "VIEWER"
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 401


def test_cannot_remove_last_admin(client, admin_token):
    users = client.get("/api/admin/users", headers=auth(admin_token)).json()
    admins = [u for u in users if u["role"] == "ADMIN" and u["is_active"]]
    assert len(admins) == 1
    resp = client.put(f"/api/admin/users/{admins[0]['id']}", json={"role": "VIEWER"}, headers=auth(admin_token))
    assert resp.status_code == 409


def test_reset_password_forces_change(client, admin_token, make_user):
    username, _, token = make_user("VIEWER")
    users = client.get("/api/admin/users", headers=auth(admin_token)).json()
    user_id = next(u["id"] for u in users if u["username"] == username)
    resp = client.post(
        f"/api/admin/users/{user_id}/reset-password",
        json={"new_password": "Reinitialise-789"},
        headers=auth(admin_token),
    )
    assert resp.status_code == 200 and resp.json()["must_change_password"] is True
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 401


def test_audit_endpoint(client, admin_token):
    client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    resp = client.get("/api/admin/audit", params={"action": "login", "username": "admin"}, headers=auth(admin_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert all(item["action"] == "LOGIN" for item in body["items"])
