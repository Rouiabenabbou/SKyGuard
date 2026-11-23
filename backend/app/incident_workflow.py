"""
v2.1 (SOC stage 3 + 4): incident workflow, evidence, MITRE mapping, approvals
and the incident report.

Phases (NIST SP 800-61 style), in order:
  detection -> triage -> investigation -> containment -> eradication -> recovery -> closure
An incident moves one phase forward (or back) at a time. Closing needs a
resolution summary. Leaving containment without an executed containment
action needs a note that says why none was needed.

Approvals: isolating or releasing a device on request (from an L2 analyst, a
playbook, the AI analyst or the demo) creates an approval request. Only a
person with the "contain_approve" permission can approve it; then the
(simulated) quarantine runs. With APPROVAL_TWO_PERSON=true the requester can't
approve their own request.
"""
import json

from sqlalchemy.orm import Session

from app import config, soc, tenancy
from app.models import (ApprovalRequest, Device, Incident, IncidentEvidence, IncidentNote, IncidentPhase, SecurityAlert,
                        SecurityEvent, utcnow)
from app.websocket_manager import manager

PHASES = [
    ("detection", "Detection", "An alert or a report shows something may be wrong."),
    ("triage", "Triage", "Is it real? How bad? Who owns it?"),
    ("investigation", "Investigation", "Scope: which devices, accounts and addresses; how it started (evidence, intel, AI)."),
    ("containment", "Containment", "Stop the damage: isolate the device, block the address (with approval)."),
    ("eradication", "Eradication", "Remove the cause: rotate credentials, re-flash firmware, close the hole."),
    ("recovery", "Recovery", "Bring the device back, watch that the attack does not return."),
    ("closure", "Closure", "Resolution summary, lessons learned, report."),
]
ORDER = [p[0] for p in PHASES]
STATUS_OF = {"detection": "open", "triage": "open", "investigation": "investigating", "containment": "investigating",
             "eradication": "investigating", "recovery": "investigating", "closure": "resolved"}


class WorkflowError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------ phase
def phase_row(db: Session, inc: Incident) -> IncidentPhase:
    row = db.get(IncidentPhase, inc.id)
    if row is None:
        start = {"resolved": "closure", "investigating": "investigation"}.get(inc.status, "detection")
        row = IncidentPhase(incident_id=inc.id, phase=start, mitre="[]", updated_by="system")
        db.add(row)
        db.flush()
    return row


def note(db: Session, inc: Incident, user: str, kind: str, text: str) -> None:
    db.add(IncidentNote(incident_id=inc.id, username=user, kind=kind, text=text[:4000]))
    inc.updated_at = utcnow()


def executed_containment(db: Session, inc: Incident) -> bool:
    return db.query(ApprovalRequest).filter(ApprovalRequest.incident_id == inc.id, ApprovalRequest.action == "isolate_device",
                                            ApprovalRequest.status == "executed").count() > 0 or (
        inc.device_id is not None and (d := db.get(Device, inc.device_id)) is not None and d.security_status == "quarantined")


def set_phase(db: Session, inc: Incident, new: str, user: str, text: str = "", force: bool = False) -> IncidentPhase:
    if new not in ORDER:
        raise WorkflowError(f"Unknown phase '{new}'")
    row = phase_row(db, inc)
    cur = row.phase
    if new == cur:
        return row
    step = ORDER.index(new) - ORDER.index(cur)
    if abs(step) != 1 and not force:
        raise WorkflowError(f"Move one phase at a time: from {cur} the next phase is "
                            f"{ORDER[min(ORDER.index(cur) + 1, 6)]}.", 409)
    text = text.strip()
    if new == "closure" and not text:
        raise WorkflowError("Write a resolution summary to close the incident.", 422)
    if cur == "containment" and step > 0 and not executed_containment(db, inc) and not text:
        raise WorkflowError("No containment was executed for this incident. Add a note that explains why none was needed.", 422)
    row.phase, row.updated_by, row.updated_at = new, user, utcnow()
    status = STATUS_OF[new]
    if inc.status != status:
        inc.status = status
        inc.resolved_at = utcnow() if status == "resolved" else None
    note(db, inc, user, "phase", f"Phase {cur} → {new}." + (f" {text}" if text else ""))
    return row


