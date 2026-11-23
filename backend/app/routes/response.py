"""
v2.1 (SOC stages 3-4): incident workflow, approvals, playbooks, GNSS, demo scenario.

GET  /api/incidents/{id}/workflow             phases, MITRE, evidence, approvals, playbooks, AI analyses
POST /api/incidents/{id}/phase                {"phase", "note"}
POST /api/incidents/{id}/evidence             {"kind": "alert|security_event|note", "ref", "summary"}
PUT  /api/incidents/{id}/mitre                {"techniques": ["T1110.001", ...]}  (analyst additions)
GET  /api/incidents/{id}/report               Markdown report (?format=md downloads it)
POST /api/incidents/{id}/playbooks            {"playbook_id"}
POST /api/incidents/{id}/playbooks/{run}/steps/{step}  {"note", "skip"}
GET  /api/playbooks                           catalogue
GET  /api/approvals                           ?status=pending
POST /api/approvals                           {"action": "isolate_device|release_device", "target", "reason", "incident_id", "alert_id"}
POST /api/approvals/{id}/approve              {"note", "code"}   (contain_approve; two-factor code if the approver has it on)
POST /api/approvals/{id}/reject               {"note"}
GET  /api/soc/gnss                            GNSS integrity of the satellite terminals (simulated)
GET  /api/soc/demo                            latest demo run
POST /api/soc/demo/start                      run the end-to-end demo scenario
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth, demo, gnss, incident_workflow as wf, mfa, playbooks, soc, tenancy
from app.database import get_db
from app.models import ApprovalRequest, DemoRun, Incident, PlaybookRun, UserMfa
from app.websocket_manager import manager

router = APIRouter(prefix="/api", tags=["response"])


def _user(request: Request) -> str:
    u = getattr(request.state, "user", None)
    return u.username if u else "operator"


def _incident(db: Session, incident_id: int) -> Incident:
    inc = db.get(Incident, incident_id)
    if inc is None or (inc.device_id and inc.device_id in tenancy.current_hidden()):
        raise HTTPException(status_code=404, detail=f"Incident #{incident_id} not found")
    return inc


def _wf_error(exc: wf.WorkflowError):
    raise HTTPException(status_code=exc.status, detail=str(exc))


# ------------------------------------------------------------------ incident workflow
@router.get("/incidents/{incident_id}/workflow")
def get_workflow(incident_id: int, db: Session = Depends(get_db)):
    return wf.workflow(db, _incident(db, incident_id))


class PhaseIn(BaseModel):
    phase: str = Field(max_length=20)
    note: str = Field(default="", max_length=2000)


@router.post("/incidents/{incident_id}/phase")
async def set_phase(incident_id: int, body: PhaseIn, request: Request, db: Session = Depends(get_db)):
    inc = _incident(db, incident_id)
    try:
        wf.set_phase(db, inc, body.phase, _user(request), body.note)
    except wf.WorkflowError as exc:
        _wf_error(exc)
    db.commit()
    await manager.broadcast("incident", inc.to_dict())
    return wf.workflow(db, inc)


class EvidenceIn(BaseModel):
    kind: str = Field(pattern="^(alert|security_event|note)$")
    ref: str = Field(default="", max_length=64)
    summary: str = Field(default="", max_length=2000)


@router.post("/incidents/{incident_id}/evidence", status_code=201)
def add_evidence(incident_id: int, body: EvidenceIn, request: Request, db: Session = Depends(get_db)):
    inc = _incident(db, incident_id)
    user = _user(request)
    try:
        if body.kind == "note":
            if not body.summary.strip():
                raise wf.WorkflowError("Write the evidence text.", 422)
            e = wf.add_evidence(db, inc, "note", "", body.summary.strip(), {}, user)
        else:
            if not body.ref.isdigit():
                raise wf.WorkflowError("ref must be the numeric id of the alert / event", 422)
            e = wf.evidence_from_ref(db, inc, body.kind, body.ref, user)
    except wf.WorkflowError as exc:
        _wf_error(exc)
    wf.note(db, inc, user, "evidence", f"Evidence added: {e.summary[:200]}")
    db.commit()
    return {"evidence": e.to_dict()}


class MitreIn(BaseModel):
    techniques: list[str] = Field(default_factory=list, max_length=30)


@router.put("/incidents/{incident_id}/mitre")
def set_mitre(incident_id: int, body: MitreIn, request: Request, db: Session = Depends(get_db)):
    import json
    import re
    inc = _incident(db, incident_id)
    ids = []
    for t in body.techniques:
        t = t.strip().upper()
        if not re.fullmatch(r"T\d{4}(\.\d{3})?", t):
            raise HTTPException(status_code=422, detail=f"'{t}' is not an ATT&CK technique ID (e.g. T1110 or T1110.001)")
        if t not in ids:
            ids.append(t)
    row = wf.phase_row(db, inc)
    row.mitre = json.dumps(ids)
    wf.note(db, inc, _user(request), "mitre", "MITRE mapping: " + (", ".join(ids) or "analyst additions removed"))
    db.commit()
    return {"mitre": wf.mitre_map(db, inc)}


@router.get("/incidents/{incident_id}/report")
def report(incident_id: int, format: str = Query(default="json", pattern="^(json|md)$"), db: Session = Depends(get_db)):
    inc = _incident(db, incident_id)
    text = wf.report_markdown(db, inc)
    if format == "md":
        return PlainTextResponse(text, media_type="text/markdown",
                                 headers={"Content-Disposition": f'attachment; filename="incident-{inc.id}-report.md"'})
    return {"incident_id": inc.id, "markdown": text}


# ------------------------------------------------------------------ playbooks
@router.get("/playbooks")
def list_playbooks():
    return {"playbooks": playbooks.catalog()}


class PlaybookIn(BaseModel):
    playbook_id: str = Field(max_length=10)


@router.post("/incidents/{incident_id}/playbooks", status_code=201)
def start_playbook(incident_id: int, body: PlaybookIn, request: Request, db: Session = Depends(get_db)):
    inc = _incident(db, incident_id)
    try:
        run = playbooks.start(db, inc, body.playbook_id, _user(request))
    except wf.WorkflowError as exc:
        _wf_error(exc)
    return {"run": playbooks.view(db, run)}


class StepIn(BaseModel):
    note: str = Field(default="", max_length=2000)
    skip: bool = False


@router.post("/incidents/{incident_id}/playbooks/{run_id}/steps/{step_id}")
async def run_step(incident_id: int, run_id: int, step_id: str, body: StepIn, request: Request, db: Session = Depends(get_db)):
    inc = _incident(db, incident_id)
    run = db.get(PlaybookRun, run_id)
    if run is None or run.incident_id != inc.id:
        raise HTTPException(status_code=404, detail="Playbook run not found")
    try:
        run = await playbooks.run_step(db, run, step_id, _user(request), body.note, body.skip)
    except wf.WorkflowError as exc:
        db.rollback()
        _wf_error(exc)
    await manager.broadcast("incident", inc.to_dict())
    return {"run": playbooks.view(db, run), "workflow": wf.workflow(db, inc)}


# ------------------------------------------------------------------ approvals
@router.get("/approvals")
def list_approvals(status: str | None = Query(default=None, pattern="^(pending|approved|rejected|executed|failed)$"),
                   limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)):
    q = db.query(ApprovalRequest)
    if status:
        q = q.filter(ApprovalRequest.status == status)
    hidden = tenancy.current_hidden()
    rows = [r.to_dict() for r in q.order_by(ApprovalRequest.id.desc()).limit(limit) if r.target not in hidden]
    pending = sum(1 for r in db.query(ApprovalRequest).filter(ApprovalRequest.status == "pending") if r.target not in hidden)
    return {"approvals": rows, "pending": pending, "two_person_rule": wf.config.APPROVAL_TWO_PERSON,
            "actions": wf.ACTIONS}


class ApprovalIn(BaseModel):
    action: str = Field(pattern="^(isolate_device|release_device)$")
    target: str = Field(min_length=1, max_length=32)
    reason: str = Field(default="", max_length=2000)
    incident_id: int | None = None
    alert_id: int | None = None
    via: str = Field(default="analyst", pattern="^(analyst|ai)$")


@router.post("/approvals", status_code=201)
async def request_approval(body: ApprovalIn, request: Request, db: Session = Depends(get_db)):
    if body.incident_id:
        _incident(db, body.incident_id)
    try:
        req = await wf.request_approval(db, body.action, body.target, body.reason, _user(request), body.via,
                                        body.incident_id, body.alert_id)
    except wf.WorkflowError as exc:
        _wf_error(exc)
    return {"approval": req.to_dict()}


class DecisionIn(BaseModel):
    note: str = Field(default="", max_length=2000)
    code: str | None = Field(default=None, max_length=12)


async def _decide(approval_id: int, approve: bool, body: DecisionIn, request: Request, db: Session):
    req = db.get(ApprovalRequest, approval_id)
    if req is None or req.target in tenancy.current_hidden():
        raise HTTPException(status_code=404, detail="Approval not found")
    user = getattr(request.state, "user", None)
    if approve and user is not None and auth.mfa_enabled(db, user.username):  # step-up: the approver confirms with a code
        m = db.get(UserMfa, user.username)
        step = mfa.verify(m.secret, body.code or "", m.last_step)
        if step is None:
            raise HTTPException(status_code=401 if not body.code else 400,
                                detail="Enter your current two-factor code to approve a containment.")
        m.last_step = step
        db.commit()
    try:
        req = await wf.decide(db, req, approve, _user(request), body.note)
    except wf.WorkflowError as exc:
        _wf_error(exc)
    return {"approval": req.to_dict()}


@router.post("/approvals/{approval_id}/approve")
async def approve(approval_id: int, body: DecisionIn, request: Request, db: Session = Depends(get_db)):
    return await _decide(approval_id, True, body, request, db)


@router.post("/approvals/{approval_id}/reject")
async def reject(approval_id: int, body: DecisionIn, request: Request, db: Session = Depends(get_db)):
    return await _decide(approval_id, False, body, request, db)


# ------------------------------------------------------------------ GNSS + demo
@router.get("/soc/gnss")
def gnss_status(db: Session = Depends(get_db)):
    from datetime import timedelta
    from app.models import SecurityAlert, utcnow
    devices = gnss.status(db, tenancy.current_hidden())
    since = utcnow() - timedelta(hours=24)
    alerts = [a for a in db.query(SecurityAlert).filter(SecurityAlert.alert_type.in_(("gnss_jamming", "gnss_spoofing")),
                                                        SecurityAlert.timestamp >= since).order_by(SecurityAlert.id.desc()).limit(20)
              if a.device_id not in tenancy.current_hidden()]
    return {"devices": devices, "alerts": soc.enrich(db, alerts),
            "thresholds": {"min_cn0": wf.config.GNSS_MIN_CN0, "max_speed_mps": wf.config.GNSS_MAX_SPEED_MPS, "max_offset_km": 5},
            "note": "Simulated GNSS receiver values (the project has no GNSS hardware)."}


@router.get("/soc/demo")
def demo_status(db: Session = Depends(get_db)):
    run = db.query(DemoRun).order_by(DemoRun.id.desc()).first()
    return {"run": demo.view(run) if run else None, "steps": [{"id": i, "label": l} for i, l in demo.STEPS], "target": demo.TARGET}


@router.post("/soc/demo/start", status_code=201)
async def demo_start(request: Request, db: Session = Depends(get_db)):
    try:
        run = demo.create(db, _user(request))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"run": demo.view(run)}
