"""Login, roles, brute-force lock and the audit log (v1.1)."""
import pytest

from app import auth, config


@pytest.fixture()
def secured(client, monkeypatch):
    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    auth._failures.clear()
    yield client
    auth._failures.clear()


def login(client, user, password):
    r = client.post("/api/auth/login", json={"username": user, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_passwords_are_hashed():
    h = auth.hash_password("Secret123")
    assert "Secret123" not in h and h.startswith("pbkdf2_sha256$")
    assert auth.verify_password("Secret123", h) and not auth.verify_password("secret123", h)


def test_login_required_and_roles(secured):
    c = secured
    assert c.get("/api/health").status_code == 200  # public
    assert c.get("/api/devices").status_code == 401
    viewer = login(c, "viewer", "Viewer@2026")
    operator = login(c, "operator", "Operator@2026")
    admin = login(c, "admin", "Admin@2026")

    assert c.get("/api/devices", headers=viewer).status_code == 200
    assert c.post("/api/devices/IOT-001/quarantine", headers=viewer).status_code == 403
    assert c.post("/api/devices/IOT-001/quarantine", headers=operator).status_code == 200
    assert c.post("/api/devices/IOT-001/release", headers=operator).status_code == 200
    # admin-only: network builder, device management, users, audit
    assert c.post("/api/network/nodes", headers=operator, json={"node_id": "SAT-9", "node_type": "satellite"}).status_code == 403
    assert c.get("/api/audit", headers=operator).status_code == 403
    assert c.get("/api/auth/users", headers=admin).status_code == 200
    assert c.get("/api/auth/me", headers=operator).json()["user"]["role"] == "operator"
    # token in the query string works too (CSV downloads)
    assert c.get(f"/api/export/alerts.csv?token={admin['Authorization'][7:]}").status_code == 200


def test_wrong_password_and_lock(secured, monkeypatch):
    monkeypatch.setattr(config, "LOGIN_MAX_FAILURES", 3)
    for _ in range(3):
        assert secured.post("/api/auth/login", json={"username": "operator", "password": "nope"}).status_code == 401
    r = secured.post("/api/auth/login", json={"username": "operator", "password": "Operator@2026"})
    assert r.status_code == 429  # locked even with the right password


def test_logout_and_user_management(secured):
    c = secured
    admin = login(c, "admin", "Admin@2026")
    r = c.post("/api/auth/users", headers=admin, json={"username": "farmer1", "password": "short", "role": "operator"})
    assert r.status_code == 400  # weak password
    assert c.post("/api/auth/users", headers=admin,
                  json={"username": "farmer1", "password": "Farm2026x", "role": "viewer"}).status_code == 201
    farmer = login(c, "farmer1", "Farm2026x")
    assert c.post("/api/auth/password", headers=farmer,
                  json={"old_password": "Farm2026x", "new_password": "Farm2027y"}).status_code == 200
    assert c.post("/api/auth/logout", headers=farmer).status_code == 200
    assert c.get("/api/devices", headers=farmer).status_code == 401  # token ended
    assert c.put("/api/auth/users/admin", headers=admin, json={"role": "viewer"}).status_code == 409  # last admin
    assert c.delete("/api/auth/users/admin", headers=admin).status_code == 409  # can't delete yourself
    assert c.delete("/api/auth/users/farmer1", headers=admin).status_code == 200


def test_audit_log_records_changes_and_denials(secured):
    c = secured
    admin = login(c, "admin", "Admin@2026")
    viewer = login(c, "viewer", "Viewer@2026")
    c.post("/api/auth/login", json={"username": "admin", "password": "bad"})
    c.post("/api/devices/IOT-002/quarantine", headers=viewer)  # denied
    c.post("/api/devices/IOT-002/quarantine", headers=admin)
    c.post("/api/devices/IOT-002/release", headers=admin)
    entries = c.get("/api/audit?limit=20", headers=admin).json()["entries"]
    actions = [(e["username"], e["action"], e["outcome"]) for e in entries]
    assert ("admin", "release device", "ok") in actions
    assert ("admin", "quarantine device", "ok") in actions
    assert ("viewer", "quarantine device", "denied") in actions
    assert ("admin", "login failed", "failed") in actions
    assert c.get("/api/audit/export.csv", headers=admin).text.startswith("id,timestamp,username")


def test_websocket_needs_token(secured):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with secured.websocket_connect("/ws") as ws:
            ws.receive_json()
    admin = login(secured, "admin", "Admin@2026")
    with secured.websocket_connect(f"/ws?token={admin['Authorization'][7:]}") as ws:
        assert ws.receive_json()["type"] == "welcome"
