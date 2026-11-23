"""
Motion sensors (v1.1) and detection Rule F: movement at night.

A device with a PIR sensor (for example an HC-SR501 on the ESP32, or a simulated
one on the farm) adds "motion": true/false to its normal reading. Every reading
is stored in motion_readings. Movement during the night window
(MOTION_NIGHT_START..MOTION_NIGHT_END, local time) raises a high "movement at
night" alert: a possible intruder or animals escaping. It is a physical alert,
so the device is not marked as suspicious and never auto-quarantined.
"""
import random
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import config
from app.detection_engine import detector
from app.models import Device, DeviceProfile, MotionReading, iso, utcnow

ACTIVE_SECONDS = 15  # "movement now" if the last positive reading is this recent


def is_night(hour: int) -> bool:
    start, end = config.MOTION_NIGHT_START, config.MOTION_NIGHT_END
    return (start <= hour or hour < end) if start > end else (start <= hour < end)


class MotionService:
    def has_sensor(self, db: Session, device_id: str) -> bool:
        p = db.get(DeviceProfile, device_id)
        return bool(p and p.has_motion)

    def state(self, db: Session, device_id: str) -> dict:
        last = (db.query(MotionReading).filter(MotionReading.device_id == device_id, MotionReading.motion.is_(True))
                .order_by(MotionReading.id.desc()).first())
        since = utcnow() - timedelta(hours=24)
        count = (db.query(MotionReading).filter(MotionReading.device_id == device_id, MotionReading.motion.is_(True),
                                                MotionReading.timestamp >= since).count())
        active = bool(last and (utcnow() - last.timestamp).total_seconds() <= ACTIVE_SECONDS)
        return {"motion_now": active, "last_motion_at": iso(last.timestamp) if last else None, "motion_24h": count}

    async def handle(self, db: Session, device: Device, moved: bool, session_id=None,
                     pretend_night: bool = False) -> None:
        db.add(MotionReading(device_id=device.device_id, motion=moved))
        db.commit()
        if not moved:
            return
        night = pretend_night or is_night(datetime.now().hour)
        if night or config.MOTION_ALERT_ALWAYS:
            place = ""
            p = db.get(DeviceProfile, device.device_id)
            if p and p.address:
                place = f" at {p.address}"
            when = "at night" if night else "(alert at any hour is on)"
            await detector.raise_alert(
                db, "movement_detected", "high",
                f"Movement detected by {device.device_name} ({device.device_id}){place} {when}. "
                "Possible intruder or animals escaping: check the camera / send someone.",
                device.device_id, detection_method="rule", mark_suspicious=False)
        # Daytime movement is normal (animals, workers): stored and shown, no alert.

    @staticmethod
    def simulated_motion(state: dict) -> bool:
        """Movement for a simulated PIR: short bursts now and then (animals moving)."""
        if state.get("burst", 0) > 0:
            state["burst"] -= 1
            return True
        # Animals move a lot by day, rarely at night (so night alerts stay meaningful).
        chance = 0.01 if is_night(datetime.now().hour) else 0.08
        if random.random() < chance:
            state["burst"] = random.randint(0, 2)
            return True
        return False


motion = MotionService()
