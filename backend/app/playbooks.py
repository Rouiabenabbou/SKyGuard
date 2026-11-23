"""
v2.1 (SOC stage 4): response playbooks.

A playbook is an ordered checklist for one kind of incident. Each step is one of:
  auto      the system does it when the analyst presses Run (collect evidence, threat intel, block an address)
  approval  creates an approval request; the step is done when someone with approval rights approved it
            and the (simulated) action ran
  check     the system verifies a condition (device isolated, no new alerts)
  manual    a person does it outside the system and confirms it with a note
Running a step also moves the incident to the step's phase (never backwards).
Steps run in order. Every step is written to the incident timeline.
"""
import json
from datetime import timedelta

from sqlalchemy.orm import Session

from app import intel, soc
from app.incident_workflow import ORDER, WorkflowError, add_evidence, alerts_of, note, phase_row, request_approval, set_phase
from app.models import ApprovalRequest, Device, Incident, PlaybookRun, SecurityAlert, SecurityEvent, utcnow
from app.security_events import is_external


def S(id_, title, kind, phase, action=None, help_=""):
    return {"id": id_, "title": title, "kind": kind, "phase": phase, "action": action, "help": help_}


PLAYBOOKS = {
    "PB-01": {
        "name": "Compromised IoT device",
        "description": "Malware, a stolen account or tampering on one device: isolate it, clean it, bring it back.",
        "applies_to": ["c2_beaconing", "data_exfiltration", "threat_intel_match", "credential_compromise",
                       "excessive_message_rate", "device_id_spoofing", "unauthorized_config_change", "ml_anomaly"],
        "steps": [
            S("evidence", "Collect evidence (alerts and security events of the device)", "auto", "triage", "collect_evidence"),
            S("intel", "Enrich the external addresses with threat intelligence", "auto", "investigation", "enrich"),
            S("isolate", "Isolate the device (needs approval)", "approval", "containment", "request_isolation"),
            S("verify", "Check that the device is isolated", "check", "containment", "verify_isolated"),
            S("clean", "Rotate the device's MQTT password and re-flash its firmware", "manual", "eradication", None,
              "Outside this system: new broker credentials, firmware from the trusted image."),
            S("block", "Add the attacker addresses to the IOC list", "auto", "eradication", "block_iocs"),
            S("release", "Release the device (needs approval)", "approval", "recovery", "request_release"),
            S("watch", "No new alert on the device for 2 minutes", "check", "recovery", "verify_quiet"),
            S("close", "Close with a resolution summary", "manual", "closure", "close"),
        ],
    },
    "PB-02": {
        "name": "Credential attack (MQTT / 5G)",
        "description": "Password guessing on the broker, abuse of a device account, or 5G authentication attacks.",
        "applies_to": ["mqtt_bruteforce", "suspicious_connections", "5g_auth_anomaly", "unauthorized_publish"],
        "steps": [
            S("evidence", "Collect evidence", "auto", "triage", "collect_evidence"),
            S("intel", "Look up the attacking addresses", "auto", "investigation", "enrich"),
            S("block", "Block the attacking addresses (IOC list)", "auto", "containment", "block_iocs"),
            S("lock", "Rotate the targeted account (broker password / SIM keys)", "manual", "eradication", None,
              "Broker: change the device password and ACL. 5G: ask the operator to re-issue the SIM keys."),
            S("watch", "No new alert on the device for 2 minutes", "check", "recovery", "verify_quiet"),
            S("close", "Close with a resolution summary", "manual", "closure", "close"),
        ],
    },
    "PB-03": {
        "name": "Reconnaissance (scan)",
        "description": "Someone maps the network before attacking.",
        "applies_to": ["port_scan", "unauthorized_device"],
        "steps": [
            S("evidence", "Collect evidence", "auto", "triage", "collect_evidence"),
            S("intel", "Look up the scanning address", "auto", "investigation", "enrich"),
            S("block", "Block the scanning address (IOC list)", "auto", "containment", "block_iocs"),
            S("harden", "Close the services that answered (only MQTT should be open)", "manual", "eradication"),
            S("watch", "No new alert on the device for 2 minutes", "check", "recovery", "verify_quiet"),
            S("close", "Close with a resolution summary", "manual", "closure", "close"),
        ],
    },
    "PB-04": {
        "name": "GNSS interference",
        "description": "Jamming or spoofing of the satellite terminals' position and time.",
        "applies_to": ["gnss_jamming", "gnss_spoofing"],
        "steps": [
            S("evidence", "Collect evidence (GNSS samples)", "auto", "triage", "collect_evidence"),
            S("scope", "Check which terminals are affected together (Satellite & 5G page, 3D twin)", "manual", "investigation"),
            S("fallback", "Use 5G / hold-over time and the backup path for affected terminals", "manual", "containment"),
            S("report", "Report the interference to the satellite operator and the spectrum regulator", "manual", "eradication"),
            S("watch", "No new alert on the device for 2 minutes", "check", "recovery", "verify_quiet"),
            S("close", "Close with a resolution summary", "manual", "closure", "close"),
        ],
    },
    "PB-05": {
        "name": "Generic alert",
        "description": "Basic investigation for any alert.",
        "applies_to": [],
        "steps": [
            S("evidence", "Collect evidence", "auto", "triage", "collect_evidence"),
            S("intel", "Threat intelligence on external addresses", "auto", "investigation", "enrich"),
            S("decide", "Decide: false positive, or containment needed?", "manual", "investigation"),
            S("close", "Close with a resolution summary", "manual", "closure", "close"),
        ],
    },
}


