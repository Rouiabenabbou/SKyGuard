"""
Device and telemetry endpoints.

GET /api/devices                 -> all registered devices with latest values
GET /api/devices/{device_id}     -> one device + its last 20 readings
GET /api/telemetry               -> recent readings (filters: device_id, limit)
GET /api/events                  -> recent events (newest first)
POST /api/devices/{id}/command   -> {"action": "identify" | "ping"} over MQTT (Phase 11)
PUT  /api/devices/{id}/config    -> operator edits name, type, location and allowed ranges
POST /api/devices                -> operator adds a new IoT device (node + links + simulated twin)
DELETE /api/devices/{id}         -> remove a device the operator added
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app import config, mqtt_topics, tenancy
from app.database import get_db
from app.device_registry import RegistryError, add_device, remove_device
from app.event_log import log_event
from app.models import Company, CompanyDevice, Device, DeviceProfile, DeviceSetting, NetworkEvent, Telemetry
from app.mqtt_client import mqtt_service
from app.simulation_controller import controller
from app.websocket_manager import manager

router = APIRouter(prefix="/api", tags=["devices"])


@router.get("/devices")
def list_devices(db: Session = Depends(get_db)):
    devices = db.query(Device).order_by(Device.device_id).all()
    added = {s.device_id: s for s in db.query(DeviceSetting).all()}
    profiles = {p.node_id: p for p in db.query(DeviceProfile).all()}
    out = []
    for d in devices:
        row = d.to_dict()
        s = added.get(d.device_id)
        row["added_by_operator"] = bool(s and s.added_by_operator)
        row["simulated"] = s.simulated if s else d.device_id not in config.PHYSICAL_DEVICES
        row.update(profile_dict(profiles.get(d.device_id)))
        row.update(motion_state(db, d.device_id))
        row["company_id"] = tenancy.company_of_device(d.device_id) or None  # v1.2
        out.append(row)
    return {"count": len(out), "devices": out}


def profile_dict(p: DeviceProfile | None) -> dict:
    return p.to_dict() if p else {"latitude": None, "longitude": None, "place_type": "", "address": "", "has_motion": False}


def motion_state(db: Session, device_id: str) -> dict:
    from app.motion_service import motion
    return motion.state(db, device_id)


@router.get("/devices/{device_id}")
def get_device(device_id: str, db: Session = Depends(get_db)):
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    readings = (
        db.query(Telemetry)
        .filter(Telemetry.device_id == device_id)
        .order_by(Telemetry.id.desc())
        .limit(20)
        .all()
    )
    row = {**device.to_dict(), **profile_dict(db.get(DeviceProfile, device_id)), **motion_state(db, device_id)}
    return {"device": row, "recent_telemetry": [r.to_dict() for r in readings]}


@router.get("/telemetry")
def list_telemetry(
    device_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    query = db.query(Telemetry)
    if device_id:
        query = query.filter(Telemetry.device_id == device_id)
    rows = query.order_by(Telemetry.id.desc()).limit(limit).all()
    return {"count": len(rows), "telemetry": [r.to_dict() for r in rows]}


@router.get("/events")
def list_events(limit: int = Query(default=50, ge=1, le=1000), db: Session = Depends(get_db)):
    rows = db.query(NetworkEvent).order_by(NetworkEvent.id.desc()).limit(limit).all()
    return {"count": len(rows), "events": [e.to_dict() for e in rows]}


# ---------------------------------------------------------------- Phase 11
class DeviceCommand(BaseModel):
    action: Literal["identify", "ping"]


@router.post("/devices/{device_id}/command")
async def send_command(device_id: str, command: DeviceCommand, db: Session = Depends(get_db)):
    """Send a harmless command to a device over MQTT (cybershield/iot/<id>/command).

    identify -> the ESP32 blinks its LED 10 times, so you can find the board
    ping     -> the ESP32 answers by publishing "online" on its status topic
    (quarantine / release commands are sent by the quarantine service.)"""
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    sent = mqtt_service.publish(mqtt_topics.command_topic(device_id), {"action": command.action})
    if not sent:
        raise HTTPException(status_code=503, detail="MQTT broker not connected: the command cannot reach the device")
    await log_event(db, "device_command", f"Command '{command.action}' sent to {device_id}",
                    category="device", device_id=device_id, session_id=controller.session_id)
    return {"sent": True, "device_id": device_id, "action": command.action}


# ------------------------------------------------- device configuration
class DeviceConfig(BaseModel):
    """Settings a network security operator can change from the dashboard.
    The device ID and its network links stay fixed."""

    device_name: str = Field(min_length=1, max_length=100)
    device_type: str = Field(min_length=1, max_length=50)
    location: str = Field(default="", max_length=100)
    temp_min: float = Field(ge=-60, le=150)
    temp_max: float = Field(ge=-60, le=150)
    humidity_min: float = Field(ge=0, le=100)
    humidity_max: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def check_ranges(self):
        if self.temp_min >= self.temp_max:
            raise ValueError("the minimum temperature must be lower than the maximum")
        if self.humidity_min >= self.humidity_max:
            raise ValueError("the minimum humidity must be lower than the maximum")
        return self


@router.put("/devices/{device_id}/config")
async def configure_device(device_id: str, cfg: DeviceConfig, db: Session = Depends(get_db)):
    """Update a device's settings. The new allowed ranges are used by the
    detection engine from the next reading on. Saved in SQLite, so they
    survive a backend restart."""
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    data = cfg.model_dump()
    data["device_name"] = data["device_name"].strip()
    data["device_type"] = data["device_type"].strip()
    data["location"] = data["location"].strip()
    changes = [f"{k}: {getattr(device, k)} -> {v}" for k, v in data.items() if getattr(device, k) != v]
    for key, value in data.items():
        setattr(device, key, value)
    db.commit()
    db.refresh(device)
    if changes:
        await log_event(db, "device_configured", f"{device_id} settings changed by operator ({'; '.join(changes)})",
                        category="device", device_id=device_id, session_id=controller.session_id)
    await manager.broadcast("device", device.to_dict())
    return {"updated": bool(changes), "changes": changes, "device": device.to_dict()}


# ------------------------------------------------- adding / removing devices
class NewDevice(DeviceConfig):
    device_id: str = Field(min_length=3, max_length=24)
    connection_type: Literal["satellite", "5g"] = "5g"
    simulated: bool = True  # False = a real board will publish its own readings over MQTT
    access_node: str | None = None  # satellite (or 5G tower) it connects to; default SAT-1 / BS-5G
    backup_node: str | None = None  # satellite devices only: 5G tower for failover; default BS-5G
    latitude: float | None = Field(default=None, ge=-90, le=90)  # v1.1: real location
    longitude: float | None = Field(default=None, ge=-180, le=180)
    place_type: str = Field(default="", max_length=30)  # farm, company, desert, lab...
    address: str = Field(default="", max_length=150)
    has_motion: bool = False  # has a PIR motion sensor
    company_id: str | None = Field(default=None, max_length=40)  # v1.2: platform admin picks the company


@router.post("/devices", status_code=201)
async def create_device(new: NewDevice, db: Session = Depends(get_db)):
    """Register a new IoT device. It gets a network node, access links (satellite
    devices also get a backup 5G link for failover) and, unless simulated=false,
    a simulated twin that starts sending readings within a second.
    v1.2: a company admin's device belongs to their company; a platform admin
    may choose the company (company_id) or keep it as a platform device."""
    scope = tenancy.current()
    company_id = scope.company_id if scope.is_company else (new.company_id or None)
    if company_id and db.get(Company, company_id) is None:
        raise HTTPException(status_code=400, detail=f"Company '{company_id}' does not exist.")
    # register the owner first, so live messages sent while the device is created are already filtered
    tenancy.preassign(new.device_id.strip().upper(), company_id or "")
    try:
        device = await add_device(db, new.model_dump(exclude={"company_id"}), session_id=controller.session_id)
    except RegistryError as e:
        tenancy.refresh(db)
        raise HTTPException(status_code=e.status, detail=str(e))
    if company_id:
        db.add(CompanyDevice(device_id=device.device_id, company_id=company_id))
        db.commit()
    tenancy.refresh(db)
    row = {**device.to_dict(), "added_by_operator": True, "simulated": new.simulated, "company_id": company_id,
           **profile_dict(db.get(DeviceProfile, device.device_id)), **motion_state(db, device.device_id)}
    await manager.broadcast("device", row)
    return {"created": True, "device": row}


@router.delete("/devices/{device_id}")
async def delete_device(device_id: str, db: Session = Depends(get_db)):
    """Remove a device the operator added (built-in devices can't be removed)."""
    try:
        await remove_device(db, device_id.upper(), session_id=controller.session_id)
    except RegistryError as e:
        raise HTTPException(status_code=e.status, detail=str(e))
    db.query(CompanyDevice).filter(CompanyDevice.device_id == device_id.upper()).delete()
    db.commit()
    tenancy.refresh(db)
    await manager.broadcast("device_removed", {"device_id": device_id.upper()})
    return {"removed": True, "device_id": device_id.upper()}


# ------------------------------------------------ v1.1: location and sensors
class ProfileIn(BaseModel):
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    place_type: str = Field(default="", max_length=30)
    address: str = Field(default="", max_length=150)
    has_motion: bool | None = None  # devices only


@router.put("/profiles/{node_id}")
async def set_profile(node_id: str, body: ProfileIn, db: Session = Depends(get_db)):
    """Set where a device or network node really is (shown on the real map and the
    3D globe) and, for devices, whether it has a motion sensor."""
    from app.models import NetworkNode
    from app.network_simulator import network

    node_id = node_id.upper()
    node = db.get(NetworkNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    if (body.latitude is None) != (body.longitude is None):
        raise HTTPException(status_code=400, detail="give both latitude and longitude, or neither")
    p = db.get(DeviceProfile, node_id) or DeviceProfile(node_id=node_id)
    p.latitude, p.longitude = body.latitude, body.longitude
    p.place_type, p.address = body.place_type.strip(), body.address.strip()
    if body.has_motion is not None:
        if node.node_type != "iot_device" and body.has_motion:
            raise HTTPException(status_code=400, detail="only IoT devices can have a motion sensor")
        p.has_motion = body.has_motion
        if node_id in controller.devices:  # simulated twin starts / stops sending motion
            controller.devices[node_id].has_motion = body.has_motion
    db.merge(p)
    db.commit()
    where = f"{body.latitude:.4f}, {body.longitude:.4f}" if body.latitude is not None else "no coordinates"
    await log_event(db, "location_changed", f"{node_id} location set to {where} {body.address}".strip(),
                    category="device" if node.node_type == "iot_device" else "network",
                    device_id=node_id if node.node_type == "iot_device" else None, session_id=controller.session_id)
    if node.node_type == "iot_device":
        device = db.get(Device, node_id)
        await manager.broadcast("device", {**device.to_dict(), **profile_dict(db.get(DeviceProfile, node_id)),
                                           **motion_state(db, node_id)})
    await network.tick(db, controller.session_id, update_metrics=False)
    return {"node_id": node_id, "profile": db.get(DeviceProfile, node_id).to_dict()}


@router.post("/devices/{device_id}/motion")
async def simulate_motion(device_id: str, night: bool = True, db: Session = Depends(get_db)):
    """Simulate a person or animal moving in front of a device's motion sensor.
    night=true pretends it is night, so Rule F raises the "movement at night" alert."""
    from app.motion_service import motion

    device = db.get(Device, device_id.upper())
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    if not motion.has_sensor(db, device.device_id):
        raise HTTPException(status_code=400, detail=f"{device.device_id} has no motion sensor "
                            "(turn it on in ⚙ Configure or: sensor <id> motion on)")
    await log_event(db, "attack_simulated", f"Simulated movement in front of {device.device_id}"
                    f"{' at night' if night else ''}", category="security", device_id=device.device_id,
                    session_id=controller.session_id)
    await motion.handle(db, device, True, session_id=controller.session_id, pretend_night=night)
    state = motion.state(db, device.device_id)
    await manager.broadcast("device", {**device.to_dict(), **state})
    return {"device_id": device.device_id, "night": night, **state}
