"""
Engineer tools (v1.4). Everything is SIMULATED for the simulated devices:
a reboot or a firmware update makes the device's twin go quiet for a few
seconds, then it comes back with the new state. A real board (ESP32) gets the
command over MQTT if the broker is connected.

GET  /api/engineering/devices              health of every device (signal, latency, loss, battery, firmware...)
POST /api/devices/{id}/maintenance         {"on": true, "reason": "..."}: no phone alarm while an engineer works on it
POST /api/devices/{id}/reboot              simulated reboot (device offline ~8 s)
POST /api/devices/{id}/firmware            {"version": "1.2.0"}: simulated firmware update (~10 s)
GET  /api/engineering/firmware             the firmware versions you can install
"""
import asyncio
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import config, tenancy
from app.database import SessionLocal, get_db
from app.event_log import log_event
from app.models import Device, DeviceOps, DeviceProfile, utcnow
from app.websocket_manager import manager

router = APIRouter(tags=["engineering"])

FIRMWARE = [
    {"version": "1.0.0", "notes": "First release"},
    {"version": "1.1.0", "notes": "Faster MQTT reconnect, battery saving"},
    {"version": "1.2.0", "notes": "TLS for MQTT (port 8883), signed updates"},
]
LATEST_FIRMWARE = FIRMWARE[-1]["version"]
REBOOT_SECONDS = 8
FLASH_SECONDS = 10
_busy: dict[str, dict] = {}  # device_id -> {"action": "reboot"|"firmware", "until": t, "progress": ...}


def ops_for(db: Session, device_id: str) -> DeviceOps:
    ops = db.get(DeviceOps, device_id)
    if ops is None:
        ops = DeviceOps(device_id=device_id)
        db.add(ops)
        db.commit()
    return ops


def in_maintenance(db: Session, device_id: str | None) -> bool:
    if not device_id:
        return False
    ops = db.get(DeviceOps, device_id)
    return bool(ops and ops.maintenance)


def _user(request: Request) -> str:
    user = getattr(request.state, "user", None)
    return user.username if user else "operator"


def _device(db: Session, device_id: str) -> Device:
    device = db.get(Device, device_id.upper())
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return device


def _signal(access: str | None, latency: float | None, degraded: bool) -> int | None:
    """A simulated radio signal strength in dBm, from the link the device uses."""
    if access is None:
        return None
    base = -78 if access == "satellite" else -67
    if degraded:
        base -= 18
    jitter = (int(time.time() / 5) * 7919 % 9) - 4  # changes a little every 5 s
    return base + jitter


def health_rows(db: Session) -> list[dict]:
    from app.network_simulator import network
    from app.simulation_controller import controller

    snap = getattr(network, "latest", None) or {}
    routes = snap.get("routes", {})
    links = {l["link_id"]: l for l in snap.get("links", [])}
    hidden = tenancy.current_hidden()
    rows = []
    now = utcnow()
    for d in db.query(Device).order_by(Device.device_id):
        if d.device_id in hidden:
            continue
        ops = ops_for(db, d.device_id)
        r = routes.get(d.device_id, {})
        loss = max((links[l]["packet_loss"] for l in r.get("links", []) if l in links), default=None)
        age = (now - d.last_seen).total_seconds() if d.last_seen else None
        busy = _busy.get(d.device_id)
        if busy and busy["until"] < time.time():
            busy = None
        problems = []
        if d.security_status == "quarantined":
            problems.append("quarantined")
        if age is None or age > 30:
            problems.append("no data for 30 s+")
        if d.battery is not None and d.battery < 20:
            problems.append("battery low")
        if r.get("degraded"):
            problems.append("link degraded")
        rows.append({
            "device_id": d.device_id, "device_name": d.device_name, "device_type": d.device_type,
            "status": d.status, "security_status": d.security_status,
            "battery": d.battery, "messages": d.message_count,
            "last_seen_s": round(age, 1) if age is not None else None,
            "access": r.get("access"), "mode": r.get("mode"), "latency_ms": r.get("latency_ms"),
            "packet_loss": loss, "signal_dbm": _signal(r.get("access"), r.get("latency_ms"), bool(r.get("degraded"))),
            "simulated": d.device_id in controller.devices,
            "busy": {"action": busy["action"], "seconds_left": round(busy["until"] - time.time(), 1),
                     "target": busy.get("target")} if busy else None,
            **ops.to_dict(), "latest_firmware": LATEST_FIRMWARE,
            "health": "bad" if any(p in problems for p in ("quarantined", "no data for 30 s+")) else
                      "warn" if problems else "ok",
            "problems": problems,
        })
    return rows