def catalog() -> list[dict]:
    return [{"id": k, **v} for k, v in PLAYBOOKS.items()]


def suggest(alert_types: list[str]) -> list[str]:
    out = [k for k, v in PLAYBOOKS.items() if set(v["applies_to"]) & set(alert_types)]
    return out or ["PB-05"]


def view(db: Session, run: PlaybookRun) -> dict:
    pb = PLAYBOOKS[run.playbook_id]
    states = {s["id"]: s for s in json.loads(run.steps or "[]")}
    _refresh_waiting(db, run, states)
    steps = []
    nxt = None
    for s in pb["steps"]:
        st = states.get(s["id"], {"state": "pending"})
        if nxt is None and st["state"] not in ("done", "skipped"):
            nxt = s["id"]
        steps.append({**s, **st, "state": st.get("state", "pending")})
    return {"id": run.id, "playbook_id": run.playbook_id, "name": pb["name"], "status": run.status, "next": nxt,
            "steps": steps, "started_by": run.started_by, "started_at": run.started_at.isoformat() + "Z",
            "finished_at": run.finished_at.isoformat() + "Z" if run.finished_at else None}


def _refresh_waiting(db: Session, run: PlaybookRun, states: dict) -> None:
    changed = False
    for sid, st in states.items():
        if st.get("state") == "waiting" and st.get("approval_id"):
            req = db.get(ApprovalRequest, st["approval_id"])
            if req and req.status == "executed":
                st.update(state="done", note=f"approval #{req.id} approved by {req.decided_by} and executed")
                changed = True
            elif req and req.status in ("rejected", "failed"):
                st.update(state="failed", note=f"approval #{req.id} {req.status}" + (f": {req.result}" if req.result else ""))
                changed = True
    if changed:
        run.steps = json.dumps(list(states.values()))
        db.commit()


