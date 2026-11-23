"""v2.1 SOC stages 2-4: security events + network rules, hunting, threat intel, AI tools, incident workflow,
playbooks, approvals, SOC roles, two-factor login, hash-chained audit and the end-to-end demo."""
import time

import pytest

from app import attack_scenarios as sc, auth, config, mfa
from app.models import AuditLog, Ioc, SecurityAlert, SecurityEvent

from tests.conftest import run


def alerts_of(db, device_id, alert_type):
    db.expire_all()
    return db.query(SecurityAlert).filter(SecurityAlert.device_id == device_id, SecurityAlert.alert_type == alert_type).all()


@pytest.fixture()
def secured(fresh, monkeypatch):
    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    auth._failures.clear()
    yield fresh
    auth._failures.clear()


def login(client, user, password, code=None):
    r = client.post("/api/auth/login", json={"username": user, "password": password, **({"code": code} if code else {})})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_scenarios_trigger_network_rules(fresh, db):
    run(sc.mqtt_brute_force("IOT-002", None, attempts=6, delay=0))
    assert alerts_of(db, "IOT-002", "mqtt_bruteforce") and alerts_of(db, "IOT-002", "credential_compromise")
    run(sc.unauthorized_publish("IOT-002", None, delay=0))
    assert alerts_of(db, "IOT-002", "unauthorized_publish")
    run(sc.port_scan("IOT-001", None, delay=0))
    assert alerts_of(db, "IOT-001", "port_scan")
    run(sc.botnet_beaconing("IOT-003", None, beats=7, interval=0.4))
    assert alerts_of(db, "IOT-003", "c2_beaconing")
    assert alerts_of(db, "IOT-003", "threat_intel_match")  # 198.51.100.66 is a seeded demo IOC
    run(sc.data_exfiltration("IOT-003", None, delay=0))
    assert alerts_of(db, "IOT-003", "data_exfiltration")[0].severity == "critical"
    run(sc.g5_auth_attack("IOT-002", None, delay=0))
    assert alerts_of(db, "IOT-002", "5g_auth_anomaly")
    run(sc.config_tampering("IOT-001", None))
    assert alerts_of(db, "IOT-001", "unauthorized_config_change")
    run(sc.gnss_jamming("IOT-001", None, delay=0))
    jam = alerts_of(db, "IOT-001", "gnss_jamming")
    assert jam and jam[0].severity == "critical"  # IOT-001 and IOT-003 jammed together
    run(sc.gnss_spoofing("IOT-003", None, delay=0))
    assert alerts_of(db, "IOT-003", "gnss_spoofing")
    # every event carries its source, attackers use documentation addresses
    rows = db.query(SecurityEvent).all()
    assert rows and all(r.source == "simulation" for r in rows)
    assert all(r.src_ip is None or r.src_ip.startswith(("10.", "203.0.113.", "198.51.100.")) for r in rows)
    g = fresh.get("/api/soc/gnss").json()
    assert {d["device_id"] for d in g["devices"]} >= {"IOT-001", "IOT-003"} and g["alerts"]
    assert any(d["state"] == "jammed" for d in g["devices"])
    # rule catalogue has a test for each new rule, all known attacks
    from app.attack_simulator import ATTACKS
    rules = fresh.get("/api/soc/rules").json()["rules"]
    assert all(r["test_attack"] in ATTACKS for r in rules if r["test_attack"])


