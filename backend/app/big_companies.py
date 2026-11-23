"""
v1.4: three larger demo customers with their own IoT devices (all fictional,
all simulated). They are added once, on the first start of v1.4, and can be
removed like any operator-added device / company.

* Atlas Mining Corp           - open-pit mine: air quality and conveyor vibration
* Medina Health Hospital      - vaccine fridge and an operating room
* Tangier Cold Chain Logistics - refrigerated container at sea and a freezer warehouse
"""
from app import config, tenancy
from app.auth import hash_password
from app.models import AppFlag, Company, CompanyDevice, CompanyMember, Device, User

BIG_COMPANIES = [
    {
        "company_id": "atlas-mining", "name": "Atlas Mining Corp", "sector": "mining",
        "admin": ("mining_admin", "Mining@2026"),
        "devices": [
            {"device_id": "IOT-101", "device_name": "Pit Air Monitor", "device_type": "Industrial Air Quality Sensor",
             "location": "Open-pit mine, Khouribga plateau", "connection_type": "satellite",
             "temp_min": 0, "temp_max": 50, "humidity_min": 5, "humidity_max": 60,
             "latitude": 32.8811, "longitude": -6.9063, "place_type": "mine",
             "address": "Open-pit phosphate mine, Khouribga plateau", "has_motion": True},
            {"device_id": "IOT-102", "device_name": "Conveyor Vibration Node", "device_type": "Industrial Vibration Sensor",
             "location": "Main conveyor belt", "connection_type": "5g",
             "temp_min": 0, "temp_max": 70, "humidity_min": 5, "humidity_max": 80,
             "latitude": 32.9042, "longitude": -6.9471, "place_type": "factory",
             "address": "Conveyor line 2, processing plant, Khouribga"},
        ],
    },
    {
        "company_id": "medina-health", "name": "Medina Health Hospital", "sector": "hospital",
        "admin": ("hospital_admin", "Hospital@2026"),
        "devices": [
            {"device_id": "IOT-201", "device_name": "Vaccine Fridge 1", "device_type": "Cold Storage Sensor",
             "location": "Pharmacy, ground floor", "connection_type": "5g",
             "temp_min": 2, "temp_max": 8, "humidity_min": 20, "humidity_max": 80,
             "latitude": 34.0331, "longitude": -5.0003, "place_type": "cold_storage",
             "address": "Hospital pharmacy, Fès"},
            {"device_id": "IOT-202", "device_name": "Operating Room 3", "device_type": "Smart Building Sensor",
             "location": "Surgery wing, 2nd floor", "connection_type": "5g",
             "temp_min": 18, "temp_max": 24, "humidity_min": 30, "humidity_max": 60,
             "latitude": 34.0352, "longitude": -5.0041, "place_type": "hospital",
             "address": "Surgery wing, Fès", "has_motion": True},
        ],
    },
    {
        "company_id": "tangier-coldchain", "name": "Tangier Cold Chain Logistics", "sector": "logistics",
        "admin": ("logistics_admin", "Logistics@2026"),
        "devices": [
            {"device_id": "IOT-301", "device_name": "Reefer Container 07", "device_type": "Refrigerated Container Tracker",
             "location": "At sea, Strait of Gibraltar", "connection_type": "satellite",
             "temp_min": -25, "temp_max": -15, "humidity_min": 30, "humidity_max": 95,
             "latitude": 35.9500, "longitude": -5.6000, "place_type": "cold_storage",
             "address": "Container ship, Strait of Gibraltar"},
            {"device_id": "IOT-302", "device_name": "Freezer Warehouse A", "device_type": "Cold Storage Sensor",
             "location": "Logistics zone, Tangier", "connection_type": "5g",
             "temp_min": -30, "temp_max": -18, "humidity_min": 20, "humidity_max": 90,
             "latitude": 35.7595, "longitude": -5.8340, "place_type": "cold_storage",
             "address": "Freezer warehouse, logistics zone, Tangier"},
        ],
    },
]

BIG_COMPANY_ADMINS = [c["admin"] for c in BIG_COMPANIES]


async def seed_big_companies(db) -> list[str]:
    """Create the big companies (with their devices and admins) once per database.
    If you delete them later they stay deleted."""
    from app.device_registry import RegistryError, add_device

    if not config.SEED_BIG_COMPANIES or db.get(AppFlag, "big_companies_seeded") is not None:
        return []
    db.add(AppFlag(key="big_companies_seeded", value="v1.4"))
    db.commit()
    added = []
    for c in BIG_COMPANIES:
        if db.get(Company, c["company_id"]) is not None:
            continue
        db.add(Company(company_id=c["company_id"], name=c["name"], sector=c["sector"]))
        username, password = c["admin"]
        if db.get(User, username) is None:
            db.add(User(username=username, password_hash=hash_password(password), role="admin"))
            db.add(CompanyMember(username=username, company_id=c["company_id"]))
        db.commit()
        for d in c["devices"]:
            if db.get(Device, d["device_id"]) is not None:
                continue
            tenancy.preassign(d["device_id"], c["company_id"])
            try:
                await add_device(db, {**d, "simulated": True})
            except RegistryError as exc:
                print(f"[seed] {d['device_id']} skipped: {exc}")
                continue
            db.add(CompanyDevice(device_id=d["device_id"], company_id=c["company_id"]))
            db.commit()
            added.append(d["device_id"])
    tenancy.refresh(db)
    return added
