"""
AI security assistant endpoints (v1.1). See app/ai_assistant.py.

GET  /api/ai/status                 provider, model, key configured?
POST /api/ai/chat                   {"message": "...", "history": [...]}
POST /api/ai/explain-alert/{id}     what an alert means and what to do
POST /api/ai/report                 short incident report of the session
v2.1 (AI SOC analyst with controlled tools, see app/ai_tools.py):
GET  /api/ai/tools                  the tools the analyst may use (read / action)
POST /api/ai/tools/{name}           run one READ tool yourself
POST /api/ai/investigate            {"alert_id"} | {"incident_id"} | {"question"} -> answer with cited evidence
GET  /api/ai/investigations         past investigations (?alert_id=, ?incident_id=)
"""
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import ai_assistant
from app.database import get_db
from app.models import SecurityAlert

router = APIRouter(prefix="/api/ai", tags=["ai"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[dict] = Field(default_factory=list)


@router.get("/status")
def ai_status():
    return ai_assistant.status()


@router.post("/chat")
async def chat(body: ChatIn, db: Session = Depends(get_db)):
    return await ai_assistant.answer(db, body.message, body.history)


@router.post("/explain-alert/{alert_id}")
async def explain_alert(alert_id: int, db: Session = Depends(get_db)):
    from app import tenancy
    alert = db.get(SecurityAlert, alert_id)
    if alert is None or alert.device_id in tenancy.current_hidden():
        raise HTTPException(status_code=404, detail=f"Alert #{alert_id} not found")
    question = (f"Explain alert #{alert.id} ({alert.alert_type}, {alert.severity}, device {alert.device_id or '-'}, "
                f"status {alert.status}): \"{alert.description}\". What does it mean, what is the likely cause, "
                "and what should the operator do now?")
    if alert.status != "open" or not ai_assistant.is_configured():
        # The offline analyst needs the alert even if it is resolved.
        text = ai_assistant.offline_explain({"id": alert.id, "type": alert.alert_type, "severity": alert.severity,
                                             "device": alert.device_id})
        if not ai_assistant.is_configured():
            return {"answer": text, "source": "offline", "commands": ai_assistant.commands_in(text)}
    return await ai_assistant.answer(db, question, task=f"explain:{alert.id}")


@router.post("/report")
async def report(db: Session = Depends(get_db)):
    return await ai_assistant.answer(
        db, "Write a short incident report of the current session for my supervisor: overall status, the main "
            "incidents and their likely causes, what was done (quarantine, failover) and 3 recommendations.",
        task="report")


# ------------------------------------------- v1.4: set the free AI key from the dashboard
class AiSettingsIn(BaseModel):
    provider: str = Field(default="deepseek", max_length=20)
    api_key: str | None = Field(default=None, max_length=300)  # None = keep, "" = remove
    model: str = Field(default="", max_length=100)
    base_url: str | None = Field(default=None, max_length=190)  # v1.5: OmniRoute address


def _public(db: Session) -> dict:
    from app.models import AiSettings
    row = db.get(AiSettings, 1)
    return {**ai_assistant.status(), "saved_provider": row.provider if row else "deepseek",
            "saved_model": row.model if row else "", "key_saved": bool(row and row.api_key),
            "key_hint": (f"…{row.api_key[-4:]}" if row and len(row.api_key) > 8 else ""),
            "saved_base_url": ai_assistant.base_url(row.provider if row else None)}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    """Platform admin: which AI is used. The key itself is never sent back."""
    return _public(db)


@router.put("/settings")
def save_settings(body: AiSettingsIn, db: Session = Depends(get_db)):
    from app.models import AiSettings, utcnow
    if body.provider not in ai_assistant.PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Provider must be one of {', '.join(ai_assistant.PROVIDERS)}.")
    row = db.get(AiSettings, 1) or AiSettings(id=1)
    row.provider, row.model, row.updated_at = body.provider, body.model.strip(), utcnow()
    if body.api_key is not None:
        row.api_key = body.api_key.strip()
    if body.base_url is not None:
        from app.models import AppFlag
        url = body.base_url.strip()
        if url and not re.match(r"^https?://[^\s/]+(/\S*)?$", url):
            raise HTTPException(status_code=400, detail="The address must start with http:// or https://")
        flag = db.get(AppFlag, "ai_base_url") or AppFlag(key="ai_base_url")
        flag.value = url
        db.merge(flag)
    db.merge(row)
    db.commit()
    return _public(db)


@router.post("/test")
async def test_key(db: Session = Depends(get_db)):
    """Ask the AI one tiny question to check the key works."""
    if not ai_assistant.is_configured():
        raise HTTPException(status_code=400, detail="No AI key yet: paste a free key first.")
    try:
        text = await ai_assistant.ask_llm([{"role": "user", "content": "Reply with exactly: CyberShield AI ready"}])
        return {"ok": True, "answer": text[:200], **ai_assistant.status()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300], **ai_assistant.status()}


# ------------------------------------------------------------------ v2.1 AI SOC analyst
class InvestigateIn(BaseModel):
    alert_id: int | None = None
    incident_id: int | None = None
    question: str | None = Field(default=None, max_length=1000)


@router.get("/tools")
def tools():
    from app import ai_tools
    return {"tools": ai_tools.TOOLS}


@router.post("/tools/{name}")
async def run_tool(name: str, args: dict, db: Session = Depends(get_db)):
    from app import ai_tools
    if name not in ai_tools.READ_TOOLS:
        raise HTTPException(status_code=403, detail="Only read tools can be run directly; actions go through incidents and approvals.")
    allowed = set(next(t for t in ai_tools.TOOLS if t["name"] == name)["params"])
    try:
        return await ai_tools.run_tool(db, name, {k: v for k, v in args.items() if k in allowed})
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/investigate")
async def investigate(body: InvestigateIn, request: Request, db: Session = Depends(get_db)):
    from app import ai_tools
    if not (body.alert_id or body.incident_id or (body.question and body.question.strip())):
        raise HTTPException(status_code=422, detail="Give an alert_id, an incident_id or a question.")
    user = getattr(request.state, "user", None)
    try:
        return await ai_tools.investigate(db, user.username if user else "analyst", alert_id=body.alert_id,
                                          incident_id=body.incident_id, question=(body.question or "").strip() or None)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/investigations")
def investigations(alert_id: int | None = None, incident_id: int | None = None, db: Session = Depends(get_db)):
    import json
    from app import tenancy
    from app.models import AiInvestigation, Incident
    q = db.query(AiInvestigation)
    if alert_id:
        q = q.filter(AiInvestigation.alert_id == alert_id)
    if incident_id:
        q = q.filter(AiInvestigation.incident_id == incident_id)
    hidden = tenancy.current_hidden()
    out = []
    for r in q.order_by(AiInvestigation.id.desc()).limit(30):
        if r.alert_id and (a := db.get(SecurityAlert, r.alert_id)) is not None and a.device_id in hidden:
            continue
        if r.incident_id and (i := db.get(Incident, r.incident_id)) is not None and i.device_id in hidden:
            continue
        out.append({"id": r.id, "alert_id": r.alert_id, "incident_id": r.incident_id, "question": r.question, "answer": r.answer,
                    "evidence": json.loads(r.evidence), "tool_calls": json.loads(r.tools), "proposed_actions": json.loads(r.actions),
                    "source": r.provider, "created_by": r.created_by, "created_at": r.created_at.isoformat() + "Z"})
    return {"investigations": out}