def test_threat_hunting(fresh, db):
    run(sc.mqtt_brute_force("IOT-002", None, attempts=5, delay=0, src="203.0.113.77"))
    r = fresh.get("/api/hunt/events", params={"q": "type:mqtt_auth_failure src:203.0.113.*", "hours": 1}).json()
    assert r["total"] == 5 and r["facets"]["src_ip"][0] == {"value": "203.0.113.77", "count": 5}
    assert sum(b["count"] for b in r["histogram"]) == 5
    assert fresh.get("/api/hunt/events", params={"q": "type:mqtt_connect -src:10.*"}).json()["total"] == 1
    assert fresh.get("/api/hunt/events", params={"q": '"bad user name"'}).json()["total"] == 5
    assert fresh.get("/api/hunt/events", params={"q": "nosuch:1"}).status_code == 400
    assert fresh.get("/api/hunt/events", params={"q": "source:lab"}).json()["total"] == 0
    csv = fresh.get("/api/hunt/export", params={"q": "src:203.0.113.77", "format": "csv"})
    assert csv.status_code == 200 and csv.text.count("\n") == 7  # header + 6 events
    js = fresh.get("/api/hunt/export", params={"q": "src:203.0.113.77", "format": "json"}).json()
    assert js["count"] == 6
    saved = fresh.post("/api/hunt/queries", json={"name": "BF", "query": "type:mqtt_auth_failure", "shared": True})
    assert saved.status_code == 201
    lst = fresh.get("/api/hunt/queries").json()
    assert any(q["name"] == "BF" for q in lst["queries"]) and lst["templates"]
    assert fresh.delete(f"/api/hunt/queries/{saved.json()['query']['id']}").status_code == 200
    # flows: one summary record per device
    from app import security_events
    security_events.note_message("IOT-001", 120, "builtin")
    security_events.note_message("IOT-001", 120, "builtin")
    assert run(security_events.flush_flows(db)) == 1
    flow = fresh.get("/api/hunt/events", params={"q": "category:flow device:IOT-001"}).json()["events"][0]
    assert flow["bytes"] == 240 and flow["details"]["messages"] == 2 and flow["dst_port"] == 1883


def test_threat_intel(fresh, db):
    r = fresh.post("/api/intel/iocs", json={"value": "203.0.113.200", "threat": "Test scanner", "confidence": 85})
    assert r.status_code == 201 and r.json()["ioc"]["kind"] == "ip"
    assert fresh.post("/api/intel/iocs", json={"value": "not an ioc!"}).status_code == 400
    run(sc.port_scan("IOT-001", None, delay=0, src="203.0.113.200"))
    hit = alerts_of(db, "IOT-001", "threat_intel_match")
    assert hit and hit[0].severity == "critical"
    look = fresh.get("/api/intel/lookup", params={"value": "203.0.113.200"}).json()
    assert look["verdict"] == "malicious" and look["local"] and "documentation" in look["external_skipped"]
    assert fresh.get("/api/intel/lookup", params={"value": "10.20.1.2"}).json()["external_skipped"].startswith("private")
    assert fresh.get("/api/intel/lookup", params={"value": "44d88612fea8a8f36de82e1278abb02f"}).json()["local"]
    providers = fresh.get("/api/intel/providers").json()["providers"]
    assert {p["id"] for p in providers} == {"virustotal", "abuseipdb", "otx"} and not any("key" in p for p in providers)
    iocs = fresh.get("/api/intel/iocs", params={"q": "203.0.113.200"}).json()["iocs"]
    assert iocs[0]["sightings_24h"] >= 24
    sight = fresh.get("/api/intel/sightings", params={"value": "203.0.113.200"}).json()
    assert sight["devices"] == ["IOT-001"] and sight["alerts"]
    ioc_id = iocs[0]["id"]
    assert fresh.put(f"/api/intel/iocs/{ioc_id}", json={"active": False}).json()["ioc"]["active"] is False
    assert fresh.delete(f"/api/intel/iocs/{ioc_id}").status_code == 200


