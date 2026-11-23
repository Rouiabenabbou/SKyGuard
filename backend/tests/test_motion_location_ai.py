"""Motion sensors (Rule F), real locations and the AI assistant (v1.1)."""
import pytest

from app import ai_assistant, config
from app.models import MotionReading, SecurityAlert
from app.telemetry_service import ingest_telemetry
from tests.conftest import run


def test_farm_device_has_motion_and_location(fresh, client):
    d = client.get("/api/devices/IOT-003").json()["device"]
    assert d["has_motion"] is True and d["place_type"] == "farm"
    assert 33 < d["latitude"] < 35 and -6 < d["longitude"] < -5
    node = next(n for n in client.get("/api/network/topology").json()["nodes"] if n["node_id"] == "GS-1")
    assert node["place_type"] == "ground_station" and node["latitude"] is not None


def test_motion_reading_stored_and_night_alert(fresh, db, client, monkeypatch):
    run(ingest_telemetry(db, {"device_id": "IOT-003", "temperature": 20, "humidity": 60, "battery": 90,
                              "motion": False, "source": "test"}))
    assert db.query(MotionReading).count() == 1
    monkeypatch.setattr("app.motion_service.is_night", lambda hour: False)
    run(ingest_telemetry(db, {"device_id": "IOT-003", "temperature": 20, "humidity": 60, "battery": 90,
                              "motion": True, "source": "test"}))
    assert db.query(SecurityAlert).filter(SecurityAlert.alert_type == "movement_detected").count() == 0  # daytime
    r = client.post("/api/devices/IOT-003/motion?night=true")
    assert r.status_code == 200 and r.json()["motion_now"] is True
    alert = db.query(SecurityAlert).filter(SecurityAlert.alert_type == "movement_detected").one()
    assert alert.severity == "high" and "Saïss" in alert.description
    assert client.get("/api/devices/IOT-003").json()["device"]["security_status"] == "normal"  # not "suspicious"
    assert client.post("/api/devices/IOT-002/motion").status_code == 400  # no motion sensor


def test_set_profile(fresh, client):
    try:
        r = client.put("/api/profiles/IOT-002", json={"latitude": 35.7595, "longitude": -5.834,
                                                      "place_type": "company", "address": "Tangier office",
                                                      "has_motion": True})
        assert r.status_code == 200
        d = client.get("/api/devices/IOT-002").json()["device"]
        assert d["address"] == "Tangier office" and d["has_motion"] is True
        assert client.put("/api/profiles/IOT-002", json={"latitude": 10}).status_code == 400
        assert client.put("/api/profiles/SAT-1", json={"has_motion": True}).status_code == 400
        assert client.put("/api/profiles/NOPE", json={}).status_code == 404
    finally:
        client.put("/api/profiles/IOT-002", json={"latitude": 33.5856, "longitude": -7.6328, "place_type": "company",
                                                  "address": "Office tower, Maarif business district, Casablanca",
                                                  "has_motion": False})


def test_ai_offline_analyst(fresh, client):
    assert client.get("/api/ai/status").json()["provider"] == "offline"
    client.post("/api/simulation/attack/abnormal-reading?device_id=IOT-001")
    import time
    time.sleep(0.5)
    r = client.post("/api/ai/chat", json={"message": "what is wrong right now?"}).json()
    assert r["source"] == "offline" and "Situation now" in r["answer"]
    r = client.post("/api/ai/chat", json={"message": "tell me about IOT-003"}).json()
    assert "IOT-003" in r["answer"] and "motion" in r["answer"]
    assert "Incident report" in client.post("/api/ai/report").json()["answer"]


def test_ai_explain_alert_offline(fresh, db, client):
    run(ingest_telemetry(db, {"device_id": "IOT-001", "temperature": 95, "humidity": 2, "battery": 90, "source": "t"}))
    alert = db.query(SecurityAlert).first()
    r = client.post(f"/api/ai/explain-alert/{alert.id}").json()
    assert "Likely cause" in r["answer"] and "device IOT-001" in r["commands"]
    assert client.post("/api/ai/explain-alert/99999").status_code == 404


def test_ai_uses_llm_when_key_set_and_falls_back(fresh, client, monkeypatch):
    monkeypatch.setattr(config, "AI_API_KEY", "test-key")
    monkeypatch.setattr(config, "AI_PROVIDER", "groq")
    seen = {}

    async def fake_llm(messages):
        seen["messages"] = messages
        return "IOT-002 looks fine. Run `status` to check, or `quarantine IOT-002` if unsure."
    monkeypatch.setattr(ai_assistant, "ask_llm", fake_llm)
    r = client.post("/api/ai/chat", json={"message": "is IOT-002 ok?"}).json()
    assert r["source"] == "groq" and r["commands"] == ["status", "quarantine IOT-002"]
    assert "SIMULATED" in seen["messages"][0]["content"] and "IOT-002" in seen["messages"][1]["content"]

    async def broken(messages):
        raise RuntimeError("quota exceeded")
    monkeypatch.setattr(ai_assistant, "ask_llm", broken)
    r = client.post("/api/ai/chat", json={"message": "status?"}).json()
    assert r["source"] == "offline" and "quota exceeded" in r["answer"]
