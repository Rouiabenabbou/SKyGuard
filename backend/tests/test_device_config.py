"""Operator device configuration: PUT /api/devices/{id}/config."""
from app.models import NetworkEvent, SecurityAlert
from app.telemetry_service import ingest_telemetry
from tests.conftest import run

IOT002 = {"device_name": "Smart Building 02", "device_type": "Smart Building Sensor",
          "location": "City office tower", "temp_min": 15, "temp_max": 32,
          "humidity_min": 25, "humidity_max": 70}


def test_config_updates_device_and_detection(fresh, db, client):
    try:
        r = client.put("/api/devices/IOT-002/config",
                       json={**IOT002, "location": "Lab 3", "temp_max": 25})
        assert r.status_code == 200
        body = r.json()
        assert body["updated"] is True
        assert body["device"]["location"] == "Lab 3"
        assert body["device"]["ranges"]["temperature"] == [15, 25]
        assert db.query(NetworkEvent).filter(NetworkEvent.event_type == "device_configured").count() == 1

        # 28 °C was fine before (max 32); with the new limit (max 25) it is abnormal.
        run(ingest_telemetry(db, {"device_id": "IOT-002", "temperature": 28.0, "humidity": 45.0,
                                  "battery": 90.0, "source": "test"}))
        assert db.query(SecurityAlert).filter(SecurityAlert.alert_type == "abnormal_sensor_value").count() == 1
    finally:
        client.put("/api/devices/IOT-002/config", json=IOT002)


def test_config_rejects_bad_ranges(fresh, client):
    assert client.put("/api/devices/IOT-002/config", json={**IOT002, "temp_min": 40}).status_code == 422
    assert client.put("/api/devices/IOT-002/config", json={**IOT002, "humidity_max": 120}).status_code == 422
    assert client.put("/api/devices/IOT-002/config", json={**IOT002, "device_name": ""}).status_code == 422


def test_config_unknown_device_is_404(client):
    assert client.put("/api/devices/NOPE-1/config", json=IOT002).status_code == 404
