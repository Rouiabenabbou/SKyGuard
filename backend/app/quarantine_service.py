"""
Logical device quarantine (simulation).

Quarantining a device here means, inside this project only:
1. its security_status becomes "quarantined",
2. every message it sends is BLOCKED: not stored, not shown as a reading,
   only counted (see telemetry_service.ingest_telemetry),
3. it is drawn as isolated on the network map and excluded from routing,
4. a "quarantine" command is published on cybershield/iot/<id>/command so a
   real device (e.g. the ESP32 in Phase 11) could react,
5. everything is recorded in quarantine_records and the event log.

It does NOT isolate a real device from a real telecom network.

Quarantine can be triggered by the operator (dashboard button) or
automatically by the detection engine for serious alerts (AUTO_QUARANTINE).
"""
from sqlalchemy.orm import Session

from app import config
from app.event_log import log_event
from app.models import Device, QuarantineRecord, utcnow
from app.websocket_manager import manager


class QuarantineService:
    def __init__(self) -> None:
        self.auto_enabled = config.AUTO_QUARANTINE
        self.session_id_provider = lambda: None  # set by main.py

    # ------------------------------------------------------------ queries
    @staticmethod
    def active_record(db: Session, device_id: str) -> QuarantineRecord | None:
        return (db.query(QuarantineRecord)
                .filter(QuarantineRecord.device_id == device_id, QuarantineRecord.released_at.is_(None))
                .order_by(QuarantineRecord.id.desc()).first())

    @staticmethod
    def is_quarantined(device: Device | None) -> bool:
        return device is not None and device.security_status == "quarantined"

    # ------------------------------------------------------------ actions
    async def quarantine(self, db: Session, device_id: str, reason: str,
                         triggered_by: str = "operator", alert_id: int | None = None) -> dict:
        device = db.get(Device, device_id)
        if device is None:
            raise ValueError(f"Device '{device_id}' not found")
        if self.is_quarantined(device):
            return {"changed": False, "device": device.to_dict(), "record": self.active_record(db, device_id).to_dict()}

        device.security_status = "quarantined"
        record = QuarantineRecord(device_id=device_id, reason=reason, triggered_by=triggered_by, alert_id=alert_id)
        db.add(record)
        db.commit()

        who = "automatically" if triggered_by == "auto" else "by operator"
        await log_event(db, "device_quarantined", f"{device.device_name} ({device_id}) QUARANTINED {who}: {reason}",
                        category="security", device_id=device_id, session_id=self.session_id_provider())
        self._send_command(device_id, "quarantine")
        await self._broadcast(db, device, record, "quarantined")
        return {"changed": True, "device": device.to_dict(), "record": record.to_dict()}

    async def release(self, db: Session, device_id: str) -> dict:
        device = db.get(Device, device_id)
        if device is None:
            raise ValueError(f"Device '{device_id}' not found")
        record = self.active_record(db, device_id)
        if device.security_status == "suspicious":
            # Not quarantined, only flagged: the operator marks it as trusted again.
            device.security_status = "normal"
            db.commit()
            await log_event(db, "device_cleared", f"Operator cleared suspicion on {device.device_name} ({device_id})",
                            category="security", device_id=device_id, session_id=self.session_id_provider())
            await manager.broadcast("device", device.to_dict())
            return {"changed": True, "device": device.to_dict(), "record": None}
        if not self.is_quarantined(device):
            return {"changed": False, "device": device.to_dict(), "record": record.to_dict() if record else None}

        device.security_status = "normal"
        if record:
            record.released_at = utcnow()
        db.commit()

        # Forget recent detection history so a new attack is detected again immediately.
        from app.detection_engine import detector
        detector.forget_device(device_id)

        blocked = record.blocked_messages if record else 0
        await log_event(db, "device_released",
                        f"{device.device_name} ({device_id}) released from quarantine ({blocked} messages were blocked)",
                        category="security", device_id=device_id, session_id=self.session_id_provider())
        self._send_command(device_id, "release")
        await self._broadcast(db, device, record, "released")
        return {"changed": True, "device": device.to_dict(), "record": record.to_dict() if record else None}

    async def count_blocked(self, db: Session, device: Device) -> None:
        """Called for every message a quarantined device tries to send."""
        record = self.active_record(db, device.device_id)
        device.last_seen = utcnow()  # it's still alive, just isolated
        if device.status != "online":
            device.status = "online"
        if record:
            record.blocked_messages += 1
        db.commit()
        if record and (record.blocked_messages == 1 or record.blocked_messages % 5 == 0):
            await manager.broadcast("quarantine", {"action": "blocked", "device": device.to_dict(), "record": record.to_dict()})

    async def maybe_auto_quarantine(self, db: Session, alert) -> None:
        """Called by the detection engine after every alert."""
        if not (self.auto_enabled and alert.device_id and alert.alert_type in config.AUTO_QUARANTINE_ALERTS):
            return
        device = db.get(Device, alert.device_id)
        if device is None or self.is_quarantined(device):
            return
        await self.quarantine(db, device.device_id, f"alert #{alert.id}: {alert.alert_type.replace('_', ' ')}",
                              triggered_by="auto", alert_id=alert.id)

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _send_command(device_id: str, action: str) -> None:
        from app import mqtt_topics
        from app.mqtt_client import mqtt_service
        mqtt_service.publish(mqtt_topics.command_topic(device_id), {"action": action})

    async def _broadcast(self, db: Session, device: Device, record, action: str) -> None:
        # refresh routes right away, so the map and the 3D twin show the isolation immediately
        from app.network_simulator import network
        await network.tick(db, self.session_id_provider(), update_metrics=False)
        await manager.broadcast("device", device.to_dict())
        await manager.broadcast("quarantine", {"action": action, "device": device.to_dict(),
                                               "record": record.to_dict() if record else None})


quarantine = QuarantineService()
