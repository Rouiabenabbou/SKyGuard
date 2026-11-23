"""
4D timeline endpoints (Phase 9).

GET /api/timeline/range                  first/last recorded moment and frame count
GET /api/timeline/frames?minutes=10      recorded frames (thinned out to at most `max`)
                                         plus the events in the same period
GET /api/timeline/at?t=<ISO time>        the frame closest before a moment, with recent events
"""
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import NetworkEvent, StateSnapshot
from app.timeline_service import timeline

router = APIRouter(prefix="/api/timeline", tags=["timeline"])


def _parse(value: str | None) -> datetime | None:
    """Accept '2026-11-02T09:00:00Z' and similar; store-compatible naive UTC."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Bad time '{value}', use ISO format like 2026-11-02T09:00:00Z")
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


@router.get("/range")
def time_range(db: Session = Depends(get_db)):
    return timeline.range(db)


@router.get("/frames")
def frames(
    start: str | None = None,
    end: str | None = None,
    minutes: float | None = Query(default=None, gt=0, le=24 * 60, description="Only the last N minutes"),
    max: int = Query(default=600, ge=10, le=3000, alias="max"),
    db: Session = Depends(get_db),
):
    start_dt, end_dt = _parse(start), _parse(end)
    if minutes and not start_dt:
        last = db.query(StateSnapshot).order_by(StateSnapshot.id.desc()).first()
        if last:
            start_dt = last.timestamp - timedelta(minutes=minutes)
    data = timeline.frames(db, start_dt, end_dt, max)
    q = db.query(NetworkEvent)
    if start_dt:
        q = q.filter(NetworkEvent.timestamp >= start_dt)
    if end_dt:
        q = q.filter(NetworkEvent.timestamp <= end_dt)
    events = q.order_by(NetworkEvent.id.desc()).limit(1000).all()
    return {
        "count": len(data),
        "start_ms": data[0]["t"] if data else None,
        "end_ms": data[-1]["t"] if data else None,
        "frames": data,
        "events": [e.to_dict() for e in reversed(events)],
    }


@router.get("/at")
def at(t: str, db: Session = Depends(get_db)):
    moment = _parse(t)
    row = (db.query(StateSnapshot).filter(StateSnapshot.timestamp <= moment)
           .order_by(StateSnapshot.timestamp.desc()).first())
    if row is None:
        raise HTTPException(status_code=404, detail="Nothing was recorded before that moment")
    events = (db.query(NetworkEvent)
              .filter(NetworkEvent.timestamp <= moment, NetworkEvent.timestamp >= moment - timedelta(seconds=30))
              .order_by(NetworkEvent.id).all())
    return {"frame": json.loads(row.data), "events": [e.to_dict() for e in events]}