def sync_status(db: Session, inc: Incident) -> None:
    """Keep the phase in line when the old status field is changed directly (v1.4 incident board)."""
    row = phase_row(db, inc)
    if inc.status == "resolved" and row.phase != "closure":
        row.phase = "closure"
    elif inc.status != "resolved" and row.phase == "closure":
        row.phase = "recovery"
    elif inc.status == "investigating" and row.phase in ("detection", "triage"):
        row.phase = "investigation"


def phase_history(db: Session, inc: Incident) -> dict:
    out = {"detection": inc.created_at.isoformat() + "Z" if inc.created_at else None}
    for n in db.query(IncidentNote).filter(IncidentNote.incident_id == inc.id, IncidentNote.kind == "phase").order_by(IncidentNote.id):
        target = n.text.split("→")[-1].strip().split(".")[0] if "→" in n.text else None
        if target in ORDER:
            out[target] = n.created_at.isoformat() + "Z"
    return out


# ------------------------------------------------------------------ evidence
def add_evidence(db: Session, inc: Incident, kind: str, ref: str, summary: str, data: dict | None = None,
                 user: str = "system") -> IncidentEvidence:
    existing = db.query(IncidentEvidence).filter(IncidentEvidence.incident_id == inc.id, IncidentEvidence.kind == kind,
                                                 IncidentEvidence.ref == ref).first() if ref else None
    if existing:
        return existing
    ev = IncidentEvidence(incident_id=inc.id, kind=kind, ref=ref, summary=summary[:4000],
                          data=json.dumps(data or {}, default=str)[:20000], added_by=user)
    db.add(ev)
    inc.updated_at = utcnow()
    db.flush()
    return ev


def evidence_from_ref(db: Session, inc: Incident, kind: str, ref: str, user: str) -> IncidentEvidence:
    """Attach a stored object by its id (alert / security_event)."""
    hidden = tenancy.current_hidden()
    if kind == "alert":
        a = db.get(SecurityAlert, int(ref))
        if a is None or a.device_id in hidden:
            raise WorkflowError(f"Alert #{ref} not found", 404)
        r = soc.enrich(db, [a])[0]
        return add_evidence(db, inc, "alert", str(a.id), f"Alert #{a.id} {r['rule_id'] or ''} {r['rule_name']}: {a.description}",
                            {"severity": a.severity, "mitre": r["mitre"], "timestamp": r["timestamp"], "device_id": a.device_id}, user)
    if kind == "security_event":
        e = db.get(SecurityEvent, int(ref))
        if e is None or e.device_id in hidden:
            raise WorkflowError(f"Security event #{ref} not found", 404)
        d = e.to_dict()
        return add_evidence(db, inc, "security_event", str(e.id),
                            f"Event #{e.id} {e.event_type} {e.src_ip or ''} → {e.dst_ip or ''}:{e.dst_port or ''} {e.message}".strip(),
                            d, user)
    raise WorkflowError("kind must be alert or security_event (use note for free text)")


def alerts_of(db: Session, inc: Incident) -> list[SecurityAlert]:
    ids = {inc.alert_id} if inc.alert_id else set()
    ids |= {int(e.ref) for e in db.query(IncidentEvidence).filter(IncidentEvidence.incident_id == inc.id,
                                                                  IncidentEvidence.kind == "alert") if e.ref.isdigit()}
    return [a for a in (db.get(SecurityAlert, i) for i in sorted(ids)) if a is not None]


# ------------------------------------------------------------------ MITRE
def all_techniques() -> list[dict]:
    seen = {}
    for r in soc.rule_catalog():
        if r["mitre"]:
            seen[r["mitre"]["id"]] = r["mitre"]
    return sorted(seen.values(), key=lambda m: m["id"])


def mitre_map(db: Session, inc: Incident) -> list[dict]:
    row = phase_row(db, inc)
    out = {}
    for a in alerts_of(db, inc):
        rule = soc.RULES_BY_TYPE.get(a.alert_type)
        if rule and rule["mitre"]:
            m = rule["mitre"]
            out.setdefault(m["id"], {**m, "from": [], "manual": False})["from"].append(f"alert #{a.id}")
    catalog = {m["id"]: m for m in all_techniques()}
    for tid in json.loads(row.mitre or "[]"):
        m = catalog.get(tid, {"id": tid, "name": tid, "tactic": "", "url": soc.ATTACK_URL.format(tid.replace(".", "/"))})
        out.setdefault(tid, {**m, "from": [], "manual": True})["manual"] = True
    return sorted(out.values(), key=lambda m: m["id"])