def start(db: Session, inc: Incident, playbook_id: str, user: str) -> PlaybookRun:
    if playbook_id not in PLAYBOOKS:
        raise WorkflowError(f"Unknown playbook {playbook_id}", 404)
    if db.query(PlaybookRun).filter(PlaybookRun.incident_id == inc.id, PlaybookRun.playbook_id == playbook_id,
                                    PlaybookRun.status == "running").first():
        raise WorkflowError(f"{playbook_id} is already running on this incident.", 409)
    run = PlaybookRun(playbook_id=playbook_id, incident_id=inc.id, started_by=user,
                      steps=json.dumps([{"id": s["id"], "state": "pending"} for s in PLAYBOOKS[playbook_id]["steps"]]))
    db.add(run)
    note(db, inc, user, "playbook", f"Playbook {playbook_id} ({PLAYBOOKS[playbook_id]['name']}) started.")
    db.commit()
    return run


def _external_ips(db: Session, inc: Incident) -> list[str]:
    ips = []
    for e in _device_events(db, inc, minutes=60):
        for ip in (e.src_ip, e.dst_ip):
            if ip and is_external(ip) and ip not in ips:
                ips.append(ip)
    return ips[:5]


def _device_events(db: Session, inc: Incident, minutes: int = 30) -> list[SecurityEvent]:
    if not inc.device_id:
        return []
    t0 = min([a.timestamp for a in alerts_of(db, inc)] or [inc.created_at])
    return (db.query(SecurityEvent).filter(SecurityEvent.device_id == inc.device_id, SecurityEvent.category != "flow",
                                           SecurityEvent.timestamp >= t0 - timedelta(minutes=minutes),
                                           SecurityEvent.timestamp <= t0 + timedelta(minutes=minutes))
            .order_by(SecurityEvent.id).limit(200).all())


async def _do(db: Session, inc: Incident, action: str | None, user: str, text: str) -> tuple[str, str, int | None]:
    """Returns (state, note, approval_id)."""
    if action is None:
        if not text.strip():
            raise WorkflowError("Confirm a manual step with a short note (what was done).", 422)
        return "done", text.strip(), None
    if action == "collect_evidence":
        n = 0
        for a in alerts_of(db, inc):
            r = soc.enrich(db, [a])[0]
            add_evidence(db, inc, "alert", str(a.id), f"Alert #{a.id} {r['rule_id'] or ''} {r['rule_name']}: {a.description}",
                         {"severity": a.severity, "timestamp": r["timestamp"]}, user)
            n += 1
        if inc.device_id:
            t0 = min([a.timestamp for a in alerts_of(db, inc)] or [inc.created_at])
            for a in db.query(SecurityAlert).filter(SecurityAlert.device_id == inc.device_id,
                                                    SecurityAlert.timestamp >= t0 - timedelta(minutes=60),
                                                    SecurityAlert.timestamp <= t0 + timedelta(minutes=60)).limit(20):
                add_evidence(db, inc, "alert", str(a.id), f"Alert #{a.id} {a.alert_type}: {a.description}", {"severity": a.severity}, user)
                n += 1
            for e in _device_events(db, inc)[:30]:
                add_evidence(db, inc, "security_event", str(e.id),
                             f"Event #{e.id} {e.event_type} {e.src_ip or ''} → {e.dst_ip or ''}{':' + str(e.dst_port) if e.dst_port else ''} {e.message}",
                             e.to_dict(), user)
                n += 1
        return "done", f"{n} items attached as evidence", None
    if action == "enrich":
        ips = _external_ips(db, inc)
        if not ips:
            return "done", "no external address in the device's events", None
        out = []
        for ip in ips:
            res = await intel.lookup(db, ip)
            out.append(f"{ip}: {res['verdict']}")
            add_evidence(db, inc, "intel", ip, f"Threat intel {ip}: {res['verdict']}"
                         + (f" (local IOC: {res['local'][0]['threat']})" if res["local"] else "")
                         + (f" · external: {res['external_skipped']}" if res.get("external_skipped") else ""), res, user)
        return "done", "; ".join(out), None
    if action in ("request_isolation", "request_release"):
        if not inc.device_id:
            raise WorkflowError("This incident has no device.", 409)
        req = await request_approval(db, "isolate_device" if action == "request_isolation" else "release_device", inc.device_id,
                                     f"playbook on incident #{inc.id}" + (f": {text}" if text else ""), user, "playbook", inc.id, inc.alert_id)
        return "waiting", f"approval #{req.id} waiting", req.id
    if action == "verify_isolated":
        d = db.get(Device, inc.device_id) if inc.device_id else None
        if d and d.security_status == "quarantined":
            return "done", f"{d.device_id} is quarantined (simulated isolation)", None
        return "failed", "the device is not quarantined yet", None
    if action == "block_iocs":
        ips = _external_ips(db, inc)
        for ip in ips:
            intel.add_ioc(db, "ip", ip, f"Seen in incident #{inc.id}", 70, "incident", "playbook",
                          f"Added by playbook on incident #{inc.id}.", user, days=30)
        return "done", ("added to IOC list: " + ", ".join(ips)) if ips else "no external address to block", None
    if action == "verify_quiet":
        if not inc.device_id:
            return "done", "network-level incident", None
        n = db.query(SecurityAlert).filter(SecurityAlert.device_id == inc.device_id,
                                           SecurityAlert.timestamp >= utcnow() - timedelta(minutes=2)).count()
        return ("done", "no new alert in the last 2 minutes", None) if n == 0 else ("failed", f"{n} alert(s) in the last 2 minutes", None)
    if action == "close":
        if not text.strip():
            raise WorkflowError("Write a resolution summary.", 422)
        return "done", text.strip(), None
    raise WorkflowError(f"Unknown step action {action}")


