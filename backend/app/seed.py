"""
The list of registered (authorized) IoT devices.

Any device ID not in this list will later be flagged as an
"Unauthorized IoT device" by the detection engine (Phase 5).
"""
from sqlalchemy.orm import Session

from app import config
from app.models import Device, DeviceProfile, NetworkLink, NetworkNode

REGISTERED_DEVICES = [
    {
        "device_id": "IOT-001",
        "device_name": "Remote Sensor 01",
        "device_type": "Environmental Sensor",
        "location": "Desert monitoring site",
        "connection_type": "satellite",
        "temp_min": 0, "temp_max": 50, "humidity_min": 5, "humidity_max": 70,
    },
    {
        "device_id": "IOT-002",
        "device_name": "Smart Building 02",
        "device_type": "Smart Building Sensor",
        "location": "City office tower",
        "connection_type": "5g",
        "temp_min": 15, "temp_max": 32, "humidity_min": 25, "humidity_max": 70,
    },
    {
        "device_id": "IOT-003",
        "device_name": "Agri Field 03",
        "device_type": "Agricultural Sensor",
        "location": "Rural farmland",
        "connection_type": "satellite",
        "temp_min": -5, "temp_max": 45, "humidity_min": 20, "humidity_max": 95,
    },
]


# Phase 11: the real ESP32 + DHT22 board (only when ESP32_ENABLED=true in .env).
ESP32_DEVICE = {
    "device_id": config.ESP32_DEVICE_ID,
    "device_name": "ESP32 Lab Sensor",
    "device_type": "ESP32 + DHT22 (physical)",
    "location": "University lab (Wi-Fi)",
    "connection_type": "5g",  # reaches the network over Wi-Fi; modelled as terrestrial access
    "temp_min": 5, "temp_max": 40, "humidity_min": 10, "humidity_max": 90,
}
ESP32_LINK = {"link_id": f"L-{config.ESP32_DEVICE_ID.replace('-', '')}-5G", "source_node": config.ESP32_DEVICE_ID,
              "target_node": "BS-5G", "link_type": "5g", "is_active_path": True}


def registered_devices() -> list[dict]:
    return REGISTERED_DEVICES + ([ESP32_DEVICE] if config.ESP32_ENABLED else [])


def seed_devices(db: Session) -> None:
    """Insert any registered device that is not in the database yet."""
    for data in registered_devices():
        if db.get(Device, data["device_id"]) is None:
            db.add(Device(**data))
    db.commit()


# ------------------------------------------------------------------ Phase 4
# The simulated telecom network. IoT devices are network nodes too.
NETWORK_NODES = [
    {"node_id": "SAT-1", "name": "CyberSat-1 (LEO satellite)", "node_type": "satellite"},
    {"node_id": "GS-1", "name": "Ground Station Alpha", "node_type": "ground_station"},
    {"node_id": "BS-5G", "name": "5G Base Station (gNodeB)", "node_type": "base_station"},
    {"node_id": "CORE", "name": "Telecom Core Network", "node_type": "core"},
    {"node_id": "SEC", "name": "Cybersecurity Monitoring Server", "node_type": "security_server"},
]

# is_active_path=True  -> primary link, carries traffic now
# is_active_path=False -> backup link, used for failover in Phase 8
NETWORK_LINKS = [
    # access links: device -> satellite or 5G tower
    {"link_id": "L-IOT001-SAT", "source_node": "IOT-001", "target_node": "SAT-1", "link_type": "satellite", "is_active_path": True},
    {"link_id": "L-IOT003-SAT", "source_node": "IOT-003", "target_node": "SAT-1", "link_type": "satellite", "is_active_path": True},
    {"link_id": "L-IOT002-5G", "source_node": "IOT-002", "target_node": "BS-5G", "link_type": "5g", "is_active_path": True},
    # backup terrestrial access for the satellite devices
    {"link_id": "L-IOT001-5G", "source_node": "IOT-001", "target_node": "BS-5G", "link_type": "5g", "is_active_path": False},
    {"link_id": "L-IOT003-5G", "source_node": "IOT-003", "target_node": "BS-5G", "link_type": "5g", "is_active_path": False},
    # backbone
    {"link_id": "L-SAT-GS", "source_node": "SAT-1", "target_node": "GS-1", "link_type": "satellite", "is_active_path": True},
    {"link_id": "L-GS-CORE", "source_node": "GS-1", "target_node": "CORE", "link_type": "fiber", "is_active_path": True},
    {"link_id": "L-5G-CORE", "source_node": "BS-5G", "target_node": "CORE", "link_type": "fiber", "is_active_path": True},
    {"link_id": "L-CORE-SEC", "source_node": "CORE", "target_node": "SEC", "link_type": "lan", "is_active_path": True},
]