@router.get("/api/engineering/devices")
def device_health(db: Session = Depends(get_db)):
    return {"devices": health_rows(db), "latest_firmware": LATEST_FIRMWARE}


@router.get("/api/engineering/firmware")
def firmware_list():
    return {"firmware": FIRMWARE, "latest": LATEST_FIRMWARE}


class MaintenanceIn(BaseModel):
    on: bool
    reason: str = Field(default="", max_length=200)


@router.post("/api/devices/{device_id}/maintenance")
async def set_maintenance(device_id: str, body: MaintenanceIn, request: Request, db: Session = Depends(get_db)):
    """While a device is in maintenance its alerts still appear, but they don't ring the phone."""
    from app.simulation_controller import controller

    device = _device(db, device_id)
    ops = ops_for(db, device.device_id)
    ops.maintenance = body.on
    ops.maintenance_reason = body.reason.strip() if body.on else ""
    ops.maintenance_by = _user(request) if body.on else ""
    ops.maintenance_since = utcnow() if body.on else None
    db.commit()
    text = (f"{device.device_id} put in maintenance by {ops.maintenance_by}" + (f": {ops.maintenance_reason}" if ops.maintenance_reason else "")
            if body.on else f"{device.device_id} back from maintenance")
    await log_event(db, "maintenance", text, category="device", device_id=device.device_id, session_id=controller.session_id)
    await manager.broadcast("device_ops", ops.to_dict())
    return {"device": ops.to_dict()}


def _pause_twin(device_id: str, seconds: float) -> bool:
    """Make a simulated device go quiet for a while (as if it restarts). False = not simulated."""
    from app.simulation_controller import controller

    if device_id not in controller.devices:
        return False
    controller.next_due[device_id] = time.time() + seconds
    return True


def _send_to_board(device_id: str, payload: dict) -> bool:
    from app import mqtt_topics
    from app.mqtt_client import mqtt_service

    return mqtt_service.publish(mqtt_topics.command_topic(device_id), payload)


@router.post("/api/devices/{device_id}/reboot")
async def reboot(device_id: str, request: Request, db: Session = Depends(get_db)):
    from app.simulation_controller import controller

    device = _device(db, device_id)
    if device.device_id in _busy and _busy[device.device_id]["until"] > time.time():
        raise HTTPException(status_code=409, detail=f"{device.device_id} is busy ({_busy[device.device_id]['action']}).")
    simulated = _pause_twin(device.device_id, REBOOT_SECONDS)
    if not simulated and not _send_to_board(device.device_id, {"action": "reboot"}):
        raise HTTPException(status_code=503, detail="MQTT broker not connected: the reboot cannot reach the board")
    ops = ops_for(db, device.device_id)
    ops.last_reboot = utcnow()
    ops.reboots += 1
    db.commit()
    _busy[device.device_id] = {"action": "reboot", "until": time.time() + REBOOT_SECONDS}
    await log_event(db, "device_reboot", f"{device.device_id} rebooted by {_user(request)}"
                    + (" (simulated)" if simulated else " (command sent to the board)"),
                    category="device", device_id=device.device_id, session_id=controller.session_id)
    await manager.broadcast("device_ops", ops.to_dict())
    return {"device_id": device.device_id, "rebooting": True, "seconds": REBOOT_SECONDS, "simulated": simulated}


class FirmwareIn(BaseModel):
    version: str = Field(default=LATEST_FIRMWARE, max_length=20)


async def _finish_flash(device_id: str, version: str, user: str) -> None:
    from app.simulation_controller import controller

    await asyncio.sleep(FLASH_SECONDS)
    with SessionLocal() as db:
        ops = ops_for(db, device_id)
        old = ops.firmware
        ops.firmware = version
        ops.last_reboot = utcnow()
        ops.reboots += 1
        db.commit()
        await log_event(db, "firmware_update", f"{device_id} firmware {old} -> {version} (by {user}, simulated)",
                        category="device", device_id=device_id, session_id=controller.session_id)
        await manager.broadcast("device_ops", ops.to_dict())


_tasks: set[asyncio.Task] = set()


