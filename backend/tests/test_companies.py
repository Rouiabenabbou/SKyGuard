"""Many companies on one system (v1.2): each company only sees and controls its own devices."""
import asyncio
import json

import pytest

from app import auth, config, tenancy


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


def test_demo_companies_seeded(secured):
    admin = login(secured, "admin", "Admin@2026")
    data = secured.get("/api/companies", headers=admin).json()
    ids = {c["company_id"]: c for c in data["companies"]}
    assert {"atlas-farms", "casa-offices", "sahara-solar"} <= set(ids)
    assert ids["atlas-farms"]["devices"] == ["IOT-003"] and "farm_admin" in ids["atlas-farms"]["users"]
    assert "IOT-001" not in data["platform_devices"]  # (ESP32-001 is a platform device when enabled)
    farm = login(secured, "farm_admin", "Farm@2026")
    me = secured.get("/api/auth/me", headers=farm).json()["user"]
    assert me["company_id"] == "atlas-farms" and me["company_name"] == "Atlas Dairy Farms"


def test_company_sees_only_its_devices(secured):
    c = secured
    farm = login(c, "farm_admin", "Farm@2026")
    assert [d["device_id"] for d in c.get("/api/devices", headers=farm).json()["devices"]] == ["IOT-003"]
    assert c.get("/api/devices/IOT-001", headers=farm).status_code == 403
    assert c.post("/api/devices/IOT-002/quarantine", headers=farm).status_code == 403
    assert c.post("/api/devices/IOT-003/quarantine", headers=farm).status_code == 200
    assert c.post("/api/devices/IOT-003/release", headers=farm).status_code == 200
    assert c.get("/api/telemetry?device_id=IOT-001", headers=farm).status_code == 403
    assert c.post("/api/simulation/attack/excessive-traffic", headers=farm).status_code == 403  # default is IOT-002

    topo = c.get("/api/network/topology", headers=farm).json()
    nodes = {n["node_id"] for n in topo["nodes"]}
    assert {"SAT-1", "GS-1", "IOT-003"} <= nodes and not {"IOT-001", "IOT-002"} & nodes
    assert set(topo["routes"]) == {"IOT-003"}
    assert all("IOT-001" not in (l["source_node"], l["target_node"]) for l in topo["links"])

    # the platform still sees everything
    admin = login(c, "admin", "Admin@2026")
    assert len(c.get("/api/devices", headers=admin).json()["devices"]) >= 3


def test_shared_network_is_platform_only(secured):
    farm = login(secured, "farm_admin", "Farm@2026")
    for method, path in [("post", "/api/simulation/reset"), ("post", "/api/failover/drill"),
                         ("post", "/api/network/links/L-SAT-GS/state"), ("post", "/api/network/nodes/SAT-1/state"),
                         ("get", "/api/companies"), ("post", "/api/quarantine/settings")]:
        r = secured.get(path, headers=farm) if method == "get" else secured.post(path, headers=farm, json={})
        assert r.status_code == 403, path


def test_alerts_exports_and_report_are_filtered(secured, db):
    from app.models import SecurityAlert
    other = SecurityAlert(device_id="IOT-001", alert_type="test_other", severity="low", description="IOT-001 test")
    mine = SecurityAlert(device_id="IOT-003", alert_type="test_mine", severity="low", description="IOT-003 test")
    db.add_all([other, mine])
    db.commit()
    farm = login(secured, "farm_admin", "Farm@2026")
    seen = {a["device_id"] for a in secured.get("/api/alerts?limit=500", headers=farm).json()["alerts"]}
    assert "IOT-001" not in seen and "IOT-003" in seen
    assert secured.post(f"/api/alerts/{other.id}/resolve", headers=farm).status_code == 404
    assert secured.post(f"/api/ai/explain-alert/{other.id}", headers=farm).status_code == 404
    csv_text = secured.get("/api/export/alerts.csv", headers=farm).text
    assert "test_mine" in csv_text and "test_other" not in csv_text
    report = secured.get("/api/report/summary", headers=farm).json()
    assert [d["device_id"] for d in report["devices"]] == ["IOT-003"] and report["company"] == "Atlas Dairy Farms"


