"""v1.4: big demo companies, incidents, engineer tools, AI key from the dashboard, cloud metrics."""
import asyncio
import time

import pytest

from app import auth, config, tenancy
from app.models import AppFlag, Company, Device

from tests.conftest import run


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


def test_big_companies_seed_once(fresh, db, monkeypatch):
    from app.big_companies import seed_big_companies
    monkeypatch.setattr(config, "SEED_BIG_COMPANIES", True)
    added = run(seed_big_companies(db))
    assert set(added) == {"IOT-101", "IOT-102", "IOT-201", "IOT-202", "IOT-301", "IOT-302"}
    assert db.get(Company, "medina-health").name == "Medina Health Hospital"
    assert tenancy.company_of_device("IOT-201") == "medina-health"
    assert db.get(Device, "IOT-301").temp_max == -15
    assert run(seed_big_companies(db)) == []  # only once per database
    # tidy up for the other tests
    for d in added:
        fresh.delete(f"/api/devices/{d}")
    for c in ("atlas-mining", "medina-health", "tangier-coldchain"):
        for u in ("mining_admin", "hospital_admin", "logistics_admin"):
            fresh.delete(f"/api/auth/users/{u}")
        fresh.delete(f"/api/companies/{c}")
    db.query(AppFlag).delete()
    db.commit()


def test_incident_lifecycle(fresh, db):
    from app.models import SecurityAlert
    alert = SecurityAlert(device_id="IOT-002", alert_type="excessive_message_rate", severity="high", description="flood")
    db.add(alert)
    db.commit()
    r = fresh.post("/api/incidents", json={"alert_id": alert.id})
    assert r.status_code == 201
    inc = r.json()["incident"]
    assert inc["device_id"] == "IOT-002" and inc["severity"] == "high" and inc["status"] == "open"
    # the same alert does not open a second incident
    assert fresh.post("/api/incidents", json={"alert_id": alert.id}).json()["existing"] is True
    r = fresh.put(f"/api/incidents/{inc['id']}", json={"status": "investigating", "assignee": "operator"})
    assert r.status_code == 200 and r.json()["incident"]["assignee"] == "operator"
    fresh.post(f"/api/incidents/{inc['id']}/notes", json={"text": "Device quarantined, checking the gateway."})
    r = fresh.put(f"/api/incidents/{inc['id']}", json={"status": "resolved"})
    detail = r.json()["incident"]
    assert detail["status"] == "resolved" and detail["resolved_at"]
    assert [n["kind"] for n in detail["notes"]] == ["created", "assign", "status", "note", "status"]
    assert fresh.put(f"/api/incidents/{inc['id']}", json={"assignee": "nobody-here"}).status_code == 400
    assert fresh.get("/api/incidents?status=resolved").json()["counts"]["resolved"] >= 1


def test_company_sees_only_its_incidents(secured):
    admin = login(secured, "admin", "Admin@2026")
    mine = secured.post("/api/incidents", headers=admin, json={"title": "Farm check", "device_id": "IOT-003"}).json()["incident"]
    other = secured.post("/api/incidents", headers=admin, json={"title": "Office check", "device_id": "IOT-002"}).json()["incident"]
    farm = login(secured, "farm_admin", "Farm@2026")
    ids = {i["id"] for i in secured.get("/api/incidents", headers=farm).json()["incidents"]}
    assert mine["id"] in ids and other["id"] not in ids
    assert secured.get(f"/api/incidents/{other['id']}", headers=farm).status_code == 404
    assert secured.post("/api/incidents", headers=farm, json={"title": "x", "device_id": "IOT-002"}).status_code == 403