# ------------------------------------------------------------------ approvals
ACTIONS = {"isolate_device": "Isolate (quarantine) device", "release_device": "Release device from quarantine"}


async def request_approval(db: Session, action: str, target: str, reason: str, user: str, via: str = "analyst",
                           incident_id: int | None = None, alert_id: int | None = None) -> ApprovalRequest:
    if action not in ACTIONS:
        raise WorkflowError(f"Unknown action '{action}'")
    target = target.upper()
    device = db.get(Device, target)
    if device is None or target in tenancy.current_hidden():
        raise WorkflowError(f"Device {target} not found", 404)
    pending = db.query(ApprovalRequest).filter(ApprovalRequest.action == action, ApprovalRequest.target == target,
                                               ApprovalRequest.status == "pending").first()
    if pending:
        return pending
    req = ApprovalRequest(action=action, target=target, reason=reason.strip()[:2000] or ACTIONS[action],
                          requested_by=user, requested_via=via, incident_id=incident_id, alert_id=alert_id)
    db.add(req)
    db.flush()
    if incident_id:
        inc = db.get(Incident, incident_id)
        if inc:
            note(db, inc, user, "approval", f"Requested approval #{req.id}: {ACTIONS[action]} {target} ({via}). {reason}".strip())
            add_evidence(db, inc, "approval", str(req.id), f"Approval #{req.id} requested: {ACTIONS[action]} {target}", req.to_dict(), user)
    db.commit()
    await manager.broadcast("approval", req.to_dict())
    return req


async def decide(db: Session, req: ApprovalRequest, approve: bool, user: str, text: str = "") -> ApprovalRequest:
    from app.quarantine_service import quarantine
    if req.status != "pending":
        raise WorkflowError(f"Approval #{req.id} is already {req.status}.", 409)
    if req.target in tenancy.current_hidden():
        raise WorkflowError("Approval not found", 404)
    if approve and config.APPROVAL_TWO_PERSON and user == req.requested_by:
        raise WorkflowError("Two-person rule: someone else must approve your own request.", 409)
    req.decided_by, req.decided_at, req.decision_note = user, utcnow(), text.strip()[:2000]
    if not approve:
        req.status = "rejected"
    else:
        req.status = "approved"
        try:
            if req.action == "isolate_device":
                res = await quarantine.quarantine(db, req.target, f"approval #{req.id} by {user}: {req.reason}"[:200],
                                                  triggered_by="approval", alert_id=req.alert_id)
            else:
                res = await quarantine.release(db, req.target)
            req.status = "executed"
            req.result = ("done (simulated isolation)" if req.action == "isolate_device" else "released") + \
                ("" if res.get("changed", True) else " - nothing to change")
        except Exception as exc:
            req.status, req.result = "failed", str(exc)[:500]
    if req.incident_id:
        inc = db.get(Incident, req.incident_id)
        if inc:
            note(db, inc, user, "approval", f"Approval #{req.id} {req.status} by {user}: {ACTIONS[req.action]} {req.target}."
                 + (f" {req.result}." if req.result else "") + (f" {text}" if text else ""))
    db.commit()
    await manager.broadcast("approval", req.to_dict())
    if req.incident_id:
        await manager.broadcast("incident", {"id": req.incident_id})
    return req


# ------------------------------------------------------------------ full view + report
def workflow(db: Session, inc: Incident) -> dict:
    from app.models import AiInvestigation, PlaybookRun
    row = phase_row(db, inc)
    db.commit()
    hist = phase_history(db, inc)
    evidence = [e.to_dict() for e in db.query(IncidentEvidence).filter(IncidentEvidence.incident_id == inc.id).order_by(IncidentEvidence.id)]
    approvals = [a.to_dict() for a in db.query(ApprovalRequest).filter(ApprovalRequest.incident_id == inc.id).order_by(ApprovalRequest.id)]
    from app import playbooks
    runs = [playbooks.view(db, r) for r in db.query(PlaybookRun).filter(PlaybookRun.incident_id == inc.id).order_by(PlaybookRun.id)]
    ai = [{"id": x.id, "created_at": x.created_at.isoformat() + "Z", "provider": x.provider, "created_by": x.created_by,
           "answer": x.answer} for x in db.query(AiInvestigation).filter(AiInvestigation.incident_id == inc.id).order_by(AiInvestigation.id)]
    alerts = soc.enrich(db, alerts_of(db, inc))
    return {
        "phase": row.phase,
        "phases": [{"id": p, "label": label, "help": h, "at": hist.get(p), "done": ORDER.index(p) < ORDER.index(row.phase),
                    "current": p == row.phase} for p, label, h in PHASES],
        "mitre": mitre_map(db, inc), "techniques": all_techniques(),
        "evidence": evidence, "approvals": approvals, "playbook_runs": runs, "ai": ai, "alerts": alerts,
        "suggested_playbooks": playbooks.suggest([a.alert_type for a in alerts_of(db, inc)]),
        "containment_executed": executed_containment(db, inc),
    }