def test_company_admin_manages_only_own_users_and_devices(secured):
    c = secured
    farm = login(c, "farm_admin", "Farm@2026")
    r = c.post("/api/auth/users", headers=farm, json={"username": "farm_worker", "password": "Worker2026", "role": "viewer"})
    assert r.status_code == 201 and r.json()["user"]["company_id"] == "atlas-farms"
    names = {u["username"] for u in c.get("/api/auth/users", headers=farm).json()["users"]}
    assert names == {"farm_admin", "farm_worker"}
    assert c.delete("/api/auth/users/operator", headers=farm).status_code == 404
    audit_users = {e["username"] for e in c.get("/api/audit?limit=500", headers=farm).json()["entries"]}
    assert audit_users <= {"farm_admin", "farm_worker"}

    # a device added by the farm admin belongs to the farm
    r = c.post("/api/devices", headers=farm, json={"device_id": "FARM-010", "device_name": "Barn sensor",
               "device_type": "sensor", "location": "Barn", "temp_min": 0, "temp_max": 40,
               "humidity_min": 10, "humidity_max": 90, "connection_type": "5g"})
    assert r.status_code == 201, r.text
    assert r.json()["device"]["company_id"] == "atlas-farms"
    assert tenancy.company_of_device("FARM-010") == "atlas-farms"

    # the platform moves it to another company: the farm can't see it any more
    admin = login(c, "admin", "Admin@2026")
    assert c.put("/api/companies/devices/FARM-010", headers=admin, json={"company_id": "casa-offices"}).status_code == 200
    assert "FARM-010" not in {d["device_id"] for d in c.get("/api/devices", headers=farm).json()["devices"]}
    offices = login(c, "offices_admin", "Offices@2026")
    assert "FARM-010" in {d["device_id"] for d in c.get("/api/devices", headers=offices).json()["devices"]}
    assert c.delete("/api/devices/FARM-010", headers=offices).status_code == 200
    assert c.delete("/api/auth/users/farm_worker", headers=farm).status_code == 200


def test_platform_admin_creates_company(secured):
    admin = login(secured, "admin", "Admin@2026")
    r = secured.post("/api/companies", headers=admin, json={"company_id": "test-co", "name": "Test Co",
                     "admin_username": "testco_admin", "admin_password": "TestCo2026"})
    assert r.status_code == 201, r.text
    assert secured.delete("/api/companies/test-co", headers=admin).status_code == 409  # still has a user
    me = secured.get("/api/auth/me", headers=login(secured, "testco_admin", "TestCo2026")).json()["user"]
    assert me["company_id"] == "test-co"
    assert secured.delete("/api/auth/users/testco_admin", headers=admin).status_code == 200
    assert secured.delete("/api/companies/test-co", headers=admin).status_code == 200


def test_scrub_and_websocket_filter():
    hidden = frozenset({"IOT-001"})
    data = {"routes": {"IOT-001": {}, "IOT-003": {}},
            "links": [{"source_node": "IOT-001", "target_node": "SAT-1"}, {"source_node": "IOT-003", "target_node": "SAT-1"}],
            "events": [{"device_id": None, "description": "IOT-001 now on backup"}, {"description": "SAT-1 ok"}]}
    clean = tenancy.scrub(data, hidden)
    assert set(clean["routes"]) == {"IOT-003"} and len(clean["links"]) == 1 and len(clean["events"]) == 1
    assert tenancy.message_is_hidden({"device_id": "IOT-001", "temperature": 20}, hidden)
    assert not tenancy.message_is_hidden({"device_id": "IOT-003"}, hidden)
    assert tenancy.message_is_hidden({"device": {"device_id": "IOT-001"}, "reading": {"device_id": "IOT-001"}}, hidden)

    from app.websocket_manager import WebSocketManager

    class FakeWS:
        def __init__(self):
            self.sent = []

        async def send_text(self, text):
            self.sent.append(json.loads(text))

    m = WebSocketManager()
    platform, farm = FakeWS(), FakeWS()
    m.active |= {platform, farm}
    m.company[farm] = "atlas-farms"
    asyncio.run(m.broadcast("telemetry", {"device_id": "IOT-001", "temperature": 20}))
    asyncio.run(m.broadcast("telemetry", {"device_id": "IOT-003", "temperature": 21}))
    assert len(platform.sent) == 2
    assert [s["data"]["device_id"] for s in farm.sent] == ["IOT-003"]


def test_ai_context_is_scoped(db):
    from app import ai_assistant
    token = tenancy.set_current(tenancy.Scope(company_id="atlas-farms", hidden=tenancy.hidden_for("atlas-farms")))
    try:
        ctx = ai_assistant.build_context(db)
    finally:
        tenancy._current.reset(token)
    assert [d["id"] for d in ctx["devices"]] == ["IOT-003"]
    assert not set(ctx["routes"]) - {"IOT-003"}
