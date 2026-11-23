"""
v2.0 SOC endpoints (see app/soc.py).

GET  /api/soc/overview               SOC metrics from real rows (incidents, alerts, MTTD/MTTA/MTTR, ingestion)
GET  /api/soc/rules                  detection rule catalogue + on/off + hits
PUT  /api/soc/rules/{id}             {"enabled": false}                       (platform admin)
POST /api/soc/rules/{id}/test        run the rule's simulated test attack      (platform operator)
GET  /api/soc/alerts                 enriched alerts with filters and search
GET  /api/soc/alerts/{id}            one alert with evidence (events, readings, related alerts, incidents, history)
POST /api/soc/alerts/{id}/action     {"action": "acknowledge|assign|investigate|escalate|close|reopen|note", ...}
"""
import asyncio
from collections import Counter
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.security_events import is_lab
from app import soc, tenancy
from app.database import get_db
from app.event_log import log_event
from app.models import (AlertActivity, AlertTriage, Device, Incident, IncidentNote, NetworkEvent, SecurityAlert,
                        Telemetry, User, utcnow)
from app.simulation_controller import controller
from app.websocket_manager import manager

router = APIRouter(prefix="/api/soc", tags=["soc"])
SEV = ["critical", "high", "medium", "low"]


def _user(request: Request) -> str:
    user = getattr(request.state, "user", None)
    return user.username if user else "operator"


def _visible(q, column):
    hidden = tenancy.current_hidden()
    return q.filter(~column.in_(hidden)) if hidden else q


