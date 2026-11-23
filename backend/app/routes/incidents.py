"""
Incidents (v1.4): the operators' case board. An alert says "something happened";
an incident is the work to fix it: who is on it, what was done, when it was closed.

GET  /api/incidents                    list (?status=open|investigating|resolved)
POST /api/incidents                    {"title", "device_id", "alert_id", "severity"} or just {"alert_id"}
GET  /api/incidents/{id}               one incident with its timeline
PUT  /api/incidents/{id}               {"status", "assignee", "severity"}
POST /api/incidents/{id}/notes         {"text"}
Company users only see the incidents of their own devices.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import tenancy
from app.database import get_db
from app.models import Incident, IncidentNote, SecurityAlert, User, utcnow
from app.websocket_manager import manager

router = APIRouter(prefix="/api/incidents", tags=["incidents"])
Severity = Literal["low", "medium", "high", "critical"]
Status = Literal["open", "investigating", "resolved"]


def _user(request: Request) -> str:
    user = getattr(request.state, "user", None)
    return user.username if user else "operator"


def _get(db: Session, incident_id: int) -> Incident:
    inc = db.get(Incident, incident_id)
    if inc is None or (inc.device_id and inc.device_id in tenancy.current_hidden()):
        raise HTTPException(status_code=404, detail=f"Incident #{incident_id} not found")
    return inc


def _with_notes(db: Session, inc: Incident) -> dict:
    notes = db.query(IncidentNote).filter(IncidentNote.incident_id == inc.id).order_by(IncidentNote.id).all()
    return {**inc.to_dict(), "notes": [n.to_dict() for n in notes]}


@router.get("")
def list_incidents(status: Status | None = None, limit: int = Query(default=100, ge=1, le=500),
                   db: Session = Depends(get_db)):
    q = db.query(Incident)
    if status:
        q = q.filter(Incident.status == status)
    hidden = tenancy.current_hidden()
    items = [i.to_dict() for i in q.order_by(Incident.id.desc()).limit(limit) if not (i.device_id and i.device_id in hidden)]
    counts = {s: 0 for s in ("open", "investigating", "resolved")}
    for (s, d) in db.query(Incident.status, Incident.device_id):
        if not (d and d in hidden):
            counts[s] = counts.get(s, 0) + 1
    return {"incidents": items, "counts": counts}


class IncidentIn(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    device_id: str | None = Field(default=None, max_length=32)
    alert_id: int | None = None
    severity: Severity | None = None
    assignee: str | None = Field(default=None, max_length=64)


@router.post("", status_code=201)
async def create_incident(body: IncidentIn, request: Request, db: Session = Depends(get_db)):
    title, device_id, severity = body.title, body.device_id, body.severity
    if body.alert_id is not None:
        alert = db.get(SecurityAlert, body.alert_id)
        if alert is None or (alert.device_id and alert.device_id in tenancy.current_hidden()):
            raise HTTPException(status_code=404, detail=f"Alert #{body.alert_id} not found")
        existing = db.query(Incident).filter(Incident.alert_id == alert.id, Incident.status != "resolved").first()
        if existing:
            return {"incident": _with_notes(db, existing), "existing": True}
        title = title or f"{alert.alert_type.replace('_', ' ').capitalize()} on {alert.device_id or 'the network'}"
        device_id = device_id or alert.device_id
        severity = severity or alert.severity
    if not title:
        raise HTTPException(status_code=422, detail="Give a title or an alert_id.")
    device_id = device_id.upper() if device_id else None
    if device_id and device_id in tenancy.current_hidden():
        raise HTTPException(status_code=403, detail=f"{device_id} belongs to another company.")
    user = _user(request)
    inc = Incident(title=title.strip(), device_id=device_id, alert_id=body.alert_id, severity=severity or "high",
                   assignee=(body.assignee or "").strip(), created_by=user)
    db.add(inc)
    db.flush()
    db.add(IncidentNote(incident_id=inc.id, username=user, kind="created",
                        text=f"Incident opened{f' from alert #{body.alert_id}' if body.alert_id else ''}."))
    if body.alert_id is not None:  # v2.1: the alert is the first piece of evidence
        from app import incident_workflow
        incident_workflow.evidence_from_ref(db, inc, "alert", str(body.alert_id), user)
    db.commit()
    await manager.broadcast("incident", inc.to_dict())
    return {"incident": _with_notes(db, inc), "existing": False}


@router.get("/{incident_id}")
def get_incident(incident_id: int, db: Session = Depends(get_db)):
    return {"incident": _with_notes(db, _get(db, incident_id))}


class IncidentUpdate(BaseModel):
    status: Status | None = None
    assignee: str | None = Field(default=None, max_length=64)
    severity: Severity | None = None


@router.put("/{incident_id}")
async def update_incident(incident_id: int, body: IncidentUpdate, request: Request, db: Session = Depends(get_db)):
    inc = _get(db, incident_id)
    user = _user(request)
    if body.assignee is not None and body.assignee.strip() != inc.assignee:
        name = body.assignee.strip()
        if name and db.get(User, name) is None:
            raise HTTPException(status_code=400, detail=f"No user called '{name}'.")
        inc.assignee = name
        db.add(IncidentNote(incident_id=inc.id, username=user, kind="assign",
                            text=f"Assigned to {name}." if name else "Unassigned."))
    if body.severity and body.severity != inc.severity:
        db.add(IncidentNote(incident_id=inc.id, username=user, kind="status",
                            text=f"Severity {inc.severity} -> {body.severity}."))
        inc.severity = body.severity
    if body.status and body.status != inc.status:
        db.add(IncidentNote(incident_id=inc.id, username=user, kind="status", text=f"Status {inc.status} -> {body.status}."))
        inc.status = body.status
        inc.resolved_at = utcnow() if body.status == "resolved" else None
    inc.updated_at = utcnow()
    from app import incident_workflow  # v2.1: keep the 7-phase workflow in line with the status
    incident_workflow.sync_status(db, inc)
    db.commit()
    await manager.broadcast("incident", inc.to_dict())
    return {"incident": _with_notes(db, inc)}


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/{incident_id}/notes", status_code=201)
async def add_note(incident_id: int, body: NoteIn, request: Request, db: Session = Depends(get_db)):
    inc = _get(db, incident_id)
    db.add(IncidentNote(incident_id=inc.id, username=_user(request), kind="note", text=body.text.strip()))
    inc.updated_at = utcnow()
    db.commit()
    await manager.broadcast("incident", inc.to_dict())
    return {"incident": _with_notes(db, inc)}