def seed_network(db: Session) -> None:
    """Insert network nodes (including one node per IoT device) and links if missing."""
    for data in NETWORK_NODES:
        if db.get(NetworkNode, data["node_id"]) is None:
            db.add(NetworkNode(**data))
    for device in db.query(Device).all():
        if db.get(NetworkNode, device.device_id) is None:
            db.add(NetworkNode(node_id=device.device_id, name=device.device_name, node_type="iot_device"))
    db.flush()
    links = NETWORK_LINKS + ([ESP32_LINK] if config.ESP32_ENABLED else [])
    for data in links:
        if db.get(NetworkLink, data["link_id"]) is None:
            db.add(NetworkLink(**data))
    db.commit()


# ------------------------------------------------------------------ v1.1
# Where every node really is. The example region is Morocco (desert, city,
# farmland and a ground station within one view). Change any of them from the
# dashboard (⚙ Configure -> location, or click on the real map) or here.
# Coordinates point at real kinds of places, not at real equipment.
PROFILES = {
    "IOT-001": {"latitude": 31.0802, "longitude": -4.0133, "place_type": "desert",
                "address": "Erg Chebbi dunes, near Merzouga"},
    "IOT-002": {"latitude": 33.5856, "longitude": -7.6328, "place_type": "company",
                "address": "Office tower, Maarif business district, Casablanca"},
    "IOT-003": {"latitude": 33.8615, "longitude": -5.4489, "place_type": "farm",
                "address": "Livestock farm, Saïss plain near Meknès", "has_motion": True},
    "ESP32-001": {"latitude": 34.0036, "longitude": -6.8579, "place_type": "lab",
                  "address": "University lab, Rabat"},
    "GS-1": {"latitude": 32.2215, "longitude": -7.9370, "place_type": "ground_station",
             "address": "Satellite ground station, Benguerir"},
    "BS-5G": {"latitude": 33.5731, "longitude": -7.5898, "place_type": "tower",
              "address": "5G base station, Casablanca"},
    "CORE": {"latitude": 33.5400, "longitude": -7.6500, "place_type": "data_center",
             "address": "Telecom core data centre, Casablanca"},
    "SEC": {"latitude": 34.0209, "longitude": -6.8416, "place_type": "soc",
            "address": "Security operations centre, Rabat"},
}


def seed_profiles(db: Session) -> None:
    """Give the built-in nodes their coordinates (only if they have none yet)."""
    for node_id, data in PROFILES.items():
        if db.get(NetworkNode, node_id) is not None and db.get(DeviceProfile, node_id) is None:
            db.add(DeviceProfile(node_id=node_id, **data))
    db.commit()


def seed_companies(db) -> None:
    """v1.2: create the demo companies once (when the companies table is empty)."""
    from app import config
    from app.auth import hash_password
    from app.models import Company, CompanyDevice, CompanyMember, Device, User

    if not config.SEED_DEMO_COMPANIES or db.query(Company).count():
        return
    for company_id, name, sector, devices, admin_user, admin_password in config.DEMO_COMPANIES:
        db.add(Company(company_id=company_id, name=name, sector=sector))
        for device_id in devices:
            if db.get(Device, device_id) is not None and db.get(CompanyDevice, device_id) is None:
                db.add(CompanyDevice(device_id=device_id, company_id=company_id))
        if db.get(User, admin_user) is None:
            db.add(User(username=admin_user, password_hash=hash_password(admin_password), role="admin"))
            db.add(CompanyMember(username=admin_user, company_id=company_id))
    db.commit()