# ------------------------------------------------------------------ overview
@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    from app.mqtt_client import mqtt_service
    from app.network_simulator import network

    hidden = tenancy.current_hidden()
    now = utcnow()
    day = now - timedelta(hours=24)
    week = now - timedelta(days=7)

    incidents = [i for i in db.query(Incident) if not (i.device_id and i.device_id in hidden)]
    open_inc = [i for i in incidents if i.status != "resolved"]
    alerts_24 = [a for a in _visible(db.query(SecurityAlert), SecurityAlert.device_id).filter(SecurityAlert.timestamp >= day)
                 if a.device_id not in hidden]
    open_alerts = [a for a in _visible(db.query(SecurityAlert), SecurityAlert.device_id).filter(SecurityAlert.status == "open")]

    # MTTD: simulated attack start (event) -> first alert on the same device within 2 minutes
    starts = db.query(NetworkEvent).filter(NetworkEvent.event_type == "attack_started", NetworkEvent.timestamp >= week).all()
    pairs = []
    for e in starts:
        if not e.device_id or e.device_id in hidden:
            continue
        first = (db.query(SecurityAlert).filter(SecurityAlert.device_id == e.device_id, SecurityAlert.timestamp >= e.timestamp,
                                                SecurityAlert.timestamp <= e.timestamp + timedelta(minutes=2))
                 .order_by(SecurityAlert.timestamp).first())
        if first:
            pairs.append((e.timestamp, first.timestamp))
    mttd_s = [(b - a).total_seconds() for a, b in pairs]
    week_alerts = {a.id: a for a in _visible(db.query(SecurityAlert), SecurityAlert.device_id).filter(SecurityAlert.timestamp >= week)}
    triage = db.query(AlertTriage).filter(AlertTriage.alert_id.in_(list(week_alerts))).all() if week_alerts else []
    mtta = soc.avg_minutes((week_alerts[t.alert_id].timestamp, t.first_action_at) for t in triage if t.first_action_at)
    mttr = soc.avg_minutes((i.created_at, i.resolved_at) for i in incidents if i.resolved_at and i.created_at >= week)

    start = day.replace(minute=0, second=0, microsecond=0)
    hours = [{"t": (start + timedelta(hours=h)).isoformat() + "Z", **{s: 0 for s in SEV}} for h in range(25)]
    for a in alerts_24:
        i = int((a.timestamp - start).total_seconds() // 3600)
        if 0 <= i < 25 and a.severity in hours[i]:
            hours[i][a.severity] += 1

    devices = [d for d in db.query(Device) if d.device_id not in hidden]
    snap = network.latest or {}
    links = snap.get("links", [])
    nodes = snap.get("nodes", [])

    def seg(kind):
        ls = [l for l in links if l["link_type"] == kind]
        return {"total": len(ls), "online": sum(l["status"] == "online" for l in ls),
                "degraded": sum(l["status"] == "degraded" for l in ls), "offline": sum(l["status"] == "offline" for l in ls)}

    five = now - timedelta(minutes=5)
    hour = now - timedelta(hours=1)
    recent = _visible(db.query(Telemetry), Telemetry.device_id).filter(Telemetry.timestamp >= hour).all()
    last_reading = max((r.timestamp for r in recent), default=None)
    sources = Counter("lab" if is_lab(r.source) else "simulation" for r in recent)

    from app.ml_detector import ml_detector
    rules = soc.rule_catalog()
    enabled = sum(soc.rule_enabled(r["alert_type"]) for r in rules)
    last_alert = max((a.timestamp for a in alerts_24), default=None)

    return {
        "incidents": {"open": len(open_inc), "by_severity": {s: sum(i.severity == s for i in open_inc) for s in SEV},
                      "total": len(incidents)},
        "alerts": {"open": len(open_alerts), "last_24h": len(alerts_24),
                   "open_by_severity": {s: sum(a.severity == s for a in open_alerts) for s in SEV},
                   "timeline": hours},
        "mttd_seconds": round(sum(mttd_s) / len(mttd_s), 1) if mttd_s else None, "mttd_samples": len(mttd_s),
        "mtta_minutes": mtta, "mttr_minutes": mttr,
        "devices": {"total": len(devices), "online": sum(d.status == "online" for d in devices),
                    "suspicious": sum(d.security_status == "suspicious" for d in devices),
                    "quarantined": sum(d.security_status == "quarantined" for d in devices)},
        "network": {"availability": snap.get("availability", {}).get("current"), "satellite": seg("satellite"),
                    "5g": seg("5g"), "fiber": seg("fiber"),
                    "nodes_down": [n["node_id"] for n in nodes if n["node_type"] != "iot_device" and n["status"] != "online"]},
        "traffic": {"messages_last_hour": len(recent),
                    "messages_per_min": round(sum(r.timestamp >= five for r in recent) / 5, 1)},
        "top_targets": Counter(a.device_id for a in alerts_24 if a.device_id).most_common(5),
        "top_types": Counter(a.alert_type for a in alerts_24).most_common(5),
        "detection": {"rules_enabled": enabled, "rules_total": len(rules), "alerts_last_hour": sum(a.timestamp >= hour for a in alerts_24),
                      "last_alert": last_alert.isoformat() + "Z" if last_alert else None,
                      "ml": {"enabled": ml_detector.enabled, "trained": ml_detector.model is not None}},
        "ingestion": {"last_reading": last_reading.isoformat() + "Z" if last_reading else None,
                      "readings_last_5min": sum(r.timestamp >= five for r in recent),
                      "mqtt_connected": mqtt_service.connected if hasattr(mqtt_service, "connected") else False,
                      "sources_last_hour": dict(sources), "simulation_running": controller.running},
    }


# ------------------------------------------------------------------ rules
@router.get("/rules")
def rules(db: Session = Depends(get_db)):
    hidden = tenancy.current_hidden()
    day = utcnow() - timedelta(hours=24)
    rows = [a for a in db.query(SecurityAlert).filter(SecurityAlert.timestamp >= day) if a.device_id not in hidden]
    hits = Counter(a.alert_type for a in rows)
    last = {}
    for a in rows:
        last[a.alert_type] = max(last.get(a.alert_type, a.timestamp), a.timestamp)
    out = []
    for r in soc.rule_catalog():
        out.append({**r, "enabled": soc.rule_enabled(r["alert_type"]), "hits_24h": hits.get(r["alert_type"], 0),
                    "last_hit": last[r["alert_type"]].isoformat() + "Z" if r["alert_type"] in last else None})
    return {"rules": out}


class RuleIn(BaseModel):
    enabled: bool


@router.put("/rules/{rule_id}")
def set_rule(rule_id: str, body: RuleIn, request: Request, db: Session = Depends(get_db)):
    if rule_id not in {r["id"] for r in soc.rule_catalog()}:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    soc.set_rule(db, rule_id, body.enabled, _user(request))
    return {"rule_id": rule_id, "enabled": body.enabled}


@router.post("/rules/{rule_id}/test")
async def test_rule(rule_id: str, device_id: str | None = None):
    """Start the simulated attack that this rule should catch. Watch the Alert Center for the result."""
    from app.attack_simulator import ATTACKS
    from app.routes.simulation import _running_attacks

    rule = next((r for r in soc.rule_catalog() if r["id"] == rule_id), None)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    if not rule["test_attack"]:
        raise HTTPException(status_code=400, detail=f"{rule_id} has no simulated test (it fires on network faults or sensors).")
    if not soc.rule_enabled(rule["alert_type"]):
        raise HTTPException(status_code=409, detail=f"{rule_id} is switched off; switch it on to test it.")
    func, default = ATTACKS[rule["test_attack"]]
    target = (device_id or default).upper()
    task = asyncio.create_task(func(target, controller.session_id))
    _running_attacks.add(task)
    task.add_done_callback(_running_attacks.discard)
    return {"rule_id": rule_id, "attack": rule["test_attack"], "device_id": target, "source": "simulation",
            "message": f"Simulated {rule['test_attack']} started on {target}. Expect a {rule['alert_type']} alert."}


# ------------------------------------------------------------------ alerts
@router.get("/alerts")
def alerts(status: Literal["open", "resolved", "all"] = "all", severity: str | None = None, state: str | None = None,
           q: str | None = Query(default=None, max_length=100), device_id: str | None = None, rule_id: str | None = None,
           hours: int = Query(default=168, ge=1, le=24 * 365), limit: int = Query(default=200, ge=1, le=1000),
           source: str | None = Query(default=None, pattern="^(all|simulation|lab|production)$"),
           db: Session = Depends(get_db)):
    query = _visible(db.query(SecurityAlert), SecurityAlert.device_id).filter(SecurityAlert.timestamp >= soc.since(hours))
    if status != "all":
        query = query.filter(SecurityAlert.status == status)
    if severity:
        query = query.filter(SecurityAlert.severity.in_(severity.split(",")))
    if device_id:
        query = query.filter(SecurityAlert.device_id == device_id.upper())
    rows = query.order_by(SecurityAlert.id.desc()).limit(2000).all()
    rows = [a for a in rows if a.device_id not in tenancy.current_hidden()]
    out = soc.enrich(db, rows)
    if state:
        out = [a for a in out if a["state"] in state.split(",")]
    if rule_id:
        out = [a for a in out if a["rule_id"] == rule_id]
    if source and source != "all":  # v2.1 environment selector
        out = [a for a in out if a["source"] == source]
    if q:
        needle = q.lower()
        out = [a for a in out if needle in " ".join(str(a.get(k) or "") for k in
               ("id", "device_id", "alert_type", "description", "rule_id", "rule_name", "assignee")).lower()
               or (a["mitre"] and needle in (a["mitre"]["id"] + a["mitre"]["name"]).lower())]
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    counts = Counter(a["state"] for a in out)
    return {"count": len(out), "states": dict(counts), "alerts": out[:limit],
            "severity_rank": rank}


def _get_alert(db: Session, alert_id: int) -> SecurityAlert:
    a = db.get(SecurityAlert, alert_id)
    if a is None or a.device_id in tenancy.current_hidden():
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return a


def _detail(db: Session, a: SecurityAlert) -> dict:
    row = soc.enrich(db, [a])[0]
    rule = soc.RULES_BY_TYPE.get(a.alert_type)
    t0 = a.timestamp
    events, readings, related = [], [], []
    if a.device_id:
        events = (db.query(NetworkEvent).filter(NetworkEvent.device_id == a.device_id,
                                                NetworkEvent.timestamp >= t0 - timedelta(minutes=10),
                                                NetworkEvent.timestamp <= t0 + timedelta(minutes=5))
                  .order_by(NetworkEvent.timestamp).limit(40).all())
        readings = (db.query(Telemetry).filter(Telemetry.device_id == a.device_id,
                                               Telemetry.timestamp >= t0 - timedelta(minutes=5),
                                               Telemetry.timestamp <= t0 + timedelta(minutes=2))
                    .order_by(Telemetry.timestamp).limit(60).all())
        related = (db.query(SecurityAlert).filter(SecurityAlert.device_id == a.device_id, SecurityAlert.id != a.id,
                                                  SecurityAlert.timestamp >= t0 - timedelta(minutes=60),
                                                  SecurityAlert.timestamp <= t0 + timedelta(minutes=60))
                   .order_by(SecurityAlert.timestamp).limit(20).all())
    incidents = db.query(Incident).filter((Incident.alert_id == a.id) |
                                          ((Incident.device_id == a.device_id) & (Incident.created_at >= t0 - timedelta(hours=24)))
                                          if a.device_id else (Incident.alert_id == a.id)).all()
    device = db.get(Device, a.device_id) if a.device_id else None
    return {
        "alert": row, "rule": rule,
        "device": device.to_dict() if device else None,
        "evidence": {
            "events": [e.to_dict() for e in events],
            "readings": [{**r.to_dict(), "source_mode": "lab" if is_lab(r.source) else "simulation"} for r in readings],
            "related_alerts": soc.enrich(db, related),
        },
        "incidents": [i.to_dict() for i in incidents],
        "activity": [x.to_dict() for x in db.query(AlertActivity).filter(AlertActivity.alert_id == a.id).order_by(AlertActivity.id)],
    }


@router.get("/alerts/{alert_id}")
def alert_detail(alert_id: int, db: Session = Depends(get_db)):
    return _detail(db, _get_alert(db, alert_id))


class ActionIn(BaseModel):
    action: Literal["acknowledge", "assign", "investigate", "escalate", "close", "reopen", "note"]
    assignee: str | None = Field(default=None, max_length=64)
    note: str = Field(default="", max_length=2000)


STATE_OF = {"acknowledge": "acknowledged", "investigate": "investigating", "escalate": "escalated",
            "close": "closed", "reopen": "new"}


@router.post("/alerts/{alert_id}/action")
async def alert_action(alert_id: int, body: ActionIn, request: Request, db: Session = Depends(get_db)):
    a = _get_alert(db, alert_id)
    user = _user(request)
    t = db.get(AlertTriage, a.id) or AlertTriage(alert_id=a.id, state="closed" if a.status == "resolved" else "new")
    now = utcnow()
    text = body.note.strip()
    if body.action == "assign":
        name = (body.assignee or "").strip()
        if name and db.get(User, name) is None:
            raise HTTPException(status_code=400, detail=f"No user called {name}")
        t.assignee = name
        text = (f"Assigned to {name}. " if name else "Unassigned. ") + text
    elif body.action in STATE_OF:
        t.state = STATE_OF[body.action]
        if body.action in ("acknowledge", "investigate") and not t.assignee:
            t.assignee = user
    if body.action != "note" and t.first_action_at is None:
        t.first_action_at = now
    t.updated_by, t.updated_at = user, now
    db.merge(t)

    incident_id = None
    if body.action == "escalate":
        inc = db.query(Incident).filter(Incident.alert_id == a.id).first()
        if inc is None:
            rule = soc.RULES_BY_TYPE.get(a.alert_type)
            inc = Incident(title=f"{rule['name'] if rule else a.alert_type} on {a.device_id or 'network'}"[:160],
                           device_id=a.device_id, alert_id=a.id, severity=a.severity, created_by=user)
            db.add(inc)
            db.flush()
            db.add(IncidentNote(incident_id=inc.id, username=user, kind="created",
                                text=f"Escalated from alert #{a.id}. {text}".strip()))
            from app import incident_workflow  # v2.1
            incident_workflow.evidence_from_ref(db, inc, "alert", str(a.id), user)
        incident_id = inc.id
        text = f"Escalated to incident #{inc.id}. {text}".strip()
    if body.action == "close" and a.status != "resolved":
        a.status = "resolved"
    if body.action == "reopen" and a.status != "open":
        a.status = "open"
    db.add(AlertActivity(alert_id=a.id, username=user, action=body.action, text=text))
    db.commit()
    if body.action in ("close", "reopen"):
        await manager.broadcast("alert_update", a.to_dict())
        await log_event(db, "alert_resolved" if body.action == "close" else "alert_reopened",
                        f"{user} {'closed' if body.action == 'close' else 'reopened'} alert #{a.id} ({a.alert_type})",
                        category="security", device_id=a.device_id, session_id=controller.session_id)
    if incident_id:
        await manager.broadcast("incident", {"id": incident_id})
    return {**_detail(db, a), "incident_id": incident_id}
