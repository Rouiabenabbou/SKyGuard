"""
Failover endpoints (Phase 8).

GET  /api/failover/status    on/off, settings, each device's mode, statistics
GET  /api/failover/history   failover / failback / outage records
POST /api/failover/settings  {"enabled": true | false}
POST /api/failover/drill     "satellite outage drill": SAT-1 goes offline for
                             DRILL_SECONDS, then comes back by itself
"""
import asyncio
import time

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import config
from app.database import SessionLocal, get_db
from app.event_log import log_event
from app.failover_service import failover
from app.models import FailoverEvent
from app.network_simulator import network
from app.simulation_controller import controller
from app.websocket_manager import manager

router = APIRouter(prefix="/api/failover", tags=["failover"])

DRILL_NODE = "SAT-1"
_drill_task: asyncio.Task | None = None


class FailoverSettings(BaseModel):
    enabled: bool


@router.get("/status")
def status(db: Session = Depends(get_db)):
    return failover.summary(db)


@router.get("/history")
def history(limit: int = Query(default=50, ge=1, le=500), db: Session = Depends(get_db)):
    rows = db.query(FailoverEvent).order_by(FailoverEvent.id.desc()).limit(limit).all()
    return {"count": len(rows), "events": [r.to_dict() for r in rows]}


@router.post("/settings")
async def settings(body: FailoverSettings, db: Session = Depends(get_db)):
    failover.enabled = body.enabled
    await log_event(db, "failover_setting", f"Operator turned automatic failover {'ON' if body.enabled else 'OFF'}",
                    category="network", session_id=controller.session_id)
    await network.tick(db, controller.session_id)
    summary = failover.summary(db)
    await manager.broadcast("failover", {"status": summary})
    return summary


async def _end_drill_later(seconds: float) -> None:
    await asyncio.sleep(seconds)
    with SessionLocal() as db:
        network.set_node_state(DRILL_NODE, "auto")
        failover.drill_until = None
        await log_event(db, "drill_finished", f"Outage drill finished: {DRILL_NODE} is back online",
                        category="network", session_id=controller.session_id)
        await network.tick(db, controller.session_id)
        await manager.broadcast("failover", {"status": failover.summary(db)})


@router.post("/drill")
async def drill(seconds: float = Query(default=None, ge=5, le=300), db: Session = Depends(get_db)):
    global _drill_task
    seconds = seconds or config.DRILL_SECONDS
    if _drill_task and not _drill_task.done():
        _drill_task.cancel()
    network.set_node_state(DRILL_NODE, "offline")
    failover.drill_until = time.time() + seconds
    await log_event(db, "drill_started",
                    f"Outage drill: {DRILL_NODE} taken OFFLINE for {seconds:.0f} s (failover is {'ON' if failover.enabled else 'OFF'})",
                    category="network", session_id=controller.session_id)
    await network.tick(db, controller.session_id)
    _drill_task = asyncio.create_task(_end_drill_later(seconds))
    summary = failover.summary(db)
    await manager.broadcast("failover", {"status": summary})
    return {"message": f"{DRILL_NODE} offline for {seconds:.0f} s", "status": summary}
