"""
Quarantine endpoints.

POST /api/devices/{device_id}/quarantine    body (optional): {"reason": "..."}
POST /api/devices/{device_id}/release      (also clears a "suspicious" flag)
GET  /api/quarantine                        active quarantines + history
GET  /api/quarantine/settings               {"auto_quarantine": true, "alert_types": [...]}
POST /api/quarantine/settings               body: {"auto_quarantine": false}
"""
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import config
from app.database import get_db
from app.models import QuarantineRecord
from app.quarantine_service import quarantine

router = APIRouter(prefix="/api", tags=["quarantine"])


class QuarantineRequest(BaseModel):
    reason: str = "manual quarantine by operator"


class QuarantineSettings(BaseModel):
    auto_quarantine: bool


@router.post("/devices/{device_id}/quarantine")
async def quarantine_device(device_id: str, body: QuarantineRequest | None = Body(default=None),
                            db: Session = Depends(get_db)):
    try:
        result = await quarantine.quarantine(db, device_id, (body or QuarantineRequest()).reason, "operator")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    msg = "Device quarantined (simulation)" if result["changed"] else "Device was already quarantined"
    return {"message": msg, **result}


@router.post("/devices/{device_id}/release")
async def release_device(device_id: str, db: Session = Depends(get_db)):
    try:
        result = await quarantine.release(db, device_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if not result["changed"]:
        msg = "Device was not quarantined"
    elif result["record"] is None:
        msg = "Suspicion cleared, device trusted again"
    else:
        msg = "Device released from quarantine"
    return {"message": msg, **result}


@router.get("/quarantine")
def list_quarantine(db: Session = Depends(get_db)):
    rows = db.query(QuarantineRecord).order_by(QuarantineRecord.id.desc()).limit(100).all()
    return {
        "active": [r.to_dict() for r in rows if r.released_at is None],
        "history": [r.to_dict() for r in rows],
    }


@router.get("/quarantine/settings")
def get_settings():
    return {"auto_quarantine": quarantine.auto_enabled, "alert_types": config.AUTO_QUARANTINE_ALERTS}


@router.post("/quarantine/settings")
def set_settings(settings: QuarantineSettings):
    quarantine.auto_enabled = settings.auto_quarantine
    return {"auto_quarantine": quarantine.auto_enabled, "alert_types": config.AUTO_QUARANTINE_ALERTS}