async def run_step(db: Session, run: PlaybookRun, step_id: str, user: str, text: str = "", skip: bool = False) -> PlaybookRun:
    if run.status != "running":
        raise WorkflowError("This playbook run is finished.", 409)
    inc = db.get(Incident, run.incident_id)
    v = view(db, run)
    if v["next"] != step_id:
        raise WorkflowError(f"Run the steps in order: next is '{v['next']}'.", 409)
    step = next(s for s in PLAYBOOKS[run.playbook_id]["steps"] if s["id"] == step_id)
    states = {s["id"]: s for s in json.loads(run.steps)}
    if states[step_id].get("state") == "waiting":
        raise WorkflowError("Waiting for the approval of this step (see Approvals).", 409)
    if skip:
        if not text.strip():
            raise WorkflowError("Say why the step is skipped.", 422)
        state, msg, appr = "skipped", text.strip(), None
    else:
        # move the incident forward to the step's phase first (one phase at a time)
        cur = phase_row(db, inc).phase
        while ORDER.index(cur) < ORDER.index(step["phase"]) and step["phase"] != "closure":
            nxt = ORDER[ORDER.index(cur) + 1]
            set_phase(db, inc, nxt, user, f"(playbook {run.playbook_id})" if not (cur == "containment") else
                      f"(playbook {run.playbook_id}: containment step done)")
            cur = nxt
        state, msg, appr = await _do(db, inc, step["action"], user, text)
        if step["action"] == "close" and state == "done":
            while phase_row(db, inc).phase != "closure":
                cur = phase_row(db, inc).phase
                set_phase(db, inc, ORDER[ORDER.index(cur) + 1], user, msg)
    states[step_id] = {"id": step_id, "state": state, "by": user, "at": utcnow().isoformat() + "Z", "note": msg,
                       **({"approval_id": appr} if appr else {})}
    run.steps = json.dumps(list(states.values()))
    note(db, inc, user, "playbook", f"{run.playbook_id} · {step['title']}: {state}" + (f" ({msg})" if msg else ""))
    if all(states.get(s["id"], {}).get("state") in ("done", "skipped") for s in PLAYBOOKS[run.playbook_id]["steps"]):
        run.status, run.finished_at = "completed", utcnow()
    db.commit()
    return run
