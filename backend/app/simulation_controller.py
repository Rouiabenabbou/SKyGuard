"""
Starts, pauses and resets the simulation.

A background loop wakes up once per second. While the simulation is running,
each device sends a reading every SIM_INTERVAL seconds (staggered so they
don't all arrive at once). The loop also marks silent devices as offline.

Data path for each reading:
* MQTT broker connected  -> publish to cybershield/iot/<id>/telemetry, and the
  backend's own subscription receives it (exactly like a real device)
* broker not running     -> hand it straight to ingest_telemetry() ("direct")
"""
import asyncio
import random
import time

from app import config, mqtt_topics
from app.database import SessionLocal
from app.device_simulator import SimulatedDevice
from app.event_log import log_event
from app.mqtt_client import mqtt_service
from app.network_simulator import network
from app.failover_service import failover
from app.timeline_service import timeline
from app.detection_engine import detector
from app.models import (Device, DeviceProfile, DeviceSetting, MotionReading, NetworkEvent, QuarantineRecord, SecurityAlert, SimulationSession,
                        Telemetry, utcnow)
from app.telemetry_service import ingest_telemetry, mark_stale_devices_offline
from app.websocket_manager import manager


class SimulationController:
    def __init__(self) -> None:
        self.running = False
        self.session_id: int | None = None
        self.devices: dict[str, SimulatedDevice] = {}
        self.next_due: dict[str, float] = {}
        self._task: asyncio.Task | None = None
        self._ticks = 0

    # ---------------------------------------------------------------- state
    def status(self) -> dict:
        return {
            "running": self.running,
            "session_id": self.session_id,
            "interval_seconds": config.SIM_INTERVAL,
            "simulated_devices": sorted(self.devices),
            "data_path": "mqtt" if mqtt_service.connected else "direct",
        }

    async def _broadcast_status(self) -> None:
        await manager.broadcast("simulation", self.status())

    def _load_devices(self) -> None:
        """Create a simulated twin for every registered device."""
        with SessionLocal() as db:
            for device in db.query(Device).all():
                # Physical devices (the ESP32, Phase 11) send their own data: never fake them.
                if device.device_id in config.PHYSICAL_DEVICES:
                    continue
                setting = db.get(DeviceSetting, device.device_id)
                if setting is not None and not setting.simulated:  # operator-added real board
                    continue
                if device.device_id not in self.devices:
                    sim = SimulatedDevice(device.device_id, device.battery)
                    if setting is not None:  # operator-added: climate from its allowed ranges
                        from app.device_registry import profile_for
                        sim.profile = profile_for(device.temp_min, device.temp_max,
                                                  device.humidity_min, device.humidity_max)
                    profile = db.get(DeviceProfile, device.device_id)
                    sim.has_motion = bool(profile and profile.has_motion)
                    self.devices[device.device_id] = sim
        now = time.time()
        for i, device_id in enumerate(sorted(self.devices)):
            # Spread first readings over the interval: IOT-001 now, IOT-002 a bit later...
            self.next_due[device_id] = now + i * config.SIM_INTERVAL / max(len(self.devices), 1)

    def add_simulated(self, sim: SimulatedDevice) -> None:
        """Start simulating a device added while the backend runs (first reading in ~1 s)."""
        self.devices[sim.device_id] = sim
        self.next_due[sim.device_id] = time.time() + 1

    def remove_simulated(self, device_id: str) -> None:
        self.devices.pop(device_id, None)
        self.next_due.pop(device_id, None)

    # ------------------------------------------------------------- controls
    async def start(self) -> dict:
        if self.running:
            return self.status()
        with SessionLocal() as db:
            session = db.get(SimulationSession, self.session_id) if self.session_id else None
            if session is None:
                # Close sessions left open by a previous run of the backend.
                db.query(SimulationSession).filter(SimulationSession.status != "ended").update(
                    {"status": "ended", "ended_at": utcnow()}
                )
            if session is None or session.status == "ended":
                session = SimulationSession(status="running")
                db.add(session)
                db.commit()
                self.session_id = session.id
                description = f"Simulation session #{session.id} started"
            else:
                session.status = "running"
                db.commit()
                description = f"Simulation session #{session.id} resumed"
            await log_event(db, "simulation_started", description, session_id=self.session_id)
        self._load_devices()
        self.running = True
        await self._broadcast_status()
        return self.status()

    async def pause(self) -> dict:
        if not self.running:
            return self.status()
        self.running = False
        with SessionLocal() as db:
            session = db.get(SimulationSession, self.session_id)
            if session:
                session.status = "paused"
                db.commit()
            await log_event(db, "simulation_paused", "Simulation paused", session_id=self.session_id)
        await self._broadcast_status()
        return self.status()

    async def reset(self, restart: bool = True) -> dict:
        """Stop, wipe readings and events, reset devices, and start a fresh session."""
        self.running = False
        with SessionLocal() as db:
            try:  # v1.3: keep this session's data in the long-term hourly tables before wiping it
                from app import warehouse
                warehouse.rollup_live(db, hours_back=None)
            except Exception as exc:
                print(f"[rollup] before reset skipped: {exc}")
            if self.session_id:
                session = db.get(SimulationSession, self.session_id)
                if session:
                    session.status = "ended"
                    session.ended_at = utcnow()
            db.query(Telemetry).delete()
            db.query(NetworkEvent).delete()
            db.query(SecurityAlert).delete()
            db.query(QuarantineRecord).delete()
            db.query(MotionReading).delete()
            from app.models import SecurityEvent  # v2.1
            from app.security_events import _flows, net_detector
            from app import gnss
            db.query(SecurityEvent).delete()
            net_detector.reset()
            _flows.clear()
            gnss.clear()
            detector.reset()
            network.reset(db)
            failover.reset(db)
            timeline.reset(db)
            from app.ml_detector import ml_detector
            ml_detector.reset()
            from app.ml_autoencoder import ae_detector
            ae_detector.reset()
            for device in db.query(Device).all():
                device.status = "offline"
                device.security_status = "normal"
                device.temperature = device.humidity = None
                device.battery = None
                device.message_count = 0
                device.last_seen = None
            db.commit()
        self.session_id = None
        self.devices.clear()
        self.next_due.clear()
        await manager.broadcast("reset", {})
        if not restart:
            self._load_devices()
            await self._broadcast_status()
            return self.status()
        return await self.start()

    # ----------------------------------------------------------------- loop
    async def run_forever(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception as exc:  # never let one bad tick kill the loop
                print(f"[simulator] error: {exc}")
            await asyncio.sleep(1)

    async def _tick(self) -> None:
        with SessionLocal() as db:
            if self.running:
                now = time.time()
                for device_id, sim in self.devices.items():
                    if now >= self.next_due[device_id]:
                        reading = sim.read()
                        # Phase 8: no path to the core (link down, handover in progress)
                        # -> the reading never arrives. Counted as lost.
                        route = network.latest.get("routes", {}).get(device_id)
                        if route and not route["connected"] and not route.get("quarantined"):
                            failover.count_lost(device_id)
                            self.next_due[device_id] = now + config.SIM_INTERVAL + random.uniform(-0.3, 0.3)
                            continue
                        sent = mqtt_service.publish(mqtt_topics.telemetry_topic(device_id), reading)
                        if not sent:  # no broker: deliver directly
                            reading["source"] = "builtin/direct"
                            await ingest_telemetry(db, reading, session_id=self.session_id)
                        # small jitter makes it look like real devices
                        self.next_due[device_id] = now + config.SIM_INTERVAL + random.uniform(-0.3, 0.3)
            await mark_stale_devices_offline(db, config.OFFLINE_AFTER, session_id=self.session_id)

            # The network simulator updates every 2 seconds while running.
            self._ticks += 1
            if self._ticks % 2 == 0:
                await network.tick(db, self.session_id, update_metrics=self.running)

    def launch(self) -> None:
        self._task = asyncio.create_task(self.run_forever())

    def shutdown(self) -> None:
        if self._task:
            self._task.cancel()


controller = SimulationController()
