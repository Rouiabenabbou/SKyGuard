"""
Analytics on the long-term data (v1.3). See warehouse.py.

GET    /api/analytics/summary                         how much data there is, per device
GET    /api/analytics/trends?days=30&bucket=day        daily (or hourly) temperature / humidity / battery
GET    /api/analytics/alerts?days=30                   alerts per day, per type, attack heatmap
GET    /api/analytics/forecast?device_id=IOT-003       next 24 h temperature + humidity with a 95 % band
POST   /api/analytics/rollup                           summarise the live readings now          (operator)
POST   /api/analytics/history {"days":90,"interval_minutes":5}  generate months of history (platform admin)
GET    /api/analytics/history                          progress of the generator
DELETE /api/analytics/history                          delete the long-term history             (platform admin)

A company user only gets its own devices (tenancy.current_hidden()).
"""
import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import tenancy, warehouse
from app.database import get_db
from app.models import Device

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


class HistoryIn(BaseModel):
    days: int = Field(default=90, ge=1, le=warehouse.MAX_DAYS)
    interval_minutes: int = Field(default=5, ge=1, le=60)


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    return warehouse.summary(db, tenancy.current_hidden())


@router.get("/trends")
def trends(days: int = Query(default=30, ge=1, le=warehouse.MAX_DAYS), bucket: Literal["hour", "day"] = "day",
           device_id: str | None = None, db: Session = Depends(get_db)):
    return warehouse.trends(db, tenancy.current_hidden(), days, bucket, device_id.upper() if device_id else None)


@router.get("/alerts")
def alerts(days: int = Query(default=30, ge=1, le=warehouse.MAX_DAYS), db: Session = Depends(get_db)):
    return warehouse.alert_stats(db, tenancy.current_hidden(), days)


@router.get("/forecast")
def forecast(device_id: str, hours: int = Query(default=24, ge=1, le=72), db: Session = Depends(get_db)):
    device_id = device_id.upper()
    if db.get(Device, device_id) is None or device_id in tenancy.current_hidden():
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return warehouse.forecast(db, device_id, hours)


@router.post("/rollup")
def rollup(db: Session = Depends(get_db)):
    return warehouse.rollup_live(db, hours_back=None)


@router.post("/history", status_code=202)
async def generate(body: HistoryIn):
    if warehouse.history_job.state["running"]:
        raise HTTPException(status_code=409, detail="History is already being generated.")
    warehouse.history_job.state = {"running": True, "progress": 0.0, "message": "starting", "rows": 0, "seconds": 0.0}
    asyncio.get_running_loop().run_in_executor(None, warehouse.history_job.run, body.days, body.interval_minutes)
    return {"started": True, "days": body.days, "interval_minutes": body.interval_minutes,
            "estimated_readings": body.days * 24 * (60 // body.interval_minutes)}


@router.get("/history")
def history_status():
    return warehouse.history_job.state


@router.delete("/history")
def delete_history(db: Session = Depends(get_db)):
    if warehouse.history_job.state["running"]:
        raise HTTPException(status_code=409, detail="Wait until the history generator has finished.")
    return {"deleted": warehouse.clear_history(db)}
