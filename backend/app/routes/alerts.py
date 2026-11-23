"""
Security alert endpoints.

GET  /api/alerts                 recent alerts (filters: status, severity, device_id, limit)
GET  /api/alerts/stats           counts by severity, type and status
POST /api/alerts/{id}/resolve    mark an alert as handled
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.event_log import log_event
from app.models import SecurityAlert
from app.simulation_controller import controller
from app.websocket_manager import manager

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
def list_alerts(
    status: str | None = Query(default=None, pattern="^(open|resolved)$"),
    severity: str | None = Query(default=None, pattern="^(low|medium|high|critical)$"),
    device_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    q = db.query(SecurityAlert)
    if status:
        q = q.filter(SecurityAlert.status == status)
    if severity:
        q = q.filter(SecurityAlert.severity == severity)
    if device_id:
        q = q.filter(SecurityAlert.device_id == device_id)
    rows = q.order_by(SecurityAlert.id.desc()).limit(limit).all()
    return {"count": len(rows), "alerts": [a.to_dict() for a in rows]}


@router.get("/stats")
def alert_stats(db: Session = Depends(get_db)):
    def grouped(column):
        return {k: v for k, v in db.query(column, func.count()).group_by(column).all()}

    return {
        "total": db.query(SecurityAlert).count(),
        "open": db.query(SecurityAlert).filter(SecurityAlert.status == "open").count(),
        "by_severity": grouped(SecurityAlert.severity),
        "by_type": grouped(SecurityAlert.alert_type),
        "by_status": grouped(SecurityAlert.status),
    }


@router.post("/{alert_id}/resolve")
async def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    from app import tenancy
    alert = db.get(SecurityAlert, alert_id)
    if alert is None or alert.device_id in tenancy.current_hidden():
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    if alert.status != "resolved":
        alert.status = "resolved"
        db.commit()
        await log_event(db, "alert_resolved", f"Operator resolved alert #{alert.id} ({alert.alert_type})",
                        category="security", device_id=alert.device_id, session_id=controller.session_id)
        await manager.broadcast("alert_update", alert.to_dict())
    return {"message": f"Alert {alert_id} resolved", "alert": alert.to_dict()}