def test_ai_analyst_cites_evidence_and_only_proposes(fresh, db):
    run(sc.botnet_beaconing("IOT-003", None, beats=7, interval=0.4))
    alert = alerts_of(db, "IOT-003", "c2_beaconing")[0]
    r = fresh.post("/api/ai/investigate", json={"alert_id": alert.id}).json()
    assert r["source"] == "offline"
    names = [c["tool"] for c in r["tool_calls"]]
    assert names[:3] == ["analyze_alert", "get_device_information", "correlate_events"] and "get_threat_intelligence" in names
    ids = {e["id"] for e in r["evidence"]}
    import re
    cited = set(re.findall(r"\[(E\d+)\]", r["answer"]))
    assert cited and cited <= ids
    assert "**MITRE ATT&CK**" in r["answer"] and "T1071.001" in r["answer"]
    tools = {a["tool"] for a in r["proposed_actions"]}
    assert tools == {"create_incident", "request_device_isolation"}
    # nothing was executed by the AI
    db.expire_all()
    from app.models import ApprovalRequest, Device, Incident
    assert db.get(Device, "IOT-003").security_status != "quarantined"
    assert db.query(Incident).filter(Incident.alert_id == alert.id).count() == 0
    assert db.query(ApprovalRequest).filter(ApprovalRequest.target == "IOT-003", ApprovalRequest.status == "pending").count() == 0
    assert fresh.post("/api/ai/tools/request_device_isolation", json={"device_id": "IOT-003"}).status_code == 403
    t = fresh.post("/api/ai/tools/get_threat_intelligence", json={"value": "198.51.100.66"}).json()
    assert t["verdict"] == "malicious" and t["evidence"]
    q = fresh.post("/api/ai/investigate", json={"question": "What did IOT-003 do?"}).json()
    assert q["tool_calls"][0]["tool"] == "search_security_events" and q["evidence"]
    assert fresh.get("/api/ai/investigations", params={"alert_id": alert.id}).json()["investigations"]


def test_incident_workflow_playbook_and_report(fresh, db):
    run(sc.mqtt_brute_force("IOT-002", None, attempts=5, delay=0, src="203.0.113.91"))
    alert = alerts_of(db, "IOT-002", "mqtt_bruteforce")[0]
    inc = fresh.post("/api/incidents", json={"alert_id": alert.id}).json()["incident"]
    w = fresh.get(f"/api/incidents/{inc['id']}/workflow").json()
    assert w["phase"] == "detection" and len(w["phases"]) == 7
    assert w["evidence"][0]["kind"] == "alert" and w["mitre"][0]["id"] == "T1110.001"
    assert "PB-02" in w["suggested_playbooks"]
    assert fresh.post(f"/api/incidents/{inc['id']}/phase", json={"phase": "containment"}).status_code == 409
    assert fresh.post(f"/api/incidents/{inc['id']}/phase", json={"phase": "triage"}).json()["phase"] == "triage"
    assert fresh.put(f"/api/incidents/{inc['id']}/mitre", json={"techniques": ["T1046", "bad"]}).status_code == 422
    m = fresh.put(f"/api/incidents/{inc['id']}/mitre", json={"techniques": ["T1046"]}).json()["mitre"]
    assert {x["id"] for x in m} == {"T1110.001", "T1046"}
    pb = fresh.post(f"/api/incidents/{inc['id']}/playbooks", json={"playbook_id": "PB-02"}).json()["run"]
    url = f"/api/incidents/{inc['id']}/playbooks/{pb['id']}/steps"
    assert fresh.post(f"{url}/intel", json={}).status_code == 409  # out of order
    r = fresh.post(f"{url}/evidence", json={}).json()
    assert r["run"]["next"] == "intel" and len(r["workflow"]["evidence"]) > 3
    r = fresh.post(f"{url}/intel", json={}).json()
    assert r["workflow"]["phase"] == "investigation"
    r = fresh.post(f"{url}/block", json={}).json()
    assert "203.0.113.91" in r["run"]["steps"][2]["note"]
    assert db.query(Ioc).filter(Ioc.value == "203.0.113.91").count() == 1
    assert fresh.post(f"{url}/lock", json={}).status_code == 422  # manual step needs a note
    fresh.post(f"{url}/lock", json={"note": "IOT-002 broker password rotated"})
    r = fresh.post(f"{url}/watch", json={}).json()
    assert r["run"]["steps"][4]["state"] in ("done", "failed")
    if r["run"]["steps"][4]["state"] == "failed":
        r = fresh.post(f"{url}/watch", json={"skip": True, "note": "alerts are from the attack itself"}).json()
    r = fresh.post(f"{url}/close", json={"note": "Brute force blocked."}).json()
    assert r["run"]["status"] == "completed" and r["workflow"]["phase"] == "closure"
    assert fresh.get(f"/api/incidents/{inc['id']}").json()["incident"]["status"] == "resolved"
    rep = fresh.get(f"/api/incidents/{inc['id']}/report").json()["markdown"]
    assert "T1110.001" in rep and "## Evidence" in rep and "PB-02" in rep and "simulated" in rep
    md = fresh.get(f"/api/incidents/{inc['id']}/report", params={"format": "md"})
    assert md.headers["content-disposition"].endswith('report.md"')


