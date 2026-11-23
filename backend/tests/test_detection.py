"""Detection rules A-C and quarantine blocking, through the real ingest path."""
from app.models import QuarantineRecord, SecurityAlert, Telemetry
from app.telemetry_service import ingest_telemetry
from tests.conftest import run


def reading(device_id="IOT-002", temperature=22.0, humidity=45.0, battery=90.0):
    return {"device_id": device_id, "temperature": temperature, "humidity": humidity,
            "battery": battery, "source": "test"}


def test_valid_reading_is_stored(fresh, db):
    result = run(ingest_telemetry(db, reading()))
    assert result["ok"] is True
    assert db.query(Telemetry).filter(Telemetry.device_id == "IOT-002").count() == 1


def test_malformed_reading_is_rejected(fresh, db):
    result = run(ingest_telemetry(db, {"device_id": "IOT-002", "temperature": "hot"}))
    assert result == {**result, "ok": False, "error": "invalid_message"}
    assert db.query(Telemetry).count() == 0


def test_rule_b_unauthorized_device(fresh, db):
    result = run(ingest_telemetry(db, reading(device_id="IOT-999")))
    assert result["error"] == "unknown_device"
    alert = db.query(SecurityAlert).filter(SecurityAlert.alert_type == "unauthorized_device").one()
    assert alert.severity in ("high", "critical")
    assert db.query(Telemetry).count() == 0  # never stored


def test_rule_c_abnormal_value_marks_suspicious(fresh, db, client):
    run(ingest_telemetry(db, reading(device_id="IOT-001", temperature=85.0, humidity=2.0)))
    assert db.query(SecurityAlert).filter(SecurityAlert.alert_type == "abnormal_sensor_value").count() == 1
    device = client.get("/api/devices/IOT-001").json()["device"]
    assert device["security_status"] == "suspicious"  # not quarantined: a human decides
    assert db.query(QuarantineRecord).count() == 0


def test_rule_a_flood_triggers_alert_and_auto_quarantine(fresh, db, client):
    for _ in range(80):  # 80 messages in well under 5 s = more than 10 msg/s
        run(ingest_telemetry(db, reading()))
    assert db.query(SecurityAlert).filter(SecurityAlert.alert_type == "excessive_message_rate").count() == 1
    device = client.get("/api/devices/IOT-002").json()["device"]
    assert device["security_status"] == "quarantined"
    record = db.query(QuarantineRecord).one()
    assert record.triggered_by == "auto"


def test_quarantined_device_traffic_is_blocked(fresh, db, client):
    client.post("/api/devices/IOT-003/quarantine", json={"reason": "test"})
    stored_before = db.query(Telemetry).count()
    for _ in range(3):
        result = run(ingest_telemetry(db, reading(device_id="IOT-003")))
        assert result["error"] == "quarantined"
    assert db.query(Telemetry).count() == stored_before  # nothing stored
    db.expire_all()
    assert db.query(QuarantineRecord).one().blocked_messages == 3


def test_alert_cooldown_avoids_duplicates(fresh, db):
    for _ in range(3):
        run(ingest_telemetry(db, reading(device_id="IOT-999")))
    assert db.query(SecurityAlert).filter(SecurityAlert.alert_type == "unauthorized_device").count() == 1
