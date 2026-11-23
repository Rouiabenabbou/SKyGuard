"""
v1.5: a bigger, more resilient network and many more IoT devices (all simulated).

Added once per database (app_flags "network_v15_seeded"):

* a second satellite SAT-2 and a second ground station GS-2 (Agadir), with
  cross links (SAT-1 -> GS-2 and SAT-2 -> GS-1) and an inter-satellite link,
  so losing one satellite or one ground station no longer cuts the satellite path
* four regional 5G towers (Rabat, Fes, Tangier, Khouribga) on fibre to the core,
  each with a backup fibre to the Casablanca tower
* 16 more IoT devices for the six demo companies and the platform

The new nodes and links are recorded as network-builder additions, so they can
be removed or re-wired from Analytics -> Network investigation (edit mode).
Nothing here touches a real network.
"""
import time

from app import config, tenancy
from app.models import AppFlag, Company, CompanyDevice, Device, DeviceProfile, NetworkLink, NetworkNode, TopologyAddition

FLAG = "network_v15_seeded"

INFRA_NODES = [
    # node_id, name, node_type, lat, lon, place_type, address
    ("SAT-2", "CyberSat-2 (LEO satellite)", "satellite", None, None, "", ""),
    ("GS-2", "Ground Station Bravo", "ground_station", 30.4202, -9.5982, "ground_station", "Satellite ground station, Agadir"),
    ("BS-5G-RBT", "5G Base Station Rabat", "base_station", 34.0132, -6.8326, "tower", "5G base station, Rabat"),
    ("BS-5G-FES", "5G Base Station Fès", "base_station", 34.0181, -5.0078, "tower", "5G base station, Fès"),
    ("BS-5G-TNG", "5G Base Station Tangier", "base_station", 35.7673, -5.7997, "tower", "5G base station, Tangier"),
    ("BS-5G-KHO", "5G Base Station Khouribga", "base_station", 32.8860, -6.9208, "tower", "5G base station, Khouribga"),
]

INFRA_LINKS = [
    # source, target, type, primary?
    ("SAT-2", "GS-2", "satellite", True),
    ("GS-2", "CORE", "fiber", True),
    ("SAT-1", "GS-2", "satellite", False),  # backup downlink
    ("SAT-2", "GS-1", "satellite", False),  # backup downlink
    ("SAT-1", "SAT-2", "satellite", False),  # inter-satellite link
    ("BS-5G-RBT", "CORE", "fiber", True),
    ("BS-5G-FES", "CORE", "fiber", True),
    ("BS-5G-TNG", "CORE", "fiber", True),
    ("BS-5G-KHO", "CORE", "fiber", True),
    ("BS-5G-RBT", "BS-5G", "fiber", False),
    ("BS-5G-FES", "BS-5G", "fiber", False),
    ("BS-5G-TNG", "BS-5G", "fiber", False),
    ("BS-5G-KHO", "BS-5G", "fiber", False),
]


def _d(device_id, name, dtype, conn, access, temp, hum, lat, lon, place, address, backup=None, motion=False):
    return {"device_id": device_id, "device_name": name, "device_type": dtype, "location": address.split(",")[0],
            "connection_type": conn, "access_node": access, "backup_node": backup,
            "temp_min": temp[0], "temp_max": temp[1], "humidity_min": hum[0], "humidity_max": hum[1],
            "latitude": lat, "longitude": lon, "place_type": place, "address": address, "has_motion": motion}