def test_soc_roles_and_approvals(secured, db):
    c = secured
    l1 = login(c, "analyst_l1", "AnalystL1@2026")
    l2 = login(c, "analyst_l2", "AnalystL2@2026")
    l3 = login(c, "analyst_l3", "AnalystL3@2026")
    mgr = login(c, "soc_manager", "Manager@2026")
    op = login(c, "operator", "Operator@2026")
    me = c.get("/api/auth/me", headers=l1).json()["user"]
    assert me["role"] == "soc_l1" and "triage" in me["permissions"] and "contain" not in me["permissions"]
    run(sc.port_scan("IOT-001", None, delay=0, src="203.0.113.150"))
    alert = alerts_of(db, "IOT-001", "port_scan")[0]
    assert c.post(f"/api/soc/alerts/{alert.id}/action", headers=l1, json={"action": "acknowledge"}).status_code == 200
    r = c.post("/api/devices/IOT-001/quarantine", headers=l2)
    assert r.status_code == 403 and "Approvals" in r.json()["detail"]
    assert c.post("/api/devices/IOT-001/quarantine", headers=l1).status_code == 403
    assert c.post("/api/simulation/attack/port-scan", headers=l1).status_code == 403
    assert c.post("/api/approvals", headers=l1, json={"action": "isolate_device", "target": "IOT-001"}).status_code == 403
    req = c.post("/api/approvals", headers=l2, json={"action": "isolate_device", "target": "IOT-001", "reason": "scan",
                                                      "alert_id": alert.id}).json()["approval"]
    assert req["status"] == "pending" and req["requested_by"] == "analyst_l2"
    assert c.post(f"/api/approvals/{req['id']}/approve", headers=l2, json={}).status_code == 403
    ok = c.post(f"/api/approvals/{req['id']}/approve", headers=l3, json={"note": "confirmed"}).json()["approval"]
    assert ok["status"] == "executed" and ok["decided_by"] == "analyst_l3"
    db.expire_all()
    from app.models import Device
    assert db.get(Device, "IOT-001").security_status == "quarantined"
    assert c.post(f"/api/approvals/{req['id']}/approve", headers=l3, json={}).status_code == 409
    rel = c.post("/api/approvals", headers=l2, json={"action": "release_device", "target": "IOT-001"}).json()["approval"]
    assert c.post(f"/api/approvals/{rel['id']}/reject", headers=mgr, json={"note": "not yet"}).json()["approval"]["status"] == "rejected"
    # detection rules: SOC manager yes, operator (v1.1 role) no
    assert c.put("/api/soc/rules/CS-013", headers=mgr, json={"enabled": True}).status_code == 200
    assert c.put("/api/soc/rules/CS-013", headers=op, json={"enabled": True}).status_code == 403
    assert c.post("/api/devices/IOT-001/release", headers=op).status_code == 200
    roles = c.get("/api/auth/roles", headers=l1).json()["roles"]
    assert [r["id"] for r in roles][:2] == ["viewer", "soc_l1"]


def test_two_person_rule(fresh, monkeypatch):
    monkeypatch.setattr(config, "APPROVAL_TWO_PERSON", True)
    req = fresh.post("/api/approvals", json={"action": "isolate_device", "target": "IOT-002"}).json()["approval"]
    r = fresh.post(f"/api/approvals/{req['id']}/approve", json={})
    assert r.status_code == 409 and "Two-person" in r.json()["detail"]
    fresh.post(f"/api/approvals/{req['id']}/reject", json={})