@router.post("/api/devices/{device_id}/firmware")
async def update_firmware(device_id: str, body: FirmwareIn, request: Request, db: Session = Depends(get_db)):
    device = _device(db, device_id)
    if body.version not in {f["version"] for f in FIRMWARE}:
        raise HTTPException(status_code=400, detail=f"Unknown firmware version '{body.version}'.")
    if not re.fullmatch(r"[0-9.]+", body.version):
        raise HTTPException(status_code=400, detail="Bad version.")
    if device.device_id in _busy and _busy[device.device_id]["until"] > time.time():
        raise HTTPException(status_code=409, detail=f"{device.device_id} is busy ({_busy[device.device_id]['action']}).")
    ops = ops_for(db, device.device_id)
    if ops.firmware == body.version:
        raise HTTPException(status_code=409, detail=f"{device.device_id} already runs {body.version}.")
    simulated = _pause_twin(device.device_id, FLASH_SECONDS + 2)
    if not simulated:
        raise HTTPException(status_code=400, detail="Firmware updates are only simulated; flash a real board with the Arduino IDE.")
    _busy[device.device_id] = {"action": "firmware", "until": time.time() + FLASH_SECONDS, "target": body.version}
    task = asyncio.get_running_loop().create_task(_finish_flash(device.device_id, body.version, _user(request)))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    await manager.broadcast("device_ops", {**ops.to_dict(), "busy": "firmware"})
    return {"device_id": device.device_id, "updating": True, "to": body.version, "seconds": FLASH_SECONDS}


def device_place(db: Session, device_id: str) -> str:
    p = db.get(DeviceProfile, device_id)
    return (p.place_type if p else "") or ""


def metrics_text(db: Session) -> str:
    """Prometheus text format, for cloud monitoring (Huawei Cloud AOM, Grafana...)."""
    from app.models import SecurityAlert, TelemetryArchive, TelemetryHourly
    from app.network_simulator import network
    from app.websocket_manager import manager as ws

    snap = getattr(network, "latest", None) or {}
    avail = snap.get("availability", {})
    lines = [
        "# HELP cybershield_info Application version.",
        "# TYPE cybershield_info gauge",
        f'cybershield_info{{version="{config.APP_VERSION}"}} 1',
        "# TYPE cybershield_network_availability_percent gauge",
        f"cybershield_network_availability_percent {avail.get('current', 0)}",
        "# TYPE cybershield_devices_total gauge",
        f"cybershield_devices_total {db.query(Device).count()}",
        "# TYPE cybershield_devices_quarantined gauge",
        f"cybershield_devices_quarantined {db.query(Device).filter(Device.security_status == 'quarantined').count()}",
        "# TYPE cybershield_alerts_open gauge",
        f"cybershield_alerts_open {db.query(SecurityAlert).filter(SecurityAlert.status == 'open').count()}",
        "# TYPE cybershield_alerts_total counter",
        f"cybershield_alerts_total {db.query(SecurityAlert).count()}",
        "# TYPE cybershield_readings_archived counter",
        f"cybershield_readings_archived {db.query(TelemetryArchive).count()}",
        "# TYPE cybershield_hourly_rows gauge",
        f"cybershield_hourly_rows {db.query(TelemetryHourly).count()}",
        "# TYPE cybershield_websocket_clients gauge",
        f"cybershield_websocket_clients {len(ws.active)}",
        "# TYPE cybershield_device_battery_percent gauge",
    ]
    for d in db.query(Device).order_by(Device.device_id):
        if d.battery is not None:
            lines.append(f'cybershield_device_battery_percent{{device="{d.device_id}"}} {d.battery}')
    return "\n".join(lines) + "\n"


@router.get("/api/engineering/system")
def system_info(db: Session = Depends(get_db)):
    """Where and how the backend runs (for engineers): cloud or PC, database, sizes, uptime."""
    import os
    import platform

    from app import warehouse
    from app.models import SecurityAlert, Telemetry, TelemetryArchive, TelemetryHourly
    from app.mqtt_client import mqtt_service
    from app.routes.system import STARTED_AT

    url = config.DATABASE_URL
    engine = "PostgreSQL" if url.startswith("postgres") else "SQLite" if url.startswith("sqlite") else url.split(":", 1)[0]
    in_docker = os.path.exists("/.dockerenv")
    size = warehouse.database_size(db)
    return {
        "version": config.APP_VERSION,
        "runs_in": "Docker container (cloud-ready)" if in_docker else "Local computer",
        "python": platform.python_version(), "os": f"{platform.system()} {platform.release()}",
        "uptime_seconds": round(time.time() - STARTED_AT),
        "database": {"engine": engine, "size_bytes": size,
                     "rows": {"live_readings": db.query(Telemetry).count(),
                              "archived_readings": db.query(TelemetryArchive).count(),
                              "hourly_summaries": db.query(TelemetryHourly).count(),
                              "alerts": db.query(SecurityAlert).count()}},
        "mqtt": {"connected": mqtt_service.connected, "host": config.MQTT_HOST, "port": config.MQTT_PORT},
        "websocket_clients": len(manager.active),
        "rollup_every_s": config.ROLLUP_INTERVAL_SECONDS,
        "metrics_endpoint": bool(config.METRICS_TOKEN),
        "auth": config.AUTH_ENABLED,
    }
