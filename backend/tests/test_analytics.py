"""Long-term data and analytics (v1.3): hourly warehouse, generated history, trends, heatmap, forecast."""
import time
from datetime import timedelta

import pytest

from app import auth, config, warehouse
from app.models import AlertHourly, Telemetry, TelemetryArchive, TelemetryHourly, utcnow


@pytest.fixture(scope="module")
def history(client):
    """Generate 10 days of history once (5-minute readings) for the tests in this file."""
    from app.database import SessionLocal
    with SessionLocal() as db:
        warehouse.clear_history(db)
    state = warehouse.history_job.run(days=10, interval_minutes=5, seed=42)
    assert state["message"].startswith("done"), state
    yield state
    with SessionLocal() as db:
        warehouse.clear_history(db)


def test_history_fills_the_warehouse(history, db):
    devices = 3  # IOT-001..003 in the test setup (ESP32 off)
    assert history["rows"] >= devices * 10 * 24 * 12 * 0.95
    assert db.query(TelemetryArchive).count() == history["rows"]
    assert db.query(TelemetryHourly).count() >= devices * 10 * 24 * 0.95
    assert db.query(AlertHourly).count() > 0


def test_summary_trends_alerts(client, history):
    s = client.get("/api/analytics/summary").json()
    assert s["raw_readings"]["archive"] == history["rows"] and s["days_covered"] >= 9
    t = client.get("/api/analytics/trends?days=10&bucket=day").json()
    assert set(t["series"]) >= {"IOT-001", "IOT-002", "IOT-003"}
    desert = t["series"]["IOT-001"]
    assert len(desert) >= 9 and desert[0]["temp_max"] > desert[0]["temp_min"] + 10  # whole days only; big day/night swing
    office = t["series"]["IOT-002"]
    assert office[0]["temp_max"] - office[0]["temp_min"] < desert[0]["temp_max"] - desert[0]["temp_min"]
    a = client.get("/api/analytics/alerts?days=10").json()
    assert a["total"] > 0 and len(a["heatmap"]) == 7 and len(a["heatmap"][0]) == 24


def test_forecast(client, history):
    f = client.get("/api/analytics/forecast?device_id=IOT-001&hours=24").json()
    assert f["enough_data"] and len(f["points"]) == 24
    p = f["points"][0]
    assert p["temp_low"] <= p["temp"] <= p["temp_high"]
    assert client.get("/api/analytics/forecast?device_id=NOPE").status_code == 404


def test_live_rollup_survives_reset(fresh, db):
    from app.models import Device
    now = utcnow()
    db.add_all([Telemetry(device_id="IOT-002", temperature=20 + i, humidity=40, battery=90, source="test",
                          timestamp=now - timedelta(minutes=i)) for i in range(5)])
    db.commit()
    assert db.get(Device, "IOT-002") is not None
    fresh.post("/api/simulation/reset")  # rolls up first, then wipes the live table
    fresh.post("/api/simulation/pause")
    db.expire_all()
    hour = warehouse.floor_hour(now)
    rows = db.query(TelemetryHourly).filter(TelemetryHourly.device_id == "IOT-002", TelemetryHourly.hour >= hour - timedelta(hours=1)).all()
    assert sum(r.readings for r in rows) >= 5
    # a later rollup with fewer live readings never shrinks the stored hour
    warehouse.rollup_live(db, hours_back=None)
    db.expire_all()
    assert sum(r.readings for r in db.query(TelemetryHourly).filter(TelemetryHourly.device_id == "IOT-002",
               TelemetryHourly.hour >= hour - timedelta(hours=1))) >= 5


def test_company_sees_only_its_analytics(client, history, monkeypatch):
    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    auth._failures.clear()
    r = client.post("/api/auth/login", json={"username": "farm_admin", "password": "Farm@2026"})
    farm = {"Authorization": f"Bearer {r.json()['token']}"}
    t = client.get("/api/analytics/trends?days=10", headers=farm).json()
    assert set(t["series"]) == {"IOT-003"}
    assert {d["device_id"] for d in client.get("/api/analytics/summary", headers=farm).json()["devices"]} == {"IOT-003"}
    assert client.get("/api/analytics/forecast?device_id=IOT-001", headers=farm).status_code == 403
    assert client.post("/api/analytics/history", headers=farm, json={"days": 1}).status_code == 403


def test_history_endpoint_runs_in_background(client):
    r = client.post("/api/analytics/history", json={"days": 1, "interval_minutes": 30})
    assert r.status_code == 202
    for _ in range(100):
        if not client.get("/api/analytics/history").json()["running"]:
            break
        time.sleep(0.1)
    assert client.get("/api/analytics/history").json()["message"].startswith("done")
