"""v1.5: bigger network, more devices, investigation graph, re-wiring a device, OmniRoute AI option."""
import pytest

from app import ai_assistant, auth, config, tenancy
from app.models import AppFlag, Company, CompanyDevice, Device, NetworkLink, NetworkNode, SecurityAlert

from tests.conftest import run


def login(client, user, password):
    r = client.post("/api/auth/login", json={"username": user, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _tidy_network(fresh, db, added):
    from app.network_expansion import INFRA_NODES
    for d in added:
        assert fresh.delete(f"/api/devices/{d}").status_code == 200
    for node_id, *_ in INFRA_NODES:
        fresh.delete(f"/api/network/nodes/{node_id}")
    db.query(AppFlag).delete()
    db.commit()


def test_network_v15_seed_and_routes(fresh, db, monkeypatch):
    from app.network_expansion import seed_network_v15
    monkeypatch.setattr(config, "SEED_BIG_COMPANIES", True)
    added = run(seed_network_v15(db))
    try:
        # only the platform devices + those of the 3 classic demo companies (the big ones aren't seeded here)
        assert {"IOT-004", "IOT-006", "IOT-008", "IOT-401", "IOT-402"} <= set(added)
        assert "IOT-103" not in added  # Atlas Mining doesn't exist in this database
        assert db.get(NetworkNode, "SAT-2").node_type == "satellite"
        assert db.get(NetworkLink, "L-SAT1-GS2").is_active_path is False  # backup downlink
        assert tenancy.company_of_device("IOT-004") == "atlas-farms"
        assert db.get(CompanyDevice, "IOT-401") is None  # platform device
        assert run(seed_network_v15(db)) == []  # only once
        routes = fresh.get("/api/network/topology").json()["routes"]
        assert routes["IOT-402"]["path"] == ["IOT-402", "BS-5G-RBT", "CORE"]
        assert routes["IOT-008"]["path"] == ["IOT-008", "SAT-2", "GS-2", "CORE"]
        # GS-1 down: SAT-1 devices still reach the core through the backup downlink to GS-2
        fresh.post("/api/network/nodes/GS-1/state", json={"state": "offline"})
        r = fresh.get("/api/network/topology").json()["routes"]["IOT-001"]
        assert r["connected"] and "GS-2" in r["path"]
        fresh.post("/api/network/nodes/GS-1/state", json={"state": "auto"})
    finally:
        _tidy_network(fresh, db, added)


def test_graph_endpoint(fresh, db):
    db.add(SecurityAlert(device_id="IOT-002", alert_type="excessive_message_rate", severity="high", description="flood"))
    db.add(SecurityAlert(device_id="ROGUE-77", alert_type="unauthorized_device", severity="medium", description="rogue"))
    db.commit()
    g = fresh.get("/api/analytics/graph").json()
    nodes = {n["id"]: n for n in g["nodes"]}
    assert nodes["SAT-1"]["disposition"] == "asset"
    assert nodes["IOT-002"]["disposition"] == "malicious"
    assert nodes["OBS:excessive_message_rate"]["kind"] == "observable"
    assert nodes["ROGUE-77"]["kind"] == "unknown_device"
    assert nodes["CO:casa-offices"]["kind"] == "company"
    kinds = {e["kind"] for e in g["edges"]}
    assert {"link", "owns", "alert"} <= kinds
    assert g["indicators"][0]["open"] >= 1
    assert len(g["timeline"]) == 25 and sum(b["high"] for b in g["timeline"]) >= 1
    assert g["can_edit"] is True


def test_graph_tenancy_and_layout(fresh, client, monkeypatch):
    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    auth._failures.clear()
    h = login(client, "farm_admin", "Farm@2026")
    g = client.get("/api/analytics/graph", headers=h).json()
    ids = {n["id"] for n in g["nodes"]}
    assert "IOT-003" in ids and "IOT-002" not in ids and "IOT-001" not in ids
    assert "CO:casa-offices" not in ids and "CO:atlas-farms" in ids
    assert all(e["source"] in ids and e["target"] in ids for e in g["edges"])
    assert g["can_edit"] is False
    # a company may not re-wire devices (shared network)
    assert client.post("/api/network/devices/IOT-003/access", headers=h, json={"access_node": "BS-5G"}).status_code == 403
    # layouts are saved per user, also for viewers
    v = login(client, "viewer", "Viewer@2026")
    assert client.put("/api/analytics/graph/layout", headers=v, json={"positions": {"SAT-1": [10, 20]}}).status_code == 200
    assert client.get("/api/analytics/graph/layout", headers=v).json()["positions"] == {"SAT-1": [10.0, 20.0]}
    assert client.get("/api/analytics/graph/layout", headers=h).json()["positions"] == {}
    auth._failures.clear()


def test_rewire_device(fresh, db):
    r = fresh.post("/api/network/devices/IOT-002/access", json={"access_node": "SAT-1", "backup_node": "BS-5G"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Device, "IOT-002").connection_type == "satellite"
    route = fresh.get("/api/network/topology").json()["routes"]["IOT-002"]
    assert route["path"] == ["IOT-002", "SAT-1", "GS-1", "CORE"]
    assert fresh.post("/api/network/devices/IOT-002/access", json={"access_node": "CORE"}).status_code == 400
    assert fresh.post("/api/network/devices/IOT-002/access", json={"access_node": "BS-5G"}).status_code == 200
    assert fresh.get("/api/network/topology").json()["routes"]["IOT-002"]["path"] == ["IOT-002", "BS-5G", "CORE"]


def test_omniroute_provider(fresh, db):
    r = fresh.put("/api/ai/settings", json={"provider": "omniroute", "base_url": "http://localhost:20128/v1"})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["configured"] is True and s["provider"] == "omniroute" and s["model"] == "auto"  # no key needed
    assert ai_assistant.endpoint("omniroute") == "http://localhost:20128/v1/chat/completions"
    assert fresh.put("/api/ai/settings", json={"provider": "omniroute", "base_url": "ftp://x"}).status_code == 400
    fresh.put("/api/ai/settings", json={"provider": "gemini", "api_key": "", "base_url": ""})
    assert fresh.get("/api/ai/status").json()["configured"] is False
