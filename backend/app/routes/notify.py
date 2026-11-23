"""
Phone alarm settings (v1.2). Platform admin only.

GET  /api/notify/settings     current settings (the Telegram token is never returned)
PUT  /api/notify/settings     change them
POST /api/notify/test         send a test alarm now and say if it arrived at ntfy / Telegram
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.notifier import get_settings, notifier, public_settings

router = APIRouter(prefix="/api/notify", tags=["notify"])


class NotifyIn(BaseModel):
    enabled: bool | None = None
    ntfy_server: str | None = Field(default=None, max_length=200, pattern=r"^https?://\S+$")
    ntfy_topic: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]*$")
    min_severity: Literal["low", "medium", "high", "critical"] | None = None
    telegram_token: str | None = Field(default=None, max_length=100)  # "" removes it
    telegram_chat_id: str | None = Field(default=None, max_length=50)


@router.get("/settings")
def settings(db: Session = Depends(get_db)):
    return {**public_settings(get_settings(db)), "stats": notifier.last_result}


@router.put("/settings")
def update(body: NotifyIn, db: Session = Depends(get_db)):
    s = get_settings(db)
    had_channel = notifier.has_channel(s)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(s, field, value.strip() if isinstance(value, str) else value)
    if not had_channel and notifier.has_channel(s) and body.enabled is None:
        s.enabled = True  # a first topic/bot switches the automatic alarm on
    if s.enabled and s.ntfy_topic and len(s.ntfy_topic) < 12:
        raise HTTPException(status_code=400, detail="Use a longer ntfy topic (12+ characters): anyone who knows it gets your alarms.")
    db.commit()
    return {**public_settings(s), "stats": notifier.last_result}


@router.post("/test")
async def test(db: Session = Depends(get_db)):
    s = get_settings(db)
    if not (s.ntfy_topic or (s.telegram_token and s.telegram_chat_id)):
        raise HTTPException(status_code=400, detail="Set an ntfy topic (or a Telegram bot) first.")
    fake = {"id": 0, "alert_type": "test_alarm", "severity": "critical", "device_id": "TEST",
            "description": "Test alarm from CyberShield SatCom 3D. If your phone rang, the alarm works."}
    results = await notifier.send(public_settings(s) | {"telegram_token": s.telegram_token}, fake)
    ok = bool(results) and all(r["ok"] for r in results)
    if ok and not s.enabled:
        s.enabled = True  # the phone works: from now on attacks ring it automatically
        db.commit()
    return {"results": results, "ok": ok, "enabled": s.enabled}
