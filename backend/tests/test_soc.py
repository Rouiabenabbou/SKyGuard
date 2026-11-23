"""v2.0 SOC: rule catalogue + switches, alert enrichment and triage, escalation, evidence, overview metrics."""
import time

from app import auth, config, soc
from app.models import AlertTriage, Incident, NetworkEvent, RuleSetting, SecurityAlert

from tests.conftest import run


def login(client, user, password):
    r = client.post("/api/auth/login", json={"username": user, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_rule_catalog_has_mitre_and_tests(fresh):
    rules = fresh.get("/api/soc/rules").json()["rules"]
    assert len(rules) == 21 and len({r["id"] for r in rules}) == 21
    flood = next(r for r in rules if r["alert_type"] == "excessive_message_rate")
    assert flood["mitre"]["id"] == "T1498" and flood["enabled"] and flood["test_attack"] == "excessive-traffic"
    assert all(r["explanation"] and r["logic"] for r in rules)


def test_disabled_rule_does_not_fire(fresh, db):
    from app.detection_engine import detector
    assert fresh.put("/api/soc/rules/CS-002", json={"enabled": False}).status_code == 200
    try:
        assert run(detector.unauthorized_device(db, "ROGUE-1")) is None
        assert db.query(SecurityAlert).filter(SecurityAlert.device_id == "ROGUE-1").count() == 0
        assert fresh.post("/api/soc/rules/CS-002/test").status_code == 409
    finally:
        fresh.put("/api/soc/rules/CS-002", json={"enabled": True})
    run(detector.unauthorized_device(db, "ROGUE-1"))
    assert db.query(SecurityAlert).filter(SecurityAlert.device_id == "ROGUE-1").count() == 1
    db.query(RuleSetting).delete()
    db.commit()


def test_rule_test_runs_simulated_attack(fresh):
    r = fresh.post("/api/soc/rules/CS-002/test")
    assert r.status_code == 200 and r.json()["source"] == "simulation"
    deadline = time.time() + 8
    while time.time() < deadline:
        hits = fresh.get("/api/soc/alerts?rule_id=CS-002").json()["alerts"]
        if hits:
            break
        time.sleep(0.3)
    assert hits and hits[0]["device_id"] == "IOT-999" and hits[0]["mitre"]["id"] == "T1200"
    assert fresh.post("/api/soc/rules/CS-007/test").status_code == 400  # network faults have no attack test


def test_alert_triage_and_escalation(fresh, db):
    a = SecurityAlert(device_id="IOT-002", alert_type="excessive_message_rate", severity="high", description="flood")
    b = SecurityAlert(device_id="IOT-002", alert_type="suspicious_connections", severity="high", description="storm")
    db.add_all([a, b])
    db.commit()
    listed = {x["id"]: x for x in fresh.get("/api/soc/alerts?status=open").json()["alerts"]}
    assert listed[a.id]["state"] == "new" and listed[a.id]["confidence"] == 0.85 and listed[a.id]["source"] == "simulation"
    assert listed[a.id]["correlation"] and listed[a.id]["correlation"] == listed[b.id]["correlation"]
    r = fresh.post(f"/api/soc/alerts/{a.id}/action", json={"action": "acknowledge"})
    assert r.status_code == 200 and r.json()["alert"]["state"] == "acknowledged"
    assert fresh.post(f"/api/soc/alerts/{a.id}/action", json={"action": "assign", "assignee": "nobody-here"}).status_code == 400
    fresh.post(f"/api/soc/alerts/{a.id}/action", json={"action": "assign", "assignee": "operator"})
    r = fresh.post(f"/api/soc/alerts/{a.id}/action", json={"action": "escalate", "note": "looks like a botnet"}).json()
    assert r["incident_id"] and r["alert"]["state"] == "escalated"
    assert db.get(Incident, r["incident_id"]).alert_id == a.id
    d = fresh.get(f"/api/soc/alerts/{a.id}").json()
    assert [x["action"] for x in d["activity"]] == ["acknowledge", "assign", "escalate"]
    assert any(x["id"] == b.id for x in d["evidence"]["related_alerts"])
    assert d["incidents"] and d["rule"]["id"] == "CS-001"
    r = fresh.post(f"/api/soc/alerts/{a.id}/action", json={"action": "close", "note": "contained"}).json()
    assert r["alert"]["status"] == "resolved" and r["alert"]["state"] == "closed"
    assert fresh.get("/api/soc/alerts?q=T1498").json()["count"] >= 1


def test_overview_metrics(fresh, db):
    from datetime import timedelta
    from app.models import utcnow
    t = utcnow()
    db.add(NetworkEvent(event_type="attack_started", category="security", device_id="IOT-001", description="sim",
                        timestamp=t - timedelta(seconds=10)))
    db.add(SecurityAlert(device_id="IOT-001", alert_type="abnormal_sensor_value", severity="high", description="hot",
                         timestamp=t - timedelta(seconds=4)))
    db.commit()
    o = fresh.get("/api/soc/overview").json()
    assert o["mttd_seconds"] is not None and 5 <= o["mttd_seconds"] <= 7
    assert o["alerts"]["last_24h"] >= 1 and len(o["alerts"]["timeline"]) == 25
    assert o["detection"]["rules_total"] == 21 and o["devices"]["total"] >= 3
    assert o["mttr_minutes"] is None or o["mttr_minutes"] >= 0


def test_soc_permissions(fresh, client, monkeypatch):
    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    auth._failures.clear()
    v = login(client, "viewer", "Viewer@2026")
    assert client.get("/api/soc/rules", headers=v).status_code == 200
    assert client.put("/api/soc/rules/CS-001", headers=v, json={"enabled": False}).status_code == 403
    o = login(client, "operator", "Operator@2026")
    assert client.put("/api/soc/rules/CS-001", headers=o, json={"enabled": False}).status_code == 403
    f = login(client, "farm_admin", "Farm@2026")
    assert client.post("/api/soc/rules/CS-001/test", headers=f).status_code == 403
    ids = {a["device_id"] for a in client.get("/api/soc/alerts", headers=f).json()["alerts"]}
    assert ids <= {"IOT-003"}
    auth._failures.clear()
