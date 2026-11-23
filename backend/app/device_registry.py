"""
Adding and removing IoT devices at runtime (operator feature).

A new device needs four things, all created here in one step:

1. a row in `devices` (name, type, location, allowed ranges)
2. a network node, so it appears on the 2D map and in the 3D twin
3. access links: satellite devices get a primary satellite link to SAT-1 and a
   backup 5G link to BS-5G (so failover works); 5G devices get one 5G link
4. a simulated twin that sends readings, unless the operator says a real board
   will send its own data over MQTT (topic cybershield/iot/<id>/telemetry)

Only devices added this way can be removed again; the built-in ones stay.
Everything here is part of the simulation: no real device is contacted.
"""
import re

from sqlalchemy.orm import Session

from app.device_simulator import DEFAULT_PROFILE, SimulatedDevice
from app.event_log import log_event
from app.models import Device, DeviceProfile, DeviceSetting, NetworkLink, NetworkNode

ID_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,23}$")


class RegistryError(ValueError):
    """Bad request from the operator (shown as HTTP 400/409)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def profile_for(temp_min: float, temp_max: float, hum_min: float, hum_max: float) -> dict:
    """A simulated climate that stays well inside the allowed ranges."""
    return {
        "temp": round((temp_min + temp_max) / 2, 1),
        "temp_swing": round(max(0.5, (temp_max - temp_min) * 0.15), 1),
        "hum": round((hum_min + hum_max) / 2, 1),
        "hum_swing": round(max(1.0, (hum_max - hum_min) * 0.15), 1),
        "drain": DEFAULT_PROFILE["drain"],
    }


def _link_id(device_id: str, kind: str) -> str:
    return f"L-{device_id.replace('-', '')}-{kind}"[:32]


def access_links(device_id: str, connection_type: str, access_node: str = "SAT-1",
                 backup_node: str = "BS-5G") -> list[dict]:
    if connection_type == "satellite":
        return [
            {"link_id": _link_id(device_id, "SAT"), "source_node": device_id, "target_node": access_node,
             "link_type": "satellite", "is_active_path": True},
            {"link_id": _link_id(device_id, "5G"), "source_node": device_id, "target_node": backup_node,
             "link_type": "5g", "is_active_path": False},  # backup for failover
        ]
    return [{"link_id": _link_id(device_id, "5G"), "source_node": device_id, "target_node": access_node,
             "link_type": "5g", "is_active_path": True}]


def is_simulated(db: Session, device_id: str) -> bool:
    setting = db.get(DeviceSetting, device_id)
    return True if setting is None else setting.simulated


async def add_device(db: Session, data: dict, session_id=None) -> Device:
    from app.network_simulator import network
    from app.simulation_controller import controller

    device_id = data["device_id"].strip().upper()
    if not ID_PATTERN.match(device_id):
        raise RegistryError("the device ID must be 3-24 characters: capital letters, digits and '-', e.g. IOT-004")
    if db.get(Device, device_id) is not None or db.get(NetworkNode, device_id) is not None:
        raise RegistryError(f"a device or node called {device_id} already exists", status=409)
    if data["connection_type"] not in ("satellite", "5g"):
        raise RegistryError("connection_type must be 'satellite' or '5g'")
    # Which satellite / 5G tower it connects to (the defaults are SAT-1 and BS-5G).
    sat = data["connection_type"] == "satellite"
    access = (data.get("access_node") or ("SAT-1" if sat else "BS-5G")).strip().upper()
    backup = (data.get("backup_node") or "BS-5G").strip().upper()
    wanted = [(access, "satellite" if sat else "base_station")] + ([(backup, "base_station")] if sat else [])
    for node_id, node_type in wanted:
        node = db.get(NetworkNode, node_id)
        if node is None:
            raise RegistryError(f"network node {node_id} not found", status=404)
        if node.node_type != node_type:
            raise RegistryError(f"{node_id} is a {node.node_type.replace('_', ' ')}, but a "
                                f"{node_type.replace('_', ' ')} is needed here")

    device = Device(
        device_id=device_id,
        device_name=data["device_name"].strip(),
        device_type=data["device_type"].strip(),
        location=data.get("location", "").strip(),
        connection_type=data["connection_type"],
        temp_min=data["temp_min"], temp_max=data["temp_max"],
        humidity_min=data["humidity_min"], humidity_max=data["humidity_max"],
    )
    db.add(device)
    db.add(NetworkNode(node_id=device_id, name=device.device_name, node_type="iot_device"))
    db.flush()
    for link in access_links(device_id, device.connection_type, access, backup):
        db.add(NetworkLink(**link))
    db.add(DeviceSetting(device_id=device_id, simulated=data.get("simulated", True)))
    db.add(DeviceProfile(node_id=device_id, latitude=data.get("latitude"), longitude=data.get("longitude"),
                         place_type=(data.get("place_type") or "").strip(), address=(data.get("address") or "").strip(),
                         has_motion=bool(data.get("has_motion"))))
    db.commit()
    db.refresh(device)

    if data.get("simulated", True):
        sim = SimulatedDevice(device_id)
        sim.profile = profile_for(device.temp_min, device.temp_max, device.humidity_min, device.humidity_max)
        sim.has_motion = bool(data.get("has_motion"))
        controller.add_simulated(sim)

    via = f"{access}" + (f", backup {backup}" if sat else "")
    how = "simulated" if data.get("simulated", True) else "real board, waiting for its MQTT data"
    await log_event(db, "device_added",
                    f"New device {device_id} ({device.device_name}) added by operator · {device.connection_type} via {via} · {how}",
                    category="device", device_id=device_id, session_id=session_id)
    await network.tick(db, session_id, update_metrics=False)  # show it on the map straight away
    return device


async def remove_device(db: Session, device_id: str, session_id=None) -> None:
    from app.failover_service import failover
    from app.network_simulator import network
    from app.simulation_controller import controller

    device = db.get(Device, device_id)
    if device is None:
        raise RegistryError(f"device '{device_id}' not found", status=404)
    setting = db.get(DeviceSetting, device_id)
    if setting is None or not setting.added_by_operator:
        raise RegistryError(f"{device_id} is a built-in device and can't be removed (only devices you added)", status=409)

    controller.remove_simulated(device_id)
    failover.states.pop(device_id, None)
    links = db.query(NetworkLink).filter(
        (NetworkLink.source_node == device_id) | (NetworkLink.target_node == device_id)).all()
    for link in links:
        network.link_overrides.pop(link.link_id, None)
        db.delete(link)
    db.flush()
    node = db.get(NetworkNode, device_id)
    if node is not None:
        db.delete(node)
    db.delete(setting)
    profile = db.get(DeviceProfile, device_id)
    if profile is not None:
        db.delete(profile)
    db.delete(device)
    db.commit()
    # Its old readings and alerts stay in the history (and in the CSV exports).
    await log_event(db, "device_removed", f"Device {device_id} removed by operator", category="device",
                    device_id=device_id, session_id=session_id)
    await network.tick(db, session_id, update_metrics=False)
