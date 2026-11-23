"""v2.2: Huawei IoTDA bridge, ModelArts / MindSpore anomaly model, lab test report."""
import json

import pytest

from app import config
from app.ml_autoencoder import AEDetector, ae_detector
from app.models import Telemetry
from app.security_events import is_lab
from tests.test_v21 import login


def push_body(node_id, t=23.5, h=48.0):
    return {"resource": "device.property", "event": "report", "event_time": "20261104T101010Z",
            "notify_data": {"header": {"device_id": f"66aa_{node_id}", "node_id": node_id, "product_id": "66aa"},
                            "body": {"services": [{"service_id": "Sensor", "event_time": "20261104T101010Z",
                                                   "properties": {"temperature": t, "humidity": h, "battery": 97}}]}}}


def test_iotda_push(fresh, db, monkeypatch):
    c = fresh
    monkeypatch.setattr(config, "IOTDA_PUSH_TOKEN", "")
    assert c.post("/api/iotda/push?token=x", json=push_body("IOT-001")).status_code == 404  # off by default
    monkeypatch.setattr(config, "IOTDA_PUSH_TOKEN", "s3cret-token")
    monkeypatch.setattr(config, "AUTH_ENABLED", True)  # the push needs no login, only the token
    assert c.post("/api/iotda/push?token=wrong", json=push_body("IOT-001")).status_code == 401
    r = c.post("/api/iotda/push?token=s3cret-token", json=push_body("IOT-001")).json()
    assert r["ok"] and r["accepted"] == 1
    row = db.query(Telemetry).filter(Telemetry.device_id == "IOT-001").order_by(Telemetry.id.desc()).first()
    assert row.source == "iotda/https" and row.temperature == 23.5 and is_lab(row.source)
    bad = c.post("/api/iotda/push?token=s3cret-token", json=push_body("IOT-999")).json()  # unknown device: Rule B
    assert not bad["ok"] and bad["results"][0]["error"] == "unknown_device"
    assert c.post("/api/iotda/push?token=s3cret-token", json={"resource": "device.status"}).json()["accepted"] == 0
    monkeypatch.setattr(config, "AUTH_ENABLED", False)
    st = c.get("/api/iotda/status").json()
    assert st["enabled"] and st["accepted"] >= 1 and st["rejected"] >= 1 and "s3cret" not in json.dumps(st)


def test_lab_sources():
    assert is_lab("esp32/mqtt") and is_lab("iotda/https")
    assert not is_lab("builtin/mqtt") and not is_lab("attack-sim/direct") and not is_lab(None)


def test_lab_report(fresh, monkeypatch):
    c = fresh
    assert c.get("/api/lab/report?hours=1").json()["note"]  # no real board yet: says so, no numbers
    monkeypatch.setattr(config, "IOTDA_PUSH_TOKEN", "t")
    for i in range(4):
        c.post("/api/iotda/push?token=t", json=push_body("IOT-002", 22 + i * 0.1, 50))
    r = c.get("/api/lab/report?hours=1").json()
    d = next(x for x in r["devices"] if x["device_id"] == "IOT-002")
    assert d["readings"] == 4 and d["transport"] == {"https": 4} and d["temperature"]["max"] == 22.3
    md = c.get("/api/lab/report?hours=1&format=md").text
    assert "# CyberShield lab test report" in md and "IOT-002" in md


def test_autoencoder_model(tmp_path):
    assert ae_detector.model, ae_detector.error  # the shipped starter model loads
    m = ae_detector.model
    assert len(m["layers"]) == 4 and m["threshold"] > 0 and m["validation"]["false_alarm_rate"] < 0.01
    dev, s = next(iter(m["stats"].items()))
    det = AEDetector()
    assert det.score(dev, s["t_mean"], s["h_mean"]) < m["threshold"]  # a normal reading
    assert det.score(dev, s["t_mean"] + 8 * s["t_std"], s["h_mean"]) > m["threshold"]  # sudden jump
    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    assert not det.load(str(bad))["loaded"] and det.error  # bad file: no crash, error shown
    assert not det.load(str(tmp_path / "missing.json"))["loaded"]


def test_autoencoder_endpoint(fresh):
    st = fresh.get("/api/ml/autoencoder").json()
    assert st["loaded"] and st["framework"] in ("mindspore", "numpy") and st["devices"]