# company_id (None = platform) -> devices
NEW_DEVICES = {
    "atlas-mining": [
        _d("IOT-103", "Crusher Vibration Node", "Industrial Vibration Sensor", "5g", "BS-5G-KHO",
           (0, 75), (5, 80), 32.8950, -6.9300, "factory", "Primary crusher, Khouribga"),
        _d("IOT-104", "Explosives Store Climate", "Environmental Sensor", "satellite", "SAT-2",
           (5, 30), (10, 60), 32.8700, -6.8800, "mine", "Explosives magazine, Khouribga", backup="BS-5G-KHO", motion=True),
        _d("IOT-105", "Haul Truck 12 Air Monitor", "Industrial Air Quality Sensor", "satellite", "SAT-1",
           (0, 55), (5, 60), 32.8600, -6.9500, "mine", "Haul road, Khouribga pit", backup="BS-5G-KHO"),
    ],
    "medina-health": [
        _d("IOT-203", "Blood Bank Freezer", "Cold Storage Sensor", "5g", "BS-5G-FES",
           (-40, -25), (10, 80), 34.0340, -5.0010, "cold_storage", "Blood bank, Fès"),
        _d("IOT-204", "ICU Room 1", "Smart Building Sensor", "5g", "BS-5G-FES",
           (20, 25), (35, 60), 34.0360, -5.0050, "hospital", "Intensive care unit, Fès", motion=True),
        _d("IOT-205", "Pharmacy Fridge 2", "Cold Storage Sensor", "5g", "BS-5G-FES",
           (2, 8), (20, 80), 34.0325, -4.9990, "cold_storage", "Hospital pharmacy, Fès"),
    ],
    "tangier-coldchain": [
        _d("IOT-303", "Reefer Container 12", "Refrigerated Container Tracker", "satellite", "SAT-2",
           (-25, -15), (30, 95), 31.2000, -10.6000, "cold_storage", "Container ship, Atlantic off Essaouira", backup="BS-5G-TNG"),
        _d("IOT-304", "Reefer Truck 3", "Refrigerated Container Tracker", "5g", "BS-5G-TNG",
           (-22, -12), (30, 95), 35.7300, -5.8800, "cold_storage", "Reefer truck, Tangier ring road"),
        _d("IOT-305", "Loading Dock Room", "Smart Building Sensor", "5g", "BS-5G-TNG",
           (5, 20), (20, 85), 35.7620, -5.8300, "company", "Loading dock, logistics zone, Tangier", motion=True),
    ],
    "atlas-farms": [
        _d("IOT-004", "Greenhouse Soil Sensor", "Agri Soil Sensor", "satellite", "SAT-1",
           (10, 38), (40, 90), 33.8700, -5.4300, "farm", "Greenhouse, Saïss plain near Meknès", backup="BS-5G-FES"),
        _d("IOT-005", "Milk Cooling Tank", "Cold Storage Sensor", "satellite", "SAT-1",
           (1, 6), (40, 95), 33.8550, -5.4600, "farm", "Milking parlour, Saïss plain near Meknès", backup="BS-5G-FES"),
    ],
    "casa-offices": [
        _d("IOT-006", "Server Room Monitor", "Smart Building Sensor", "5g", "BS-5G",
           (16, 27), (30, 60), 33.5880, -7.6300, "company", "Server room, Maarif, Casablanca"),
        _d("IOT-007", "Lobby Air Quality", "Indoor Air Quality Sensor", "5g", "BS-5G",
           (18, 28), (25, 65), 33.5850, -7.6350, "company", "Main lobby, Maarif, Casablanca", motion=True),
    ],
    "sahara-solar": [
        _d("IOT-008", "Solar Field Weather Station", "Weather Station", "satellite", "SAT-2",
           (-5, 55), (3, 60), 31.0470, -6.8640, "desert", "Solar field, near Ouarzazate"),
        _d("IOT-009", "Inverter Room Sensor", "Industrial Temperature Sensor", "satellite", "SAT-2",
           (5, 45), (5, 60), 31.0500, -6.8700, "factory", "Inverter building, near Ouarzazate"),
    ],
    None: [
        _d("IOT-401", "Port Weather Station", "Weather Station", "5g", "BS-5G-TNG",
           (0, 45), (20, 100), 35.8900, -5.5000, "port", "Container port, Tanger Med"),
        _d("IOT-402", "Highway Air Monitor", "Air Quality Sensor", "5g", "BS-5G-RBT",
           (0, 50), (10, 95), 33.9500, -6.9000, "city", "A1 highway, Rabat-Casablanca"),
    ],
}


def link_id(a: str, b: str) -> str:
    return f"L-{a.replace('-', '')}-{b.replace('-', '')}"[:32]


async def seed_network_v15(db) -> list[str]:
    """Add the extra infrastructure and devices once. Returns the new device IDs."""
    from app.device_registry import RegistryError, add_device
    from app.network_simulator import network

    if not config.SEED_BIG_COMPANIES or db.get(AppFlag, FLAG) is not None:
        return []
    db.add(AppFlag(key=FLAG, value="v1.5"))
    db.commit()

    for node_id, name, node_type, lat, lon, place, address in INFRA_NODES:
        if db.get(NetworkNode, node_id) is not None:
            continue
        db.add(NetworkNode(node_id=node_id, name=name, node_type=node_type, status="online"))
        db.add(TopologyAddition(item_id=node_id, kind="node"))
        if lat is not None:
            db.add(DeviceProfile(node_id=node_id, latitude=lat, longitude=lon, place_type=place, address=address))
    db.flush()
    for a, b, kind, primary in INFRA_LINKS:
        lid = link_id(a, b)
        if db.get(NetworkLink, lid) is not None or db.get(NetworkNode, a) is None or db.get(NetworkNode, b) is None:
            continue
        link = NetworkLink(link_id=lid, source_node=a, target_node=b, link_type=kind, is_active_path=primary)
        network._update_link(link, time.time())
        db.add(link)
        db.add(TopologyAddition(item_id=lid, kind="link"))
    db.commit()

    added = []
    for company_id, devices in NEW_DEVICES.items():
        if company_id and db.get(Company, company_id) is None:
            continue  # that demo company was deleted: don't bring it back
        for d in devices:
            if db.get(Device, d["device_id"]) is not None:
                continue
            tenancy.preassign(d["device_id"], company_id or "")
            try:
                await add_device(db, {**d, "simulated": True})
            except RegistryError as exc:
                print(f"[seed] {d['device_id']} skipped: {exc}")
                continue
            if company_id:
                db.add(CompanyDevice(device_id=d["device_id"], company_id=company_id))
                db.commit()
            added.append(d["device_id"])
    tenancy.refresh(db)
    return added
