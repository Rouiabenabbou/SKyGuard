"""
The single path every sensor reading takes into the system:

    rate check -> validate -> check device is registered -> quarantined? (block)
    -> store -> update device -> range check -> push to browsers

The detection engine (Phase 5) is called at each step.

The simulator calls this now. In Phase 3 the MQTT client calls the same
function, so nothing else has to change.
"""
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.detection_engine import detector
from app.event_log import log_event
from app.models import Device, Telemetry, utcnow
from app.schemas import TelemetryIn
from app.websocket_manager import manager


async def ingest_telemetry(db: Session, payload: dict, session_id: int | None = None) -> dict:
    """Process one reading. Returns {"ok": True, ...} or {"ok": False, "error": ...}."""
    # Rule A: count every message, even invalid ones (floods are often garbage).
    claimed_id = payload.get("device_id")
    if isinstance(claimed_id, str) and claimed_id:
        await detector.check_message_rate(db, claimed_id, payload.get("ts_sent"))

    try:
        reading = TelemetryIn(**payload)
    except ValidationError as exc:
        return {"ok": False, "error": "invalid_message", "detail": exc.errors()}

    # v2.7: measurement log for the paper (delivery rate and end-to-end latency)
    seq, ts_sent = payload.get("seq"), payload.get("ts_sent")
    if seq is not None:
        import csv, os, time
        path = os.getenv("MEASURE_LOG", "measure_log.csv")
        new = not os.path.exists(path)
        with open(path, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["device_id", "seq", "ts_sent_ms", "ts_recv_ms"])
            w.writerow([reading.device_id, seq, ts_sent, int(time.time() * 1000)])

    device = db.get(Device, reading.device_id)
    if device is None:
        await detector.unauthorized_device(db, reading.device_id)  # Rule B
        return {"ok": False, "error": "unknown_device", "device_id": reading.device_id}

    # Phase 6: a quarantined device's traffic is blocked (counted, never stored).
    from app.quarantine_service import quarantine
    if quarantine.is_quarantined(device):
        await quarantine.count_blocked(db, device)
        return {"ok": False, "error": "quarantined", "device_id": device.device_id}

    row = Telemetry(
        device_id=reading.device_id,
        temperature=round(reading.temperature, 2),
        humidity=round(reading.humidity, 2),
        battery=round(reading.battery, 1),
        source=reading.source,
    )
    db.add(row)

    came_online = device.status != "online"
    device.temperature = row.temperature
    device.humidity = row.humidity
    device.battery = row.battery
    device.status = "online"
    device.message_count += 1
    device.last_seen = utcnow()
    db.commit()
    try:  # v2.1: counted into the per-minute MQTT flow record (Threat Hunting)
        from app.security_events import note_message
        note_message(device.device_id, len(str(payload)), reading.source)
    except Exception:
        pass

    if came_online:
        await log_event(
            db, "device_online", f"{device.device_name} ({device.device_id}) connected",
            category="device", device_id=device.device_id, session_id=session_id,
        )

    if reading.motion is not None:  # v1.1: motion sensor (Rule F: movement at night)
        from app.motion_service import motion
        await motion.handle(db, device, reading.motion, session_id=session_id)

    await detector.check_sensor_ranges(db, device, row.temperature, row.humidity)  # Rule C
    from app.ml_detector import ml_detector  # Phase 12 (optional, does nothing if disabled)
    await ml_detector.check(db, device, row.temperature, row.humidity)
    from app.ml_autoencoder import ae_detector  # v2.2: ModelArts / MindSpore model (if a model file exists)
    await ae_detector.check(db, device, row.temperature, row.humidity)
    device_row = device.to_dict()
    if reading.motion is not None:
        from app.motion_service import motion
        device_row.update(motion.state(db, device.device_id))
    await manager.broadcast("telemetry", {"device": device_row, "reading": {**row.to_dict(), "motion": reading.motion}})
    return {"ok": True, "reading": row.to_dict()}


async def mark_stale_devices_offline(db: Session, offline_after: float, session_id: int | None = None) -> None:
    """Any online device silent for longer than `offline_after` seconds becomes offline."""
    now = utcnow()
    for device in db.query(Device).filter(Device.status == "online").all():
        if device.last_seen and (now - device.last_seen).total_seconds() > offline_after:
            device.status = "offline"
            db.commit()
            await log_event(
                db, "device_offline", f"{device.device_name} ({device.device_id}) stopped responding",
                category="device", device_id=device.device_id, session_id=session_id,
            )
            await manager.broadcast("device", device.to_dict())
