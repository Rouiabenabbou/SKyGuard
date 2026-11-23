"""
v2.1 (SOC stage 4): the end-to-end demo scenario.

  1 simulated MQTT attack   brute force on IOT-002's broker account, a successful login, rogue publishes
  2 ingestion               the security events are stored (Threat Hunting)
  3 detection               rules CS-011 / CS-021 / CS-014 raise alerts on their own
  4 incident                an incident is opened from the most severe alert, alerts attached as evidence
  5 AI analysis             the AI SOC analyst runs its read tools and cites the evidence
  6 approval                isolation of IOT-002 is requested: the run WAITS for a person to approve it
  7 containment             the approved (simulated) quarantine runs
  8 eradication             attacker address added to the IOC list; credential rotation noted (simulated)
  9 recovery                the device is released and watched
 10 closure + report        resolution summary and the incident report

Everything is simulated inside the project. The only human step is the approval
(Incident page or Approvals), so the separation between AI advice and human
decision is visible in the demo.
"""
import asyncio
import json
import time
from datetime import timedelta

from app import intel
from app.database import SessionLocal
from app.models import ApprovalRequest, DemoRun, Device, Incident, IncidentNote, SecurityAlert, SecurityEvent, utcnow
from app.websocket_manager import manager

TARGET = "IOT-002"
STEPS = [
    ("attack", "Simulated MQTT attack"), ("ingestion", "Ingestion into the security event store"),
    ("detection", "Detection by the rules"), ("incident", "Incident opened"), ("ai", "AI SOC analyst"),
    ("approval", "Human approval of the containment"), ("containment", "Containment (simulated isolation)"),
    ("eradication", "Eradication"), ("recovery", "Recovery"), ("closure", "Closure and report"),
]
_tasks: set = set()


def view(run: DemoRun) -> dict:
    return {"id": run.id, "status": run.status, "steps": json.loads(run.steps), "incident_id": run.incident_id,
            "approval_id": run.approval_id, "started_by": run.started_by, "started_at": run.started_at.isoformat() + "Z",
            "finished_at": run.finished_at.isoformat() + "Z" if run.finished_at else None, "target": TARGET}


def _set(db, run: DemoRun, step: str, state: str, text: str = "", **extra) -> None:
    steps = json.loads(run.steps)
    for s in steps:
        if s["id"] == step:
            s.update(state=state, text=text, at=utcnow().isoformat() + "Z", **extra)
    run.steps = json.dumps(steps)
    db.commit()


async def _push(run: DemoRun) -> None:
    await manager.broadcast("demo", view(run))


def create(db, user: str) -> DemoRun:
    if db.get(Device, TARGET) is None:
        raise ValueError(f"The demo needs device {TARGET}.")
    if db.query(DemoRun).filter(DemoRun.status.in_(("running", "waiting"))).first():
        raise ValueError("A demo run is already in progress.")
    run = DemoRun(started_by=user, steps=json.dumps([{"id": i, "label": l, "state": "pending", "text": ""} for i, l in STEPS]))
    db.add(run)
    db.commit()
    task = asyncio.create_task(execute(run.id, user))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return run


