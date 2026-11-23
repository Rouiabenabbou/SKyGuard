"""Operator adds and removes IoT devices: POST/DELETE /api/devices."""
from app.models import NetworkLink, NetworkNode, Telemetry
from app.simulation_controller import controller
from app.telemetry_service import ingest_telemetry
from tests.conftest import run

NEW = {"device_id": "IOT-004", "device_name": "Water Tank 04", "device_type": "Water Level Sensor",
       "location": "Reservoir", "connection_type": "satellite", "temp_min": 0, "temp_max": 40,
       "humidity_min": 10, "humidity_max": 90}


def test_add_satellite_device_gets_node_links_route_and_twin(fresh, db, client):
    try:
        r = client.post("/api/devices", json=NEW)
        assert r.status_code == 201, r.text
        assert r.json()["device"]["added_by_operator"] is True
        assert db.get(NetworkNode, "IOT-004").node_type == "iot_device"
        links = {l.link_id: l for l in db.query(NetworkLink).filter(NetworkLink.source_node == "IOT-004")}
        assert links["L-IOT004-SAT"].is_active_path and not links["L-IOT004-5G"].is_active_path
        route = client.get("/api/network/status").json()["routes"]["IOT-004"]
        assert route["path"] == ["IOT-004", "SAT-1", "GS-1", "CORE"]
        assert "IOT-004" in controller.devices  # simulated twin
        p = controller.devices["IOT-004"].profile
        assert 0 < p["temp"] - p["temp_swing"] and p["temp"] + p["temp_swing"] < 40
        # its readings go through the normal ingest path
        assert run(ingest_telemetry(db, {"device_id": "IOT-004", "temperature": 20.0, "humidity": 50.0,
                                         "battery": 90.0, "source": "test"}))["ok"] is True
        assert db.query(Telemetry).filter(Telemetry.device_id == "IOT-004").count() == 1
        assert client.post("/api/devices", json=NEW).status_code == 409  # duplicate
    finally:
        client.delete("/api/devices/IOT-004")
    assert db.get(NetworkNode, "IOT-004") is None
    assert db.query(NetworkLink).filter(NetworkLink.source_node == "IOT-004").count() == 0
    assert "IOT-004" not in controller.devices
    assert client.get("/api/devices/IOT-004").status_code == 404


def test_real_board_is_not_simulated(fresh, client):
    try:
        r = client.post("/api/devices", json={**NEW, "device_id": "ESP32-002", "connection_type": "5g",
                                              "simulated": False})
        assert r.status_code == 201
        assert "ESP32-002" not in controller.devices
        route = client.get("/api/network/status").json()["routes"]["ESP32-002"]
        assert route["path"] == ["ESP32-002", "BS-5G", "CORE"]
    finally:
        client.delete("/api/devices/ESP32-002")


def test_add_device_validation_and_builtin_protection(fresh, client):
    assert client.post("/api/devices", json={**NEW, "device_id": "bad id!"}).status_code == 400
    assert client.post("/api/devices", json={**NEW, "device_id": "SAT-1"}).status_code == 409
    assert client.post("/api/devices", json={**NEW, "temp_min": 50}).status_code == 422
    assert client.delete("/api/devices/IOT-001").status_code == 409
    assert client.delete("/api/devices/NOPE-9").status_code == 404
