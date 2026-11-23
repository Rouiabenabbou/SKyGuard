"""
Built-in attack simulator for the dashboard buttons.

Each attack runs as a short background task and sends its traffic exactly
like a real device would: through the MQTT broker if it is running, or
directly into ingest_telemetry() if not. The detection engine then has to
spot it on its own. Nothing here talks to anything outside this project.

  excessive_traffic   one device floods ~20 messages/s for 8 s       -> Rule A
  unauthorized_device a device ID that is not registered sends data  -> Rule B
  abnormal_reading    a device reports extreme temperature/humidity   -> Rule C
  connection_storm    a device "reconnects" 12 times in a few seconds -> Rule D
"""
import asyncio
import random

from app import mqtt_topics
from app.database import SessionLocal
from app.event_log import log_event
from app.mqtt_client import mqtt_service
from app.telemetry_service import ingest_telemetry


def _reading(device_id: str, abnormal: bool = False) -> dict:
    if abnormal:
        return {"device_id": device_id, "temperature": round(random.uniform(75, 95), 1),
                "humidity": round(random.uniform(1, 4), 1), "battery": 80.0, "source": "attack-sim"}
    return {"device_id": device_id, "temperature": round(random.uniform(20, 26), 1),
            "humidity": round(random.uniform(40, 55), 1), "battery": 90.0, "source": "attack-sim"}


async def _send(db, reading: dict, session_id) -> None:
    if not mqtt_service.publish(mqtt_topics.telemetry_topic(reading["device_id"]), reading):
        await ingest_telemetry(db, {**reading, "source": "attack-sim/direct"}, session_id=session_id)


async def excessive_traffic(device_id: str, session_id, rate: int = 20, duration: float = 8) -> None:
    with SessionLocal() as db:
        await log_event(db, "attack_started", f"[SIMULATION] Excessive traffic attack from {device_id} ({rate} msg/s for {duration:g} s)",
                        category="security", device_id=device_id, session_id=session_id)
        for _ in range(int(rate * duration)):
            await _send(db, _reading(device_id), session_id)
            await asyncio.sleep(1 / rate)


async def unauthorized_device(device_id: str, session_id, count: int = 5) -> None:
    with SessionLocal() as db:
        await log_event(db, "attack_started", f"[SIMULATION] Unregistered device {device_id} starts sending data",
                        category="security", device_id=device_id, session_id=session_id)
        for _ in range(count):
            await _send(db, _reading(device_id), session_id)
            await asyncio.sleep(1)


async def abnormal_reading(device_id: str, session_id, count: int = 3) -> None:
    with SessionLocal() as db:
        await log_event(db, "attack_started", f"[SIMULATION] {device_id} starts reporting abnormal values",
                        category="security", device_id=device_id, session_id=session_id)
        for _ in range(count):
            await _send(db, _reading(device_id, abnormal=True), session_id)
            await asyncio.sleep(2)


async def connection_storm(device_id: str, session_id, count: int = 12) -> None:
    """Publishes repeated "online" status messages, as a device does on every reconnect."""
    from app.detection_engine import detector

    with SessionLocal() as db:
        await log_event(db, "attack_started", f"[SIMULATION] Connection storm from {device_id} ({count} reconnects)",
                        category="security", device_id=device_id, session_id=session_id)
        for _ in range(count):
            if not mqtt_service.publish(mqtt_topics.status_topic(device_id), "online"):
                await detector.connection_attempt(db, device_id)
            await asyncio.sleep(0.3)


ATTACKS = {
    "excessive-traffic": (excessive_traffic, "IOT-002"),
    "unauthorized-device": (unauthorized_device, "IOT-999"),
    "abnormal-reading": (abnormal_reading, "IOT-001"),
    "connection-storm": (connection_storm, "IOT-003"),
}

# v2.1: network, 5G and GNSS scenarios (security events + network rules)
from app.attack_scenarios import SCENARIOS  # noqa: E402

ATTACKS.update(SCENARIOS)