def report_markdown(db: Session, inc: Incident) -> str:
    w = workflow(db, inc)
    notes = db.query(IncidentNote).filter(IncidentNote.incident_id == inc.id).order_by(IncidentNote.id).all()
    device = db.get(Device, inc.device_id) if inc.device_id else None
    src = {a["source"] for a in w["alerts"]} or {"simulation"}
    lines = [
        f"# Incident report #{inc.id}: {inc.title}",
        "",
        f"*CyberShield SOC · generated {utcnow().isoformat(timespec='seconds')}Z · data source: {', '.join(sorted(src)).upper()}*",
        "",
        "> All attacks in this project are simulated inside the project; quarantine is a simulated isolation.",
        "",
        "## Summary",
        f"- Severity: **{inc.severity}** · status: **{inc.status}** · phase: **{w['phase']}**",
        f"- Opened {inc.created_at.isoformat(timespec='seconds')}Z by {inc.created_by or 'system'}; "
        f"assigned to {inc.assignee or 'nobody'}"
        + (f"; resolved {inc.resolved_at.isoformat(timespec='seconds')}Z" if inc.resolved_at else ""),
        f"- Asset: {device.device_id + ' · ' + device.device_name + ' (' + device.connection_type + ', ' + (device.location or '-') + ')' if device else (inc.device_id or 'network')}",
    ]
    if inc.resolved_at and inc.created_at:
        lines.append(f"- Time to resolve: {(inc.resolved_at - inc.created_at).total_seconds() / 60:.1f} min")
    lines += ["", "## Workflow"]
    for p in w["phases"]:
        lines.append(f"- {'[x]' if p['done'] or p['current'] and p['id'] == 'closure' else ('[>]' if p['current'] else '[ ]')} "
                     f"{p['label']}{' · ' + p['at'] if p['at'] else ''}")
    lines += ["", "## Detections"]
    for a in w["alerts"]:
        lines.append(f"- #{a['id']} {a['timestamp']} **{a['severity']}** {a['rule_id'] or ''} {a['rule_name']}: {a['description']}"
                     f" (confidence {round(a['confidence'] * 100)}%, {a['source'].upper()})")
    if not w["alerts"]:
        lines.append("- none linked")
    lines += ["", "## MITRE ATT&CK"]
    for m in w["mitre"]:
        lines.append(f"- [{m['id']}]({m['url']}) {m['name']} · {m['tactic']} ({', '.join(m['from']) or 'analyst'})")
    if not w["mitre"]:
        lines.append("- no technique mapped")
    lines += ["", "## Evidence"]
    for e in w["evidence"]:
        lines.append(f"- E{e['id']} [{e['kind']}] {e['summary']} (added by {e['added_by']}, {e['added_at']})")
    if not w["evidence"]:
        lines.append("- none attached")
    lines += ["", "## Response actions"]
    for a in w["approvals"]:
        lines.append(f"- Approval #{a['id']}: {ACTIONS.get(a['action'], a['action'])} {a['target']} · requested by "
                     f"{a['requested_by']} ({a['requested_via']}) · {a['status']}"
                     + (f" by {a['decided_by']} at {a['decided_at']}" if a['decided_by'] else "") + (f" · {a['result']}" if a['result'] else ""))
    for r in w["playbook_runs"]:
        done = sum(s["state"] == "done" for s in r["steps"])
        lines.append(f"- Playbook {r['playbook_id']} {r['name']}: {done}/{len(r['steps'])} steps · {r['status']}")
    if not w["approvals"] and not w["playbook_runs"]:
        lines.append("- none")
    if w["ai"]:
        lines += ["", "## AI analyst (advisory)", "", w["ai"][-1]["answer"]]
    lines += ["", "## Timeline"]
    for n in notes:
        lines.append(f"- {n.created_at.isoformat(timespec='seconds')}Z · {n.username or 'system'} · {n.kind}: {n.text}")
    return "\n".join(lines) + "\n"