def test_two_factor_login(secured, db):
    c = secured
    h = login(c, "analyst_l3", "AnalystL3@2026")
    setup = c.post("/api/auth/mfa/setup", headers=h).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/") and len(setup["secret"]) >= 32
    assert c.post("/api/auth/mfa/enable", headers=h, json={"code": "000000"}).status_code == 400
    step = mfa.current_step()
    assert c.post("/api/auth/mfa/enable", headers=h, json={"code": mfa.code_at(setup["secret"], step)}).json()["enabled"]
    r = c.post("/api/auth/login", json={"username": "analyst_l3", "password": "AnalystL3@2026"}).json()
    assert r["mfa_required"] and r["token"] is None
    assert c.post("/api/auth/login", json={"username": "analyst_l3", "password": "AnalystL3@2026", "code": "123456"}).status_code == 401
    # the code used to enable is spent; the next step's code works once
    code = mfa.code_at(setup["secret"], step + 1)
    h2 = login(c, "analyst_l3", "AnalystL3@2026", code)
    assert c.get("/api/auth/me", headers=h2).json()["user"]["mfa_enabled"]
    assert c.post("/api/auth/login", json={"username": "analyst_l3", "password": "AnalystL3@2026", "code": code}).status_code == 401
    # approving a containment needs a fresh code from an approver who has two-factor on
    req = c.post("/api/approvals", headers=h2, json={"action": "isolate_device", "target": "IOT-003"}).json()["approval"]
    assert c.post(f"/api/approvals/{req['id']}/approve", headers=h2, json={}).status_code == 401
    admin = login(c, "admin", "Admin@2026")
    assert c.delete("/api/auth/users/analyst_l3/mfa", headers=admin).status_code == 200
    assert c.post(f"/api/approvals/{req['id']}/reject", headers=h2, json={}).status_code == 200
    auth._failures.clear()


def test_mfa_required_role(secured, monkeypatch):
    monkeypatch.setattr(config, "MFA_REQUIRED_ROLES", ["soc_manager"])
    h = login(secured, "soc_manager", "Manager@2026")
    r = secured.get("/api/devices", headers=h)
    assert r.status_code == 403 and "Two-factor" in r.json()["detail"]
    assert secured.get("/api/auth/me", headers=h).json()["user"]["mfa_required"]
    assert secured.post("/api/auth/mfa/setup", headers=h).status_code == 200


def test_audit_hash_chain(secured, db):
    c = secured
    admin = login(c, "admin", "Admin@2026")
    c.post("/api/simulation/pause", headers=admin)
    v = c.get("/api/audit/verify", headers=admin).json()
    assert v["ok"] and v["checked"] == v["total"] > 0
    row = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    old = row.username
    row.username = "someone-else"
    db.commit()
    v = c.get("/api/audit/verify", headers=admin).json()
    assert not v["ok"] and v["broken_at"] == row.id and "modified" in v["problem"]
    row.username = old
    db.commit()
    assert c.get("/api/audit/verify", headers=admin).json()["ok"]


def test_end_to_end_demo(fresh, db):
    r = fresh.post("/api/soc/demo/start")
    assert r.status_code == 201
    assert fresh.post("/api/soc/demo/start").status_code == 409
    deadline = time.time() + 40
    run_ = None
    while time.time() < deadline:
        run_ = fresh.get("/api/soc/demo").json()["run"]
        if run_["status"] in ("waiting", "failed", "completed"):
            break
        time.sleep(0.3)
    assert run_["status"] == "waiting", run_
    steps = {s["id"]: s for s in run_["steps"]}
    assert steps["detection"]["state"] == "done" and steps["ai"]["state"] == "done"
    fresh.post(f"/api/approvals/{run_['approval_id']}/approve", json={"note": "go"})
    while time.time() < deadline:
        run_ = fresh.get("/api/soc/demo").json()["run"]
        if run_["status"] in ("failed", "completed"):
            break
        time.sleep(0.3)
    assert run_["status"] == "completed", run_
    w = fresh.get(f"/api/incidents/{run_['incident_id']}/workflow").json()
    assert w["phase"] == "closure" and w["containment_executed"] and w["ai"]
    kinds = {e["kind"] for e in w["evidence"]}
    assert {"alert", "ai_analysis", "approval", "ioc"} <= kinds
    rep = fresh.get(f"/api/incidents/{run_['incident_id']}/report").json()["markdown"]
    assert "approved by" not in rep or "executed" in rep