def test_engineer_tools(fresh, db):
    from app.simulation_controller import controller
    rows = {d["device_id"]: d for d in fresh.get("/api/engineering/devices").json()["devices"]}
    assert {"IOT-001", "IOT-002", "IOT-003"} <= set(rows)
    assert rows["IOT-001"]["firmware"] == "1.0.0" and rows["IOT-001"]["latest_firmware"] == "1.2.0"

    # maintenance: the alert is stored but the phone does not ring
    r = fresh.post("/api/devices/IOT-002/maintenance", json={"on": True, "reason": "sensor swap"})
    assert r.json()["device"]["maintenance"] is True
    from app.notifier import notifier
    from app.detection_engine import detector
    sent = []

    async def fake_send(settings, alert):
        sent.append(alert)
        return []

    notifier_send = notifier.send
    notifier.send = fake_send
    try:
        fresh.put("/api/notify/settings", json={"enabled": True, "ntfy_topic": "cybershield-test-topic-789", "min_severity": "medium"})

        async def scenario():
            await detector.raise_alert(db, "excessive_message_rate", "high", "flood", device_id="IOT-002")
            await detector.raise_alert(db, "excessive_message_rate", "high", "flood", device_id="IOT-003")
            await asyncio.sleep(0.05)

        run(scenario())
        assert [a["device_id"] for a in sent] == ["IOT-003"]
    finally:
        notifier.send = notifier_send
        fresh.put("/api/notify/settings", json={"enabled": False, "ntfy_topic": ""})
        fresh.post("/api/devices/IOT-002/maintenance", json={"on": False})

    # reboot: the simulated twin goes quiet for a few seconds
    controller._load_devices()
    r = fresh.post("/api/devices/IOT-001/reboot")
    assert r.status_code == 200 and r.json()["simulated"] is True
    assert controller.next_due["IOT-001"] > time.time() + 5
    assert fresh.post("/api/devices/IOT-001/reboot").status_code == 409  # still busy
    assert fresh.post("/api/devices/IOT-999/reboot").status_code == 404
    assert fresh.post("/api/devices/IOT-002/firmware", json={"version": "9.9.9"}).status_code == 400


def test_ai_key_from_dashboard(client, monkeypatch):
    from app import ai_assistant
    assert client.get("/api/ai/status").json()["configured"] is False
    r = client.put("/api/ai/settings", json={"provider": "groq", "api_key": "gsk_test_key_123456"})
    assert r.status_code == 200 and r.json()["configured"] is True and r.json()["key_hint"] == "…3456"
    assert "gsk_test_key" not in r.text  # the key is never sent back
    seen = {}

    async def fake_llm(messages, settings=None):
        seen.update(ai_assistant.active())
        return "CyberShield AI ready"

    monkeypatch.setattr(ai_assistant, "ask_llm", fake_llm)
    assert client.post("/api/ai/test").json()["ok"] is True
    assert seen["provider"] == "groq" and seen["from"] == "dashboard"
    assert client.put("/api/ai/settings", json={"provider": "bad"}).status_code == 400
    client.put("/api/ai/settings", json={"provider": "gemini", "api_key": ""})
    assert client.get("/api/ai/status").json()["configured"] is False


def test_metrics_need_a_token(client, monkeypatch):
    assert client.get("/metrics").status_code == 404
    monkeypatch.setattr(config, "METRICS_TOKEN", "secret-metrics-token")
    assert client.get("/metrics").status_code == 401
    r = client.get("/metrics", headers={"Authorization": "Bearer secret-metrics-token"})
    assert r.status_code == 200 and "cybershield_devices_total" in r.text


def test_platform_only_settings(secured):
    farm = login(secured, "farm_admin", "Farm@2026")
    assert secured.get("/api/ai/settings", headers=farm).status_code == 403
    assert secured.get("/api/engineering/system", headers=farm).status_code == 403
    rows = secured.get("/api/engineering/devices", headers=farm).json()["devices"]
    assert [d["device_id"] for d in rows] == ["IOT-003"]
    admin = login(secured, "admin", "Admin@2026")
    assert secured.get("/api/engineering/system", headers=admin).json()["database"]["engine"] in ("SQLite", "PostgreSQL")