async def execute(run_id: int, user: str, approval_timeout: float = 900) -> None:
    from app import ai_tools, incident_workflow as wf, soc
    from app.attack_scenarios import mqtt_brute_force, unauthorized_publish
    from app.quarantine_service import quarantine
    from app.security_events import attacker_ip
    from app.simulation_controller import controller

    with SessionLocal() as db:
        run = db.get(DemoRun, run_id)
        try:
            t0 = utcnow() - timedelta(seconds=1)
            src = attacker_ip(f"demo-{run_id}-{time.time()}")
            device = db.get(Device, TARGET)
            if device.security_status == "quarantined":
                await quarantine.release(db, TARGET)
            _set(db, run, "attack", "running", f"Attacker {src} (documentation address) targets {TARGET}")
            await _push(run)
            await mqtt_brute_force(TARGET, controller.session_id, attempts=7, delay=0.25, src=src)
            await unauthorized_publish(TARGET, controller.session_id, src=src)
            _set(db, run, "attack", "done", f"brute force + login + rogue publish from {src}")

            n = db.query(SecurityEvent).filter(SecurityEvent.timestamp >= t0, SecurityEvent.src_ip == src).count()
            _set(db, run, "ingestion", "done", f"{n} security events stored", link=f"#hunting?q=src:{src}")
            await _push(run)

            want = {"mqtt_bruteforce", "credential_compromise", "unauthorized_publish"}
            alerts = []
            for _ in range(40):
                alerts = db.query(SecurityAlert).filter(SecurityAlert.device_id == TARGET, SecurityAlert.timestamp >= t0,
                                                        SecurityAlert.alert_type.in_(want)).all()
                if {a.alert_type for a in alerts} >= {"mqtt_bruteforce"} and len(alerts) >= 2:
                    break
                await asyncio.sleep(0.5)
                db.expire_all()
            if not alerts:
                raise RuntimeError("no alert was raised (are rules CS-011 / CS-014 / CS-021 switched on?)")
            rules = sorted({soc.RULES_BY_TYPE[a.alert_type]["id"] for a in alerts})
            _set(db, run, "detection", "done", f"{len(alerts)} alerts: " + ", ".join(f"#{a.id} {a.alert_type}" for a in alerts)
                 + f" (rules {', '.join(rules)})", link=f"#alerts/{alerts[0].id}")
            await _push(run)

            rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            main = sorted(alerts, key=lambda a: (rank[a.severity], a.id))[0]
            inc = Incident(title=f"Demo: MQTT account takeover on {TARGET}", device_id=TARGET, alert_id=main.id,
                           severity=main.severity, created_by=user, assignee=user)
            db.add(inc)
            db.flush()
            db.add(IncidentNote(incident_id=inc.id, username="demo", kind="created", text=f"Opened by the demo from alert #{main.id}."))
            for a in alerts:
                wf.evidence_from_ref(db, inc, "alert", str(a.id), "demo")
            wf.set_phase(db, inc, "triage", "demo", "Alerts confirmed by the rules.")
            db.commit()
            run.incident_id = inc.id
            _set(db, run, "incident", "done", f"incident #{inc.id} from alert #{main.id}", link=f"#incidents/{inc.id}")
            await manager.broadcast("incident", inc.to_dict())
            await _push(run)

            _set(db, run, "ai", "running", "running the analyst tools")
            res = await ai_tools.investigate(db, "demo", incident_id=inc.id)
            wf.set_phase(db, inc, "investigation", "demo", f"AI analyst investigation #{res['id']} attached.")
            db.commit()
            _set(db, run, "ai", "done", f"{len(res['tool_calls'])} tool calls, {len(res['evidence'])} evidence items ({res['source']})",
                 link=f"#incidents/{inc.id}")
            await _push(run)

            req = await wf.request_approval(db, "isolate_device", TARGET, "Demo: account taken over, isolate before more commands",
                                            user, "demo", inc.id, main.id)
            run.approval_id, run.status = req.id, "waiting"
            _set(db, run, "approval", "waiting", f"approval #{req.id} waits for a person with approval rights",
                 link=f"#incidents/{inc.id}")
            await _push(run)
            deadline = time.time() + approval_timeout
            while True:
                db.expire_all()
                req = db.get(ApprovalRequest, req.id)
                if req.status in ("executed", "rejected", "failed") or time.time() > deadline:
                    break
                await asyncio.sleep(1)
            run.status = "running"
            if req.status != "executed":
                _set(db, run, "approval", "failed", f"approval #{req.id} {req.status if req.status != 'pending' else 'timed out'}")
                raise RuntimeError("containment was not approved; the incident stays open for the analysts")
            _set(db, run, "approval", "done", f"approved by {req.decided_by}")

            inc = db.get(Incident, inc.id)
            wf.set_phase(db, inc, "containment", "demo", f"Approval #{req.id} executed.")
            db.commit()
            _set(db, run, "containment", "done", f"{TARGET} quarantined (simulated isolation): {req.result}")
            await _push(run)

            intel.add_ioc(db, "ip", src, f"MQTT brute force (demo incident #{inc.id})", 80, "bruteforce,demo", "playbook",
                          f"Attacker address of demo run {run_id}.", "demo", days=1)
            wf.add_evidence(db, inc, "ioc", src, f"{src} added to the IOC list", {"value": src}, "demo")
            wf.set_phase(db, inc, "eradication", "demo", f"{src} blocked (IOC list). Simulated: {TARGET}'s broker password rotated.")
            db.commit()
            _set(db, run, "eradication", "done", f"{src} added to the IOC list; password rotation (simulated)")
            await _push(run)

            await asyncio.sleep(1)
            await quarantine.release(db, TARGET)
            inc = db.get(Incident, inc.id)
            wf.set_phase(db, inc, "recovery", "demo", f"{TARGET} released after the approved containment; watching for new alerts.")
            db.commit()
            await asyncio.sleep(2)
            again = db.query(SecurityAlert).filter(SecurityAlert.device_id == TARGET,
                                                   SecurityAlert.timestamp >= utcnow() - timedelta(seconds=2)).count()
            _set(db, run, "recovery", "done", f"{TARGET} released; {again} new alerts")
            await _push(run)

            inc = db.get(Incident, inc.id)
            wf.set_phase(db, inc, "closure", "demo", "Resolved: brute force blocked, account rotated, device back online. "
                         "Lesson: device accounts need unique strong passwords and broker rate limits.")
            db.commit()
            _set(db, run, "closure", "done", "incident resolved; report ready", link=f"/api/incidents/{inc.id}/report")
            run.status, run.finished_at = "completed", utcnow()
            db.commit()
            await manager.broadcast("incident", inc.to_dict())
            await _push(run)
        except Exception as exc:
            db.rollback()
            run = db.get(DemoRun, run_id)
            steps = json.loads(run.steps)
            for s in steps:
                if s["state"] in ("running", "waiting", "pending"):
                    s.update(state="failed", text=str(exc)[:300])
                    break
            run.steps = json.dumps(steps)
            run.status, run.finished_at = "failed", utcnow()
            db.commit()
            await _push(run)
